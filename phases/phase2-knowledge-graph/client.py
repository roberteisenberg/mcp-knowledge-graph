"""Phase 2: MCP Client — Knowledge Graph + Prompts

Builds on Phase 1 by adding:
- Knowledge graph context (graph stats injected from resources)
- MCP prompt support (structured templates the LLM can follow)
- More MCP tools (graph traversal, path finding, node exploration)

Usage:
    python client.py                          # Interactive mode
    python client.py --test                   # Run all 6 test queries
    python client.py --query "your question"  # Single query
    python client.py --prompt review_patient_medications --args '{"patient_id": "1"}'
"""

import argparse
import asyncio
import json
import os
import sys

import anthropic
from dotenv import load_dotenv
from pydantic import AnyUrl
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.display import print_header, print_tool_call, print_tool_result
from shared.test_queries import TEST_QUERIES
from local_tools import LOCAL_TOOLS, LOCAL_TOOL_FUNCTIONS

load_dotenv()

BASE_SYSTEM_PROMPT = """You are a clinical intelligence assistant for a medical clinic.
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


def mcp_tool_to_anthropic(tool) -> dict:
    """Convert an MCP tool definition to Anthropic's tool format."""
    return {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": tool.inputSchema,
    }


async def run_query(
    user_message: str,
    anthropic_client: anthropic.Anthropic,
    session: ClientSession,
    tools: list[dict],
    mcp_tool_names: set[str],
    system_prompt: str,
) -> str:
    """Run a single query through Claude with MCP + local tool access."""
    messages = [{"role": "user", "content": user_message}]

    print(f"\n> {user_message}\n")

    while True:
        response = anthropic_client.messages.create(
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
            return "\n".join(assistant_text)

        tool_results = []
        for tool_use in tool_uses:
            print_tool_call(tool_use.name, tool_use.input)

            try:
                if tool_use.name in mcp_tool_names:
                    mcp_result = await session.call_tool(
                        tool_use.name, tool_use.input
                    )
                    if mcp_result.isError:
                        result = json.dumps({"error": "MCP tool returned an error"})
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

            print_tool_result(result)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})


async def run_prompt(
    prompt_name: str,
    prompt_args: dict,
    anthropic_client: anthropic.Anthropic,
    session: ClientSession,
    tools: list[dict],
    mcp_tool_names: set[str],
    system_prompt: str,
) -> str:
    """Run an MCP prompt — get the template from the server, then run it through Claude."""
    print_header(f"Running MCP Prompt: {prompt_name}")

    prompt_result = await session.get_prompt(prompt_name, prompt_args)
    if prompt_result.description:
        print(f"Description: {prompt_result.description}\n")

    # Extract the prompt text from the messages
    prompt_text = ""
    for msg in prompt_result.messages:
        prompt_text += msg.content.text

    print(f"Prompt template:\n{prompt_text[:200]}...\n")

    return await run_query(
        prompt_text, anthropic_client, session, tools, mcp_tool_names, system_prompt
    )


async def run_test_queries(
    anthropic_client: anthropic.Anthropic,
    session: ClientSession,
    tools: list[dict],
    mcp_tool_names: set[str],
    system_prompt: str,
):
    """Run all 6 constant test queries."""
    print_header("Phase 2: Knowledge Graph — Running Test Queries")

    for tq in TEST_QUERIES:
        print_header(f"Query {tq['id']}: {tq['query']}")
        print(f"Tests: {tq['tests']}\n")

        answer = await run_query(
            tq["query"], anthropic_client, session, tools, mcp_tool_names, system_prompt
        )
        print(f"\n{answer}")
        print(f"\n{'─' * 60}")


async def interactive_mode(
    anthropic_client: anthropic.Anthropic,
    session: ClientSession,
    tools: list[dict],
    mcp_tool_names: set[str],
    system_prompt: str,
    available_prompts: list,
):
    """Interactive chat loop with prompt support."""
    print_header("Phase 2: Knowledge Graph — Interactive Mode")
    print("Type your questions about clinic data or drug information.")
    if available_prompts:
        print(f"\nAvailable prompts (use '/prompt <name> <args>'):")
        for p in available_prompts:
            print(f"  /prompt {p.name} — {p.description or 'No description'}")
    print("\nType 'quit' to exit.\n")

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input or user_input.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        # Check for /prompt command
        if user_input.startswith("/prompt "):
            parts = user_input[8:].strip().split(None, 1)
            prompt_name = parts[0]
            prompt_args = json.loads(parts[1]) if len(parts) > 1 else {}
            answer = await run_prompt(
                prompt_name, prompt_args, anthropic_client, session,
                tools, mcp_tool_names, system_prompt,
            )
        else:
            answer = await run_query(
                user_input, anthropic_client, session, tools, mcp_tool_names,
                system_prompt,
            )

        print(f"\n{answer}")


async def main():
    parser = argparse.ArgumentParser(
        description="Phase 2: Knowledge Graph clinical intelligence tool"
    )
    parser.add_argument("--test", action="store_true", help="Run all 6 test queries")
    parser.add_argument("--query", type=str, help="Run a single query")
    parser.add_argument("--prompt", type=str, help="Run an MCP prompt by name")
    parser.add_argument("--args", type=str, default="{}", help="Prompt arguments as JSON")
    args = parser.parse_args()

    anthropic_client = anthropic.Anthropic()

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

            # --- Run queries ---
            if args.prompt:
                prompt_args = json.loads(args.args)
                answer = await run_prompt(
                    args.prompt, prompt_args, anthropic_client, session,
                    all_tools, mcp_tool_names, system_prompt,
                )
                print(f"\n{answer}")
            elif args.test:
                await run_test_queries(
                    anthropic_client, session, all_tools, mcp_tool_names, system_prompt
                )
            elif args.query:
                answer = await run_query(
                    args.query, anthropic_client, session, all_tools, mcp_tool_names,
                    system_prompt,
                )
                print(f"\n{answer}")
            else:
                await interactive_mode(
                    anthropic_client, session, all_tools, mcp_tool_names,
                    system_prompt, available_prompts,
                )


if __name__ == "__main__":
    asyncio.run(main())
