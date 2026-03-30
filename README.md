# MCP Knowledge Graph

A progressive tutorial that builds a clinical intelligence tool using MCP (Model Context Protocol), demonstrating how to reduce LLM hallucinations and cost by moving work from the LLM into infrastructure.

## The Thesis

Two problems define LLM application development:

1. **Hallucinations** — the LLM guesses when it should look up
2. **Cost** — the LLM reasons when it should just execute

Every phase of this tutorial adds infrastructure that takes work away from the LLM. The LLM doesn't get dumber — it gets a narrower, more appropriate job.

| Phase | What it adds | Hallucination reduction | Cost reduction |
|---|---|---|---|
| [Phase 0](phases/phase0-baseline/) | Baseline — all tools hardcoded | — | — |
| [Phase 1](phases/phase1-mcp-server/) | MCP server, resources, tool discovery | Same tools, same behavior — this is an architecture change, not a capability change. Resources give minor upfront context. | Same |
| [Phase 2](phases/phase2-knowledge-graph/) | Knowledge graph, graph traversal, MCP prompts | `find_path` and `suggest_join` give deterministic answers — no speculative SQL | Graph tools replace multi-step LLM reasoning |
| [Phase 3](phases/phase3-agent-workflows/) | Deterministic workflows | Python drives the tool calls — zero hallucination in orchestration | 30 MCP calls + 9 Claude calls vs. fully interactive |
| [Phase 4](phases/phase4-semantic/) | Semantic search | Discovery grounded in actual data — no hallucinated entities | First call returns ranked results vs. trial-and-error |
| [Phase 5](phases/phase5-observability/) | Tracing, cost tracking, eval | Measure hallucinations instead of eyeballing. Prove Phase 3 is cheaper. | Know what every query costs. Set budget limits. |

## What It Builds

A clinical intelligence tool that connects a private clinic database (patients, prescriptions, drug interactions) to public FDA data (drug labels, adverse events) through a knowledge graph. The same six test queries run against each phase, showing how the answers and architecture improve.

**Data sources:**
- PostgreSQL clinic database (12 patients, 6 doctors, prescriptions, outcomes, drug interactions)
- FDA openFDA API (drug labels, adverse event reports)
- NetworkX knowledge graph (34 nodes, 87 edges, built on startup from both sources)
- Sentence-transformer embeddings (semantic index over the knowledge graph)

## Phase Progression

### Phase 0 — Baseline
One script, all tools hardcoded. Claude calls them through the Anthropic SDK. No boundaries between data access and app logic. The most expensive and least reliable architecture.

### Phase 1 — MCP Server
Data access extracted into a FastMCP server. The client discovers tools at runtime, reads resources into the system prompt, and never sees a connection string. Resources give the LLM context upfront — it knows the schema before the user asks anything.

### Phase 2 — Knowledge Graph
A NetworkX graph built on startup from both data sources. The NDC (National Drug Code) bridges clinic prescriptions to FDA drug data. Graph traversal tools (`find_path`, `get_neighbors`, `suggest_join`) give deterministic answers for structural questions — no LLM reasoning needed. MCP prompts guide the LLM through structured analysis patterns.

### Phase 3 — Deterministic Workflows
The same MCP tools serve two modes: **LLM-driven** (Claude decides which tools to call) and **deterministic** (Python decides). Workflows hardcode the tool call sequence and only invoke Claude when reasoning is genuinely needed. The safety review processes 12 patients with ~30 MCP calls and only 9 Claude calls.

### Phase 4 — Semantic Search
Sentence-transformer embeddings over the knowledge graph. `semantic_search("heart problems")` returns hypertension, amlodipine, atrial fibrillation — ranked by relevance, grounded in actual data. Without semantic search, the LLM has to guess entity names from its training data. [The Phase 3 vs Phase 4 comparison](phases/phase4-semantic/README.md#phase-3-vs-phase-4-same-query-different-approach) shows this concretely: Phase 3 guessed 6 drugs that don't exist in the database.

### Phase 5 — Observability
Instrument every LLM call and tool call with tracing. Track token cost per query — prove that Phase 3's deterministic workflows are 58% cheaper than interactive. Evaluate outputs against ground truth: do the 6 test queries return the right patients, drugs, and conditions? Detect hallucinations by comparing the final answer against what the tools actually returned.

## The Orchestration Spectrum

How much control do you give the LLM? This repo and a [LangGraph repo](https://github.com/roberteisenberg/langgraph) show three points on the spectrum.

| | LLM-driven (this repo, Phases 1/2/4) | LangGraph (other repo) | Hardcoded Python (this repo, Phase 3) |
|---|---|---|---|
| Who decides the workflow | The LLM | State machine with conditional edges | Hardcoded sequence |
| Flexibility | Full — handles novel questions | Some — conditional paths, branching | None — steps are fixed |
| Predictability | Low — different path each run | High — deterministic routing | Highest — same path every time |
| Hallucination in orchestration | LLM might call wrong tool, wrong args | None — graph routes | None — sequence is code |
| Checkpoints / recovery | No | Yes — resume from failure | No |
| Human-in-the-loop | No | Built-in | No |
| Best for | Exploration, open-ended questions | Known workflows needing branching, audit, recovery | Known workflows, simple, no branching |

**LLM-driven** (most of this repo): The LLM has all tools and decides what to call. Powerful for open-ended questions like "find anything related to cardiovascular health." The tradeoff is cost and unpredictability — the LLM may take 14 tool calls when 5 would do.

**LangGraph** (other repo): A state machine routes work between specialized agents. Each agent has limited tools. The graph determines what happens next. Good for repeatable workflows that need auditability, checkpoints, and human-in-the-loop.

**Hardcoded Python** (Phase 3): The most rigid option — more rigid than LangGraph. Plain Python calls tools in a fixed sequence. The LLM is only invoked for reasoning. This works when the task is simple enough that you don't need conditional routing, recovery, or human review. For those cases, a framework is overhead.

**In practice, production systems use multiple points on this spectrum.** A LangGraph pipeline might have one node that does free reasoning with MCP tools and routes the result into a deterministic downstream step. This repo's Phase 3 shows the same idea without the framework — and both coexist in the same client, hitting the same MCP server.

## Running

```bash
# Start the database
docker-compose up -d

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env

# Run any phase
python3 phases/phase0-baseline/main.py --test
python3 phases/phase1-mcp-server/client.py --test
python3 phases/phase2-knowledge-graph/client.py --test
python3 phases/phase3-agent-workflows/client.py --workflow safety_review
python3 phases/phase4-semantic/client.py --query "Find anything related to cardiovascular health."
python3 phases/phase5-observability/run_eval.py --phase 4
```

## Tech Stack

- **Claude** (Anthropic SDK) — LLM reasoning and tool calling
- **MCP** (FastMCP) — server/client protocol for tool discovery and execution
- **NetworkX** — knowledge graph construction and traversal
- **sentence-transformers** (all-MiniLM-L6-v2) — semantic embeddings with keyword fallback
- **PostgreSQL** — clinic database (Docker)
- **httpx** — FDA openFDA API client
