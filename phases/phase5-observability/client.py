"""Phase 5: MCP Client — Observability

Builds on Phase 4 by adding always-on tracing, cost tracking,
eval scoring, and hallucination detection. The TracedClient wraps
the Anthropic SDK so every query produces a trace automatically.

Usage:
    python client.py                          # Interactive mode
    python client.py --test                   # Run all 6 test queries with tracing
    python client.py --query "your question"  # Single query with trace
    python client.py --workflow safety_review  # Run automated workflow
    python client.py --prompt review_patient_medications --args '{"patient_id": "1"}'
"""

import argparse
import asyncio
import json
import os
import sys
import time

import anthropic
from dotenv import load_dotenv
from pydantic import AnyUrl
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.display import print_header, print_tool_call, print_tool_result
from shared.test_queries import TEST_QUERIES
from local_tools import LOCAL_TOOLS, LOCAL_TOOL_FUNCTIONS
from workflows import WORKFLOWS
from tracer import TracedClient, Trace, Span
from cost import trace_cost, format_cost

load_dotenv()

BASE_SYSTEM_PROMPT = """You are a clinical intelligence assistant for a medical clinic.
You have access to:
- The clinic's PostgreSQL database (patients, prescriptions, visits, outcomes, pharmacy inventory, drug interactions)
- The FDA's openFDA API (drug labels, adverse event reports)
- A knowledge graph that connects clinic data to FDA drug data via NDC codes
- Graph traversal tools to explore relationships between patients, drugs, conditions, and interactions
- Semantic search to find related concepts by meaning (e.g., "heart problems" finds hypertension, amlodipine)
- Local tools for formatting reports and calculating risk scores

Help clinical staff explore data, review medications, check for interactions,
and answer questions about the clinic's patients and drug information.

When answering questions:
- Be thorough but concise
- Use semantic_search to discover related concepts when the query is broad
- Use the knowledge graph tools to explore specific relationships
- Always check for drug interactions when reviewing medications
- Note when information comes from the clinic DB vs FDA data
- Flag any potential safety concerns"""


def mcp_tool_to_anthropic(tool) -> dict:
    """Convert an MCP tool definition to Anthropic's tool format."""
    return {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": tool.inputSchema,
    }


def print_trace_summary(trace: Trace):
    """Print a compact trace summary after each query."""
    llm_count = len(trace.llm_spans)
    tool_count = len(trace.tool_spans)
    tokens_in = trace.total_input_tokens
    tokens_out = trace.total_output_tokens
    cost = trace_cost(trace)
    latency = trace.total_latency_ms / 1000

    print(f"\n  {'─' * 56}")
    print(f"  TRACE: {llm_count} LLM calls, {tool_count} tool calls, "
          f"{tokens_in + tokens_out:,} tokens "
          f"({tokens_in:,} in / {tokens_out:,} out)")
    print(f"  COST:  {format_cost(cost)}  |  LATENCY: {latency:.1f}s")

    # Per-LLM-call breakdown
    for i, span in enumerate(trace.llm_spans, 1):
        print(f"    LLM #{i}: {span.input_tokens:,} in, {span.output_tokens:,} out, "
              f"{span.latency_ms:.0f}ms, {format_cost(trace_cost(Trace(0, '', 0, [span])))})")

    # Tool call summary
    if trace.tool_spans:
        counts = {}
        for s in trace.tool_spans:
            counts[s.name] = counts.get(s.name, 0) + 1
        breakdown = ", ".join(f"{n}({c})" for n, c in sorted(counts.items()))
        print(f"    Tools: {breakdown}")
    print(f"  {'─' * 56}")


async def run_query(
    user_message: str,
    traced_client: TracedClient,
    session: ClientSession,
    tools: list[dict],
    mcp_tool_names: set[str],
    system_prompt: str,
) -> tuple[str, Trace]:
    """Run a single query through Claude with MCP + local tool access.

    Returns (answer_text, trace).
    """
    traced_client.reset()
    tool_spans = []
    messages = [{"role": "user", "content": user_message}]

    print(f"\n> {user_message}\n")

    while True:
        response = traced_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )

        assistant_text = []
        tool_uses = []

        for block in response.content:
            if block.type == "text":
                assistant_text.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn" or not tool_uses:
            answer = "\n".join(assistant_text)
            break

        tool_results = []
        for tool_use in tool_uses:
            print_tool_call(tool_use.name, tool_use.input)

            start = time.time()
            try:
                if tool_use.name in mcp_tool_names:
                    mcp_result = await session.call_tool(
                        tool_use.name, tool_use.input
                    )
                    if mcp_result.isError:
                        error_text = mcp_result.content[0].text if mcp_result.content else "MCP tool error"
                        result = json.dumps({"error": error_text})
                    elif mcp_result.content:
                        result = mcp_result.content[0].text
                    else:
                        result = "{}"
                else:
                    func = LOCAL_TOOL_FUNCTIONS.get(tool_use.name)
                    if func:
                        result = func(**tool_use.input)
                    else:
                        result = json.dumps({"error": f"Unknown tool: {tool_use.name}"})
            except Exception as e:
                result = json.dumps({"error": str(e)})
            end = time.time()

            tool_spans.append(Span(
                kind="tool",
                name=tool_use.name,
                start_time=start,
                end_time=end,
                tool_args=tool_use.input,
                tool_result=result,
            ))

            print_tool_result(result)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})

    # Build trace from LLM spans + tool spans, sorted by time
    all_spans = list(traced_client.spans) + tool_spans
    all_spans.sort(key=lambda s: s.start_time)

    trace = Trace(
        query_id=0,
        query=user_message,
        phase=5,
        spans=all_spans,
        answer=answer,
    )

    return answer, trace


