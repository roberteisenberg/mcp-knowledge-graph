"""Phase 5: Console report formatting."""

from cost import format_cost


def print_query_result(result: dict):
    """Print results for a single query."""
    trace = result["trace"]
    ev = result["eval"]
    hall = result["hallucinations"]
    cost = result["cost"]

    print(f"\nQuery {trace.query_id}: {trace.query}")

    # Trace summary
    llm_count = len(trace.llm_spans)
    tool_count = len(trace.tool_spans)
    tokens = trace.total_input_tokens + trace.total_output_tokens
    latency = trace.total_latency_ms / 1000

    print(f"  Trace: {llm_count} LLM calls, {tool_count} tool calls, "
          f"{tokens:,} tokens, {format_cost(cost)}, {latency:.1f}s")

    # Tool call breakdown
    tool_names = [s.name for s in trace.tool_spans]
    if tool_names:
        counts = {}
        for name in tool_names:
            counts[name] = counts.get(name, 0) + 1
        breakdown = ", ".join(f"{n}({c})" for n, c in sorted(counts.items()))
        print(f"  Tools: {breakdown}")

    # Eval score
    if ev:
        must = ev["must_include"]
        should = ev["should_include"]
        must_str = f"{len(must['found'])}/{len(must['found']) + len(must['missing'])}"
        should_str = f"{len(should['found'])}/{len(should['found']) + len(should['missing'])}"
        print(f"  Eval:  {ev['score']:.2f} (must: {must_str}, should: {should_str})")
        if must["missing"]:
            print(f"         missing must: {', '.join(must['missing'])}")
        if should["missing"]:
            print(f"         missing should: {', '.join(should['missing'])}")

    # Hallucinations
    h_count = hall["hallucination_count"]
    if h_count == 0:
        print(f"  Hallucinations: 0")
    else:
        items = hall["ungrounded"] + hall["unknown_drugs"]
        print(f"  Hallucinations: {h_count} ({', '.join(items)})")


def print_summary(results: list[dict], phase: int):
    """Print overall summary for a phase."""
    print(f"\n{'=' * 60}")
    print(f"  Summary — Phase {phase}")
    print(f"{'=' * 60}")

    total_cost = sum(r["cost"] for r in results)
    total_llm = sum(len(r["trace"].llm_spans) for r in results)
    total_tool = sum(len(r["trace"].tool_spans) for r in results)
    total_tokens = sum(
        r["trace"].total_input_tokens + r["trace"].total_output_tokens
        for r in results
    )
    total_hallucinations = sum(r["hallucinations"]["hallucination_count"] for r in results)

    scores = [r["eval"]["score"] for r in results if r["eval"]]
    avg_score = sum(scores) / len(scores) if scores else 0.0

    print(f"  Queries:        {len(results)}")
    print(f"  Total cost:     {format_cost(total_cost)}")
    print(f"  Total tokens:   {total_tokens:,}")
    print(f"  LLM calls:      {total_llm}")
    print(f"  Tool calls:     {total_tool}")
    print(f"  Avg eval score: {avg_score:.2f}")
    print(f"  Hallucinations: {total_hallucinations}")


def print_comparison(results_3: list[dict], results_4: list[dict]):
    """Print side-by-side Phase 3 vs Phase 4 comparison."""
    print(f"\n{'=' * 60}")
    print(f"  Phase 3 vs Phase 4 Comparison")
    print(f"{'=' * 60}")

    def _stats(results):
        return {
            "cost": sum(r["cost"] for r in results),
            "llm_calls": sum(len(r["trace"].llm_spans) for r in results),
            "tool_calls": sum(len(r["trace"].tool_spans) for r in results),
            "tokens": sum(
                r["trace"].total_input_tokens + r["trace"].total_output_tokens
                for r in results
            ),
            "hallucinations": sum(
                r["hallucinations"]["hallucination_count"] for r in results
            ),
            "avg_score": (
                sum(r["eval"]["score"] for r in results if r["eval"])
                / max(len([r for r in results if r["eval"]]), 1)
            ),
        }

    s3 = _stats(results_3)
    s4 = _stats(results_4)

    print(f"\n  {'':22s} {'Phase 3':>10s} {'Phase 4':>10s} {'Delta':>10s}")
    print(f"  {'-' * 52}")

    cost_delta = (s4["cost"] - s3["cost"]) / s3["cost"] * 100 if s3["cost"] else 0
    print(f"  {'Total cost':22s} {format_cost(s3['cost']):>10s} {format_cost(s4['cost']):>10s} {cost_delta:>+9.0f}%")

    print(f"  {'Total tokens':22s} {s3['tokens']:>10,} {s4['tokens']:>10,}")
    print(f"  {'LLM calls':22s} {s3['llm_calls']:>10} {s4['llm_calls']:>10}")
    print(f"  {'Tool calls':22s} {s3['tool_calls']:>10} {s4['tool_calls']:>10}")

    score_delta = s4["avg_score"] - s3["avg_score"]
    print(f"  {'Avg eval score':22s} {s3['avg_score']:>10.2f} {s4['avg_score']:>10.2f} {score_delta:>+9.2f}")
    print(f"  {'Hallucinations':22s} {s3['hallucinations']:>10} {s4['hallucinations']:>10}")

    # Per-query comparison
    print(f"\n  Per-query scores:")
    for r3, r4 in zip(results_3, results_4):
        qid = r3["trace"].query_id
        s3q = r3["eval"]["score"] if r3["eval"] else 0
        s4q = r4["eval"]["score"] if r4["eval"] else 0
        h3 = r3["hallucinations"]["hallucination_count"]
        h4 = r4["hallucinations"]["hallucination_count"]
        marker = ""
        if s4q > s3q:
            marker = " <-- Phase 4 better"
        elif s3q > s4q:
            marker = " <-- Phase 3 better"
        print(f"    Q{qid}: {s3q:.2f} vs {s4q:.2f}  (hall: {h3} vs {h4}){marker}")
