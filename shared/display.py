"""Output formatting for test query results."""

import json


def print_header(text: str):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")


def print_section(title: str, content: str):
    print(f"\n--- {title} ---")
    print(content)


def format_json(data) -> str:
    """Pretty-print JSON-serializable data."""
    return json.dumps(data, indent=2, default=str)


def print_tool_call(tool_name: str, args: dict):
    """Display a tool call for visibility."""
    args_str = ", ".join(f"{k}={v!r}" for k, v in args.items())
    print(f"  [TOOL] {tool_name}({args_str})")


def print_tool_result(result: str, max_length: int = 500):
    """Display a tool result, truncated if needed."""
    if len(result) > max_length:
        print(f"  [RESULT] {result[:max_length]}...")
    else:
        print(f"  [RESULT] {result}")