async def run_prompt(
    prompt_name: str,
    prompt_args: dict,
    traced_client: TracedClient,
    session: ClientSession,
    tools: list[dict],
    mcp_tool_names: set[str],
    system_prompt: str,
) -> tuple[str, Trace]:
    """Run an MCP prompt — get the template from the server, then run it through Claude."""
    print_header(f"Running MCP Prompt: {prompt_name}")

    prompt_result = await session.get_prompt(prompt_name, prompt_args)
    if prompt_result.description:
        print(f"Description: {prompt_result.description}\n")

    prompt_text = ""
    for msg in prompt_result.messages:
        prompt_text += msg.content.text

    print(f"Prompt template:\n{prompt_text[:200]}...\n")

    return await run_query(
        prompt_text, traced_client, session, tools, mcp_tool_names, system_prompt
    )


async def run_test_queries(
    traced_client: TracedClient,
    session: ClientSession,
    tools: list[dict],
    mcp_tool_names: set[str],
    system_prompt: str,
):
    """Run all 6 constant test queries with tracing."""
    print_header("Phase 5: Observability — Running Test Queries")

    total_cost = 0.0
    total_llm = 0
    total_tool = 0

    for tq in TEST_QUERIES:
        print_header(f"Query {tq['id']}: {tq['query']}")
        print(f"Tests: {tq['tests']}\n")

        answer, trace = await run_query(
            tq["query"], traced_client, session, tools, mcp_tool_names, system_prompt
        )
        print(f"\n{answer}")
        print_trace_summary(trace)

        cost = trace_cost(trace)
        total_cost += cost
        total_llm += len(trace.llm_spans)
        total_tool += len(trace.tool_spans)

    # Final summary
    print_header("Test Run Summary")
    print(f"  Total cost:   {format_cost(total_cost)}")
    print(f"  LLM calls:    {total_llm}")
    print(f"  Tool calls:   {total_tool}")
    print(f"  Avg cost/query: {format_cost(total_cost / len(TEST_QUERIES))}")


async def interactive_mode(
    traced_client: TracedClient,
    session: ClientSession,
    tools: list[dict],
    mcp_tool_names: set[str],
    system_prompt: str,
    available_prompts: list,
):
    """Interactive chat loop with tracing on every query."""
    print_header("Phase 5: Observability — Interactive Mode")
    print("Type your questions about clinic data or drug information.")
    print("Every query shows a trace summary with cost.\n")

    if available_prompts:
        print("MCP prompts (use '/prompt <name> <args>'):")
        for p in available_prompts:
            print(f"  /prompt {p.name} — {p.description or 'No description'}")

    print("\nAutomated workflows (use '/workflow <name>'):")
    for key, wf in WORKFLOWS.items():
        print(f"  /workflow {key} — {wf['description']}")

    print("\nType 'quit' to exit.\n")

    session_cost = 0.0

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input or user_input.lower() in ("quit", "exit", "q"):
            print(f"\nSession total: {format_cost(session_cost)}")
            print("Goodbye!")
            break

        if user_input.startswith("/workflow "):
            wf_name = user_input[10:].strip()
            if wf_name in WORKFLOWS:
                print_header(f"Running Workflow: {WORKFLOWS[wf_name]['name']}")
                result = await WORKFLOWS[wf_name]["function"](session, traced_client)
                print(f"\n{result}")
            else:
                print(f"Unknown workflow: {wf_name}")
                print(f"Available: {', '.join(WORKFLOWS.keys())}")
        elif user_input.startswith("/prompt "):
            parts = user_input[8:].strip().split(None, 1)
            prompt_name = parts[0]
            prompt_args = json.loads(parts[1]) if len(parts) > 1 else {}
            answer, trace = await run_prompt(
                prompt_name, prompt_args, traced_client, session,
                tools, mcp_tool_names, system_prompt,
            )
            print(f"\n{answer}")
            print_trace_summary(trace)
            session_cost += trace_cost(trace)
        else:
            answer, trace = await run_query(
                user_input, traced_client, session, tools, mcp_tool_names,
                system_prompt,
            )
            print(f"\n{answer}")
            print_trace_summary(trace)
            session_cost += trace_cost(trace)


