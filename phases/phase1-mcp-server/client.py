"""Phase 1: MCP Client — discovers tools from the MCP server.

The key difference from Phase 0:
- Data access tools (clinic DB, FDA API) come from the MCP server
- Local tools (formatting, computation) stay in the app
- Claude sees all tools uniformly — it doesn't know which are MCP vs local
- The client has NO database connection string or API details

This is the "when to MCP" lesson in code.

Usage:
    python client.py                          # Interactive mode
    python client.py --test                   # Run all 6 test queries
    python client.py --query "your question"  # Single query
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
- Local tools for formatting reports and calculating risk scores

Help clinical staff explore data, review medications, check for interactions,
and answer questions about the clinic's patients and drug information.

When answering questions:
- Be thorough but concise
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

        # Execute tool calls — route to MCP server or local functions
        tool_results = []
        for tool_use in tool_uses:
            print_tool_call(tool_use.name, tool_use.input)

            try:
                if tool_use.name in mcp_tool_names:
                    # Route to MCP server
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
                    # Route to local tool
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


async def run_test_queries(
    anthropic_client: anthropic.Anthropic,
    session: ClientSession,
    tools: list[dict],
    mcp_tool_names: set[str],
    system_prompt: str,
):
    """Run all 6 constant test queries."""
    print_header("Phase 1: MCP Server — Running Test Queries")

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
):
    """Interactive chat loop."""
    print_header("Phase 1: MCP Server — Interactive Mode")
    print("Type your questions about clinic data or drug information.")
    print("Type 'quit' to exit.\n")

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input or user_input.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        answer = await run_query(
            user_input, anthropic_client, session, tools, mcp_tool_names, system_prompt
        )
        print(f"\n{answer}")


async def main():
    parser = argparse.ArgumentParser(
        description="Phase 1: MCP-powered clinical intelligence tool"
    )
    parser.add_argument("--test", action="store_true", help="Run all 6 test queries")
    parser.add_argument("--query", type=str, help="Run a single query")
    args = parser.parse_args()

    anthropic_client = anthropic.Anthropic()

    # Connect to the MCP server via stdio transport.
    # The server runs as a subprocess — the client never sees the DB
    # connection string or FDA API details.
    server_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[server_script],
    )

    # errlog=devnull suppresses MCP server-side "Processing request" logs
    devnull = open(os.devnull, "w")
    async with stdio_client(server_params, errlog=devnull) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # --- Discover MCP tools ---
            mcp_tools_result = await session.list_tools()
            mcp_tools = [mcp_tool_to_anthropic(t) for t in mcp_tools_result.tools]
            mcp_tool_names = {t.name for t in mcp_tools_result.tools}

            # Combine MCP tools + local tools — Claude sees them all uniformly
            all_tools = mcp_tools + LOCAL_TOOLS

            print(f"MCP tools discovered: {', '.join(sorted(mcp_tool_names))}")
            print(f"Local tools registered: {', '.join(sorted(LOCAL_TOOL_FUNCTIONS.keys()))}")
            print(f"Total tools available: {len(all_tools)}")

            # --- Read resources for context ---
            # Resources are reference data loaded at startup and injected into
            # the system prompt. This is the difference between resources (context)
            # and tools (actions).
            resource_context = ""
            try:
                tables_result = await session.read_resource(AnyUrl("clinic://tables"))
                if tables_result.contents:
                    tables_data = tables_result.contents[0].text
                    resource_context += f"\n\nAvailable database tables:\n{tables_data}"
                    print(f"Resource loaded: clinic://tables")
            except Exception as e:
                print(f"Warning: Could not read clinic://tables resource: {e}")

            try:
                rx_result = await session.read_resource(
                    AnyUrl("clinic://summary/prescriptions")
                )
                if rx_result.contents:
                    rx_data = rx_result.contents[0].text
                    resource_context += f"\n\nPrescription summary:\n{rx_data}"
                    print(f"Resource loaded: clinic://summary/prescriptions")
            except Exception as e:
                print(f"Warning: Could not read prescription summary resource: {e}")

            system_prompt = BASE_SYSTEM_PROMPT + resource_context

            # --- Run queries ---
            if args.test:
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
                    anthropic_client, session, all_tools, mcp_tool_names, system_prompt
                )


if __name__ == "__main__":
    asyncio.run(main())
