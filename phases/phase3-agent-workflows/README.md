# Phase 3 — Deterministic Workflows

**MCP concept:** The same tools serve two modes — LLM-driven and deterministic. The server doesn't know or care which is calling.
**Domain concept:** Batch clinical analysis where reliability and cost matter more than dynamism.

## Two Ways to Use MCP Tools

Phases 1 and 2 are **LLM-driven**: the human asks a question, Claude decides which tools to call, in what order, with what arguments. This is powerful for open-ended exploration but has tradeoffs — the LLM might call the wrong tool, guess wrong arguments, or take an expensive path through 14 tool calls when 5 would do.

Phase 3 adds **deterministic workflows**: Python decides which tools to call. The execution path is hardcoded. The LLM is only invoked when reasoning is genuinely needed.

```
LLM-driven (Phases 1-2):            Deterministic (Phase 3):
  Human ─► Claude ─► decides           Python ─► calls tools directly
              │       which tools           │
           reasons about                 if reasoning needed:
              │       every step            │
           answer                        Python ─► Claude (just this part)
                                            │
                                         format results
```

The MCP server is unchanged — it doesn't know or care who's calling. That's the point.

## The Spectrum

There are three levels of orchestration rigidity. This tutorial shows the two extremes; the [LangGraph repo](https://github.com/roberteisenberg/langgraph) shows the middle.

| | LLM-driven (Phases 1, 2, 4) | LangGraph (other repo) | Hardcoded Python (Phase 3) |
|---|---|---|---|
| Who picks the next tool | The LLM | State machine with conditional edges | Hardcoded sequence |
| Flexibility | Full — handles novel questions | Some — conditional paths, branching | None — steps are fixed |
| Predictability | Low — different path each run | High — deterministic routing | Highest — same path every time |
| Hallucination in orchestration | LLM might call wrong tool | None — graph routes | None — sequence is code |
| Checkpoints / recovery | No | Yes — resume from failure | No |
| Human-in-the-loop | No | Built-in | No |
| When to use | Open-ended exploration | Known workflow with branching, audit, recovery | Known workflow, simple, no branching |

Phase 3 is the most rigid option — more rigid than even LangGraph. It only works when the steps are known in advance and simple enough that you don't need conditional routing, checkpoints, or human review. For those cases, plain Python is enough. You don't need a framework.

LangGraph adds value when the workflow has branching logic, needs to recover from failures, or requires human approval at certain steps. Phase 3 is for when it doesn't.

## The Pattern

Every workflow follows the same structure:

1. **Gather data** — MCP tool calls (deterministic, cheap, no LLM)
2. **Analyze** — Claude (LLM reasoning, expensive, only when needed)
3. **Format** — local tool (deterministic, zero cost)

The safety review workflow: 30 MCP calls (cheap) + 9 Claude calls (only for flagged patients). If this were fully interactive, Claude would reason about every step — which patients to check, which tools to use, what order. Same result, more tokens, less predictable.

## Workflows

### `safety_review` — Medication Safety Review

Checks ALL patients for drug interaction risks.

| Step | What | How | LLM? |
|------|------|-----|------|
| 1 | Find patients with 2+ active prescriptions | `run_query` (SQL) | No |
| 2 | Check interactions for each patient | `check_interactions` per patient | No |
| 3 | Get patient details for flagged cases | `get_patient`, `get_prescriptions` | No |
| 4 | Assess clinical significance | Claude (per flagged patient) | Yes |
| 5 | Calculate risk scores | `calculate_risk_score` (local) | No |
| 6 | Format report | `format_report` (local) | No |

With 12 patients: ~30 MCP calls (cheap) + 9 Claude calls (only for flagged patients).

### `drug_utilization` — Drug Utilization Report

Analyzes prescribing patterns across the clinic.

| Step | What | How | LLM? |
|------|------|-----|------|
| 1 | Get prescription stats per drug | `run_query` (SQL) | No |
| 2 | Get KG overlap data per drug | `get_drug_patient_overlap` | No |
| 3 | Get FDA adverse event profiles | `fda_adverse_event_counts` | No |
| 4 | Synthesize findings | Claude (one call for whole report) | Yes |
| 5 | Format report | `format_report` (local) | No |

~18 MCP calls + 1 Claude call.

### `cohort_comparison` — Patient Cohort Comparison

Compares diabetes vs hypertension patient cohorts.

| Step | What | How | LLM? |
|------|------|-----|------|
| 1 | Find patients per condition | `get_neighbors` (KG traversal) | No |
| 2 | Get prescriptions per cohort | `get_prescriptions` per patient | No |
| 3 | Compare cohorts | Claude (one call) | Yes |
| 4 | Format report | `format_report` (local) | No |

Uses the knowledge graph directly — condition nodes link to patient nodes.

## Running

```bash
# Run a workflow
python3 phases/phase3-agent-workflows/client.py --workflow safety_review
python3 phases/phase3-agent-workflows/client.py --workflow drug_utilization
python3 phases/phase3-agent-workflows/client.py --workflow cohort_comparison

# Interactive mode still works (both modes, same tools)
python3 phases/phase3-agent-workflows/client.py
python3 phases/phase3-agent-workflows/client.py --query "your question"

# MCP prompts
python3 phases/phase3-agent-workflows/client.py --prompt explore_drug --args '{"drug_name": "Metformin"}'
```

## What This Proves

MCP tools are infrastructure — they don't care who's calling. The same `check_interactions` tool serves an interactive conversation in Phase 2 and a batch safety review in Phase 3. The choice between LLM-driven, LangGraph, and hardcoded Python isn't about the tools — it's about the orchestration layer.

Phase 3 is one end of the spectrum: maximum reliability, minimum flexibility. The [LangGraph repo](https://github.com/roberteisenberg/langgraph) shows the middle — deterministic routing with conditional branching, checkpoints, and human-in-the-loop. Phases 1, 2, and 4 show the other end — full LLM autonomy.

Both extremes coexist in the same client. You can run `--workflow safety_review` for the batch job and type a freeform question in interactive mode, hitting the same MCP server.
