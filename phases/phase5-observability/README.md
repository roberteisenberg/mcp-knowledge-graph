# Phase 5 — Observability

**MCP concept:** Instrument the system. Prove that the architecture decisions in Phases 1-4 actually work.

Building LLM applications is phase one. Knowing whether they work — and what they cost — is phase two. Phase 5 adds tracing, cost tracking, eval, and hallucination detection as part of standard processing, not as an afterthought bolted on from outside.

## What It Adds

| Capability | What it does | Why it matters |
|---|---|---|
| **Tracing** | Records every LLM call (model, tokens, latency) and every tool call (name, args, result, latency) | See the full execution path. Diagnose wrong tool calls, excessive retries, slow responses. |
| **Cost tracking** | Computes dollar cost per query from token counts and model pricing | Prove Phase 3 workflows are cheaper. Set budget limits. |
| **Eval** | Scores answers against expected entities (must_include, should_include) | "It looks right" is not a test suite. Measure accuracy across phases. |
| **Hallucination detection** | Compares entities in the answer against entities in tool results | Catch when the LLM mentions drugs, patients, or conditions that no tool ever returned. |

## How Tracing Is Integrated

Tracing is always-on in `client.py`. The `TracedClient` wraps `anthropic.Anthropic` as a drop-in proxy — every `messages.create()` call is intercepted to record a span. Tool call spans are recorded inline in the query loop. After every query, the client prints a trace summary:

```
  ────────────────────────────────────────────────────────
  TRACE: 4 LLM calls, 8 tool calls, 6,421 tokens (4,102 in / 2,319 out)
  COST:  $0.0287  |  LATENCY: 12.1s
    LLM #1: 1,847 in, 312 out, 2100ms, $0.0102
    LLM #2: 2,923 in, 156 out, 1400ms, $0.0111
    ...
    Tools: semantic_search(1), get_neighbors(3), get_patient(2), check_interactions(2)
  ────────────────────────────────────────────────────────
```

This isn't a separate eval harness — it's how the client works. Every query you run produces a trace.

## Two Entry Points

**`client.py`** — Standard processing with always-on tracing. Same interface as Phase 4's client (interactive, `--test`, `--query`, `--workflow`), but every query prints its trace and cost.

**`run_eval.py`** — Evaluation tool that adds scoring and hallucination detection. Can target any phase's server (3, 4, or 5) and compare phases side-by-side.

| | `client.py` | `run_eval.py` |
|---|---|---|
| Tracing + cost | Always on | Always on |
| Eval scoring | No | Yes — scores against expectations.json |
| Hallucination detection | No | Yes — compares answer vs tool results |
| Cross-phase comparison | No | Yes — `--compare` runs Phase 3 vs 4 |
| Interactive mode | Yes | No |

## Eval Scoring

Each of the 6 test queries has expected entities in `expectations.json`:

```json
{
  "query_id": 4,
  "query": "Find anything related to cardiovascular health.",
  "must_include": ["hypertension", "Lisinopril", "Amlodipine"],
  "should_include": ["atrial_fibrillation", "Atorvastatin", "high_cholesterol"]
}
```

Score = `(must_include_recall * 0.7) + (should_include_recall * 0.3)`

## Hallucination Detection

Two modes:

1. **Known-entity grounding**: At startup, `list_graph_nodes` returns every entity in the knowledge graph. For each query, check which entities the answer mentions, and whether they appeared in the tool results for that specific query. An entity in the answer but not in any tool result is ungrounded.

2. **Drug name heuristic**: Catch drug-like words (common pharmaceutical suffixes: -pril, -olol, -statin, -dipine, etc.) in the answer that aren't in the known entity set at all. This catches the Phase 3 problem — the LLM guessing drug names from its training data that don't exist in our database.

## Running

```bash
# Standard processing with tracing (same interface as Phase 4)
python3 phases/phase5-observability/client.py --test
python3 phases/phase5-observability/client.py --query "Find anything related to cardiovascular health."
python3 phases/phase5-observability/client.py --workflow safety_review

# Eval scoring + hallucination detection
python3 phases/phase5-observability/run_eval.py --phase 5
python3 phases/phase5-observability/run_eval.py --phase 4 --query 4
python3 phases/phase5-observability/run_eval.py --compare
python3 phases/phase5-observability/run_eval.py --phase 5 --budget 0.10
```

## What This Proves

1. **Semantic search isn't just "seems better"** — it's measurably better. The eval framework scores both phases against the same ground truth.

2. **Cost tracking makes the Phase 3 argument concrete.** Deterministic workflows aren't just theoretically cheaper — here's the dollar amount.

3. **Hallucination detection catches the Phase 3 vs Phase 4 gap.** Phase 3 guesses drug names from training data. Phase 4's semantic search returns actual entities from the knowledge graph. The detector flags the difference automatically.

4. **Observability is part of the system, not bolted on.** The TracedClient is a drop-in replacement. Tracing and cost tracking happen during standard processing, not in a separate eval harness. Eval and hallucination detection are additional analysis tools — they use the same traces the client already produces.

## Files

| File | Purpose |
|---|---|
| `client.py` | Standard client with always-on tracing and cost tracking |
| `server.py` | MCP server (same as Phase 4 — KG + semantic search) |
| `run_eval.py` | Eval runner — scores against expectations, detects hallucinations, compares phases |
| `tracer.py` | `Span`, `Trace` dataclasses + `TracedClient` proxy |
| `cost.py` | Token pricing table + cost computation |
| `eval.py` | Entity matching scorer against `expectations.json` |
| `hallucination.py` | Compares answer entities vs tool result entities |
| `expectations.json` | Ground truth per test query (must_include, should_include) |
| `report.py` | Console report formatting for eval results |
| `graph.py` | Knowledge graph construction (same as Phase 4) |
| `embeddings.py` | Semantic index (same as Phase 4) |
| `local_tools.py` | Local tool definitions (same as Phase 4) |
| `workflows.py` | Deterministic workflows (same as Phase 4) |
