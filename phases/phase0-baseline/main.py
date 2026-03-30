"""Phase 0: Baseline — All tools hardcoded, no MCP.

This is the "before." Everything lives in one script:
- Clinic DB queries (private data)
- FDA API calls (public data)
- Formatting (app logic)

Claude calls hardcoded tool definitions through the Anthropic SDK.
There are no boundaries, no access control, and no reuse.

Usage:
    python main.py                          # Interactive mode
    python main.py --test                   # Run all 6 test queries
    python main.py --query "your question"  # Single query
"""

import argparse
import json
import os
import sys

import anthropic
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.display import print_header, print_tool_call, print_tool_result
from shared.test_queries import TEST_QUERIES
from tools import TOOLS, TOOL_FUNCTIONS

load_dotenv()

SYSTEM_PROMPT = """You are a clinical intelligence assistant for a medical clinic.
You have access to:
- The clinic's PostgreSQL database (patients, prescriptions, visits, outcomes, pharmacy inventory, drug interactions)
- The FDA's openFDA API (drug labels, adverse event reports)
- A report formatting tool

Help clinical staff explore data, review medications, check for interactions,
and answer questions about the clinic's patients and drug information.

When answering questions:
- Be thorough but concise
- Always check for drug interactions when reviewing medications
- Note when information comes from the clinic DB vs FDA data
- Flag any potential safety concerns"""


def run_query(user_message: str, client: anthropic.Anthropic) -> str:
    """Run a single query through Claude with tool access."""
    messages = [{"role": "user", "content": user_message}]

    print(f"\n> {user_message}\n")

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Process response content blocks
        assistant_text = []
        tool_uses = []

        for block in response.content:
            if block.type == "text":
                assistant_text.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)

        # Add assistant message to conversation
        messages.append({"role": "assistant", "content": response.content})

        # If no tool calls, we're done
        if response.stop_reason == "end_turn" or not tool_uses:
            return "\n".join(assistant_text)

        # Execute tool calls and add results
        tool_results = []
        for tool_use in tool_uses:
            print_tool_call(tool_use.name, tool_use.input)

            func = TOOL_FUNCTIONS.get(tool_use.name)
            if func:
                try:
                    result = func(**tool_use.input)
                except Exception as e:
                    result = json.dumps({"error": str(e)})
            else:
                result = json.dumps({"error": f"Unknown tool: {tool_use.name}"})

            print_tool_result(result)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})


def run_test_queries(client: anthropic.Anthropic):
    """Run all 6 constant test queries."""
    print_header("Phase 0: Baseline — Running Test Queries")

    for tq in TEST_QUERIES:
        print_header(f"Query {tq['id']}: {tq['query']}")
        print(f"Tests: {tq['tests']}\n")

        answer = run_query(tq["query"], client)
        print(f"\n{answer}")
        print(f"\n{'─'*60}")


def interactive_mode(client: anthropic.Anthropic):
    """Interactive chat loop."""
    print_header("Phase 0: Baseline — Interactive Mode")
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

        answer = run_query(user_input, client)
        print(f"\n{answer}")


def main():
    parser = argparse.ArgumentParser(description="Phase 0: Baseline clinical intelligence tool")
    parser.add_argument("--test", action="store_true", help="Run all 6 test queries")
    parser.add_argument("--query", type=str, help="Run a single query")
    args = parser.parse_args()

    client = anthropic.Anthropic()

    if args.test:
        run_test_queries(client)
    elif args.query:
        answer = run_query(args.query, client)
        print(f"\n{answer}")
    else:
        interactive_mode(client)


if __name__ == "__main__":
    main()