async def main():
    parser = argparse.ArgumentParser(
        description="Phase 5: Observability — clinical intelligence with tracing"
    )
    parser.add_argument("--test", action="store_true", help="Run all 6 test queries")
    parser.add_argument("--query", type=str, help="Run a single query")
    parser.add_argument("--workflow", type=str, help="Run an automated workflow",
                        choices=list(WORKFLOWS.keys()))
    parser.add_argument("--prompt", type=str, help="Run an MCP prompt by name")
    parser.add_argument("--args", type=str, default="{}", help="Prompt arguments as JSON")
    args = parser.parse_args()

    raw_client = anthropic.Anthropic()
    traced_client = TracedClient(raw_client)

    server_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[server_script],
    )

    devnull = open(os.devnull, "w")
    async with stdio_client(server_params, errlog=devnull) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # --- Discover MCP tools ---
            mcp_tools_result = await session.list_tools()
            mcp_tools = [mcp_tool_to_anthropic(t) for t in mcp_tools_result.tools]
            mcp_tool_names = {t.name for t in mcp_tools_result.tools}

            all_tools = mcp_tools + LOCAL_TOOLS

            print(f"MCP tools discovered: {', '.join(sorted(mcp_tool_names))}")
            print(f"Local tools registered: {', '.join(sorted(LOCAL_TOOL_FUNCTIONS.keys()))}")
            print(f"Total tools available: {len(all_tools)}")
            print(f"Workflows available: {', '.join(WORKFLOWS.keys())}")

            # --- Discover MCP prompts ---
            prompts_result = await session.list_prompts()
            available_prompts = prompts_result.prompts if prompts_result.prompts else []
            if available_prompts:
                print(f"MCP prompts: {', '.join(p.name for p in available_prompts)}")

            # --- Read resources for context ---
            resource_context = ""
            try:
                tables_result = await session.read_resource(AnyUrl("clinic://tables"))
                if tables_result.contents:
                    resource_context += f"\n\nAvailable database tables:\n{tables_result.contents[0].text}"
                    print(f"Resource loaded: clinic://tables")
            except Exception as e:
                print(f"Warning: Could not read clinic://tables: {e}")

            try:
                rx_result = await session.read_resource(AnyUrl("clinic://summary/prescriptions"))
                if rx_result.contents:
                    resource_context += f"\n\nPrescription summary:\n{rx_result.contents[0].text}"
                    print(f"Resource loaded: clinic://summary/prescriptions")
            except Exception as e:
                print(f"Warning: Could not read prescription summary: {e}")

            try:
                kg_result = await session.read_resource(AnyUrl("clinic://graph/stats"))
                if kg_result.contents:
                    resource_context += f"\n\nKnowledge graph overview:\n{kg_result.contents[0].text}"
                    print(f"Resource loaded: clinic://graph/stats")
            except Exception as e:
                print(f"Warning: Could not read graph stats: {e}")

            system_prompt = BASE_SYSTEM_PROMPT + resource_context

            print(f"\nTracing: ON (all queries traced with cost tracking)")

            # --- Run mode ---
            if args.workflow:
                wf = WORKFLOWS[args.workflow]
                print_header(f"Running Workflow: {wf['name']}")
                result = await wf["function"](session, traced_client)
                print(f"\n{result}")
            elif args.prompt:
                prompt_args = json.loads(args.args)
                answer, trace = await run_prompt(
                    args.prompt, prompt_args, traced_client, session,
                    all_tools, mcp_tool_names, system_prompt,
                )
                print(f"\n{answer}")
                print_trace_summary(trace)
            elif args.test:
                await run_test_queries(
                    traced_client, session, all_tools, mcp_tool_names, system_prompt
                )
            elif args.query:
                answer, trace = await run_query(
                    args.query, traced_client, session, all_tools, mcp_tool_names,
                    system_prompt,
                )
                print(f"\n{answer}")
                print_trace_summary(trace)
            else:
                await interactive_mode(
                    traced_client, session, all_tools, mcp_tool_names,
                    system_prompt, available_prompts,
                )


if __name__ == "__main__":
    asyncio.run(main())
