"""Phase 5: Eval runner — score any phase's output against ground truth.

Runs the 6 test queries against Phase 3, 4, or 5's MCP server,
then scores each answer for accuracy, cost, and hallucinations.

The client.py in this directory handles standard processing with
always-on tracing. This script adds eval scoring and hallucination
detection on top, and can compare phases side-by-side.

Usage:
    python3 phases/phase5-observability/run_eval.py --phase 5
    python3 phases/phase5-observability/run_eval.py --phase 3
    python3 phases/phase5-observability/run_eval.py --compare
    python3 phases/phase5-observability/run_eval.py --phase 4 --query 4
    python3 phases/phase5-observability/run_eval.py --phase 4 --budget 0.10
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

# --- Path setup ---
PHASE5_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(PHASE5_DIR, "..", ".."))

sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, PHASE5_DIR)

from shared.test_queries import TEST_QUERIES
from local_tools import LOCAL_TOOLS, LOCAL_TOOL_FUNCTIONS
from tracer import TracedClient, Trace, Span
from cost import trace_cost, format_cost
from eval import load_expectations, score_query
from hallucination import detect_hallucinations
from report import print_query_result, print_summary, print_comparison

load_dotenv()


# --- Phase configuration ---

PHASE_SERVER = {
    3: os.path.join(REPO_ROOT, "phases", "phase3-agent-workflows", "server.py"),
    4: os.path.join(REPO_ROOT, "phases", "phase4-semantic", "server.py"),
    5: os.path.join(PHASE5_DIR, "server.py"),
}

_PROMPT_NO_SEMANTIC = """You are a clinical intelligence assistant for a medical clinic.
You have access to:
- The clinic's PostgreSQL database (patients, prescriptions, visits, outcomes, pharmacy inventory, drug interactions)
- The FDA's openFDA API (drug labels, adverse event reports)
- A knowledge graph that connects clinic data to FDA drug data via NDC codes
- Graph traversal tools to explore relationships between patients, drugs, conditions, and interactions
- Local tools for formatting reports and calculating risk scores

Help clinical staff explore data, review medications, check for interactions,
and answer questions about the clinic's patients and drug information.

When answering questions:
- Be thorough but concise
- Use the knowledge graph tools to discover data relationships
- Always check for drug interactions when reviewing medications
- Note when information comes from the clinic DB vs FDA data
- Flag any potential safety concerns"""

_PROMPT_SEMANTIC = """You are a clinical intelligence assistant for a medical clinic.
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

BASE_SYSTEM_PROMPTS = {
    3: _PROMPT_NO_SEMANTIC,
    4: _PROMPT_SEMANTIC,
    5: _PROMPT_SEMANTIC,  # Phase 5 has same capabilities as Phase 4
}


def mcp_tool_to_anthropic(tool) -> dict:
    """Convert an MCP tool definition to Anthropic's tool format."""
    return {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": tool.inputSchema,
    }


async def build_known_entities(session: ClientSession) -> set[str]:
    """Get all entity names from the knowledge graph for hallucination detection."""
    result = await session.call_tool("list_graph_nodes", {})
    if result.isError or not result.content:
        return set()
    data = json.loads(result.content[0].text)
    entities = set()
    for node in data.get("nodes", []):
        name = node.get("name", "")
        if name and len(name) > 1:
            entities.add(name)
    return entities


async def run_query_traced(
    query_id: int,
    user_message: str,
    phase: int,
    traced_client: TracedClient,
    session: ClientSession,
    tools: list[dict],
    mcp_tool_names: set[str],
    system_prompt: str,
) -> Trace:
    """Run a query with full tracing. Returns a Trace with all spans.

    This is intentional duplication of Phase 4's run_query with tracing added.
    The query loop is the same; the difference is span recording.
    """
    traced_client.reset()
    tool_spans = []

    messages = [{"role": "user", "content": user_message}]

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
            start = time.time()
            try:
                if tool_use.name in mcp_tool_names:
                    mcp_result = await session.call_tool(
                        tool_use.name, tool_use.input
                    )
                    if mcp_result.isError:
                        result = json.dumps({"error": "MCP tool error"})
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

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})

    # Merge LLM spans and tool spans, sorted by time
    all_spans = list(traced_client.spans) + tool_spans
    all_spans.sort(key=lambda s: s.start_time)

    return Trace(
        query_id=query_id,
        query=user_message,
        phase=phase,
        spans=all_spans,
        answer=answer,
    )


