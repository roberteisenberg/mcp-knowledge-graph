"""Phase 5: Cost computation from traces.

Token pricing for Claude models. Computes cost per span and per trace.
"""

# Prices per token (USD), as of early 2025
MODEL_PRICES = {
    "claude-sonnet-4-20250514": {
        "input": 3.00 / 1_000_000,   # $3 per 1M input tokens
        "output": 15.00 / 1_000_000,  # $15 per 1M output tokens
    },
    "claude-haiku-4-5-20251001": {
        "input": 0.80 / 1_000_000,
        "output": 4.00 / 1_000_000,
    },
}

# Default for unknown models
_DEFAULT_PRICE = {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000}


def span_cost(span) -> float:
    """Cost of a single LLM span in USD."""
    if span.kind != "llm":
        return 0.0
    prices = MODEL_PRICES.get(span.name, _DEFAULT_PRICE)
    return (span.input_tokens * prices["input"]) + (span.output_tokens * prices["output"])


def trace_cost(trace) -> float:
    """Total LLM cost for a trace in USD."""
    return sum(span_cost(s) for s in trace.llm_spans)


def format_cost(cost: float) -> str:
    """Format a dollar amount for display."""
    return f"${cost:.4f}"