async def load_resources(session: ClientSession) -> str:
    """Load MCP resources for system prompt context."""
    context = ""
    for uri, label in [
        ("clinic://tables", "Available database tables"),
        ("clinic://summary/prescriptions", "Prescription summary"),
        ("clinic://graph/stats", "Knowledge graph overview"),
    ]:
        try:
            result = await session.read_resource(AnyUrl(uri))
            if result.contents:
                context += f"\n\n{label}:\n{result.contents[0].text}"
        except Exception:
            pass
    return context


async def run_phase_eval(
    phase: int,
    query_ids: list[int] | None,
    budget: float | None,
    expectations: list[dict],
) -> list[dict]:
    """Connect to a phase's MCP server, run queries, score results."""
    server_script = PHASE_SERVER[phase]

    print(f"\n{'=' * 60}")
    print(f"  Phase 5: Evaluating Phase {phase}")
    print(f"{'=' * 60}")

    raw_client = anthropic.Anthropic()
    traced_client = TracedClient(raw_client)

    devnull = open(os.devnull, "w")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[server_script],
    )

    async with stdio_client(server_params, errlog=devnull) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Discover tools
            mcp_tools_result = await session.list_tools()
            mcp_tools = [mcp_tool_to_anthropic(t) for t in mcp_tools_result.tools]
            mcp_tool_names = {t.name for t in mcp_tools_result.tools}
            all_tools = mcp_tools + LOCAL_TOOLS

            print(f"  MCP tools: {', '.join(sorted(mcp_tool_names))}")
            print(f"  Total tools: {len(all_tools)}")

            # Load resources for system prompt
            resource_context = await load_resources(session)
            system_prompt = BASE_SYSTEM_PROMPTS[phase] + resource_context

            # Build entity vocabulary for hallucination detection
            known_entities = await build_known_entities(session)
            print(f"  Known entities: {len(known_entities)}")

            # Run queries
            results = []
            total_cost = 0.0

            queries = TEST_QUERIES
            if query_ids:
                queries = [q for q in TEST_QUERIES if q["id"] in query_ids]

            for tq in queries:
                print(f"\n  Running query {tq['id']}...", end="", flush=True)

                trace = await run_query_traced(
                    query_id=tq["id"],
                    user_message=tq["query"],
                    phase=phase,
                    traced_client=traced_client,
                    session=session,
                    tools=all_tools,
                    mcp_tool_names=mcp_tool_names,
                    system_prompt=system_prompt,
                )

                # Score against expectations
                exp = next(
                    (e for e in expectations if e["query_id"] == tq["id"]), None
                )
                eval_result = score_query(trace.answer, exp) if exp else None

                # Hallucination check
                hall_result = detect_hallucinations(trace, known_entities)

                # Cost
                cost = trace_cost(trace)
                total_cost += cost

                llm_n = len(trace.llm_spans)
                tool_n = len(trace.tool_spans)
                print(f" done ({llm_n} LLM, {tool_n} tools, {format_cost(cost)})")

                results.append({
                    "trace": trace,
                    "eval": eval_result,
                    "hallucinations": hall_result,
                    "cost": cost,
                })

                # Budget check
                if budget and total_cost > budget:
                    print(f"\n  Budget exceeded: {format_cost(total_cost)} > "
                          f"{format_cost(budget)} -- stopping.")
                    break

    devnull.close()
    return results


async def main():
    parser = argparse.ArgumentParser(
        description="Phase 5: Observability — eval, cost, hallucination detection"
    )
    parser.add_argument(
        "--phase", type=int, choices=[3, 4, 5],
        help="Which phase to evaluate (3, 4, or 5)",
    )
    parser.add_argument(
        "--compare", action="store_true",
        help="Run Phase 3 and Phase 4, show side-by-side comparison",
    )
    parser.add_argument(
        "--query", type=int, action="append",
        help="Run only specific query IDs (can repeat: --query 4 --query 5)",
    )
    parser.add_argument(
        "--budget", type=float,
        help="Stop if total cost exceeds this amount (USD)",
    )
    args = parser.parse_args()

    if not args.phase and not args.compare:
        parser.error("Specify --phase 3, --phase 4, or --compare")

    expectations = load_expectations()

    if args.compare:
        results_3 = await run_phase_eval(3, args.query, args.budget, expectations)
        results_4 = await run_phase_eval(4, args.query, args.budget, expectations)

        print("\n--- Phase 3 Detail ---")
        for r in results_3:
            print_query_result(r)
        print_summary(results_3, 3)

        print("\n--- Phase 4 Detail ---")
        for r in results_4:
            print_query_result(r)
        print_summary(results_4, 4)

        print_comparison(results_3, results_4)
    else:
        results = await run_phase_eval(
            args.phase, args.query, args.budget, expectations
        )
        for r in results:
            print_query_result(r)
        print_summary(results, args.phase)


if __name__ == "__main__":
    asyncio.run(main())
