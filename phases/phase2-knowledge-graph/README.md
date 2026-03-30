# Phase 2 — Knowledge Graph

**MCP concept:** `@mcp.prompt()` (reusable prompt templates), graph traversal tools.
**Architecture concept:** Deterministic answers from graph structure — no LLM reasoning needed for structural questions.

## What Changed from Phase 1

Phase 1 separated data access into an MCP server. Phase 2 adds a knowledge graph built from both data sources and MCP prompts for structured workflows:

```
Phase 1:                              Phase 2:
┌──────────────┐  ┌────────────────┐  ┌──────────────┐  ┌─────────────────────────┐
│ client.py    │  │ server.py      │  │ client.py    │  │ server.py               │
│  - Local     │──│  - DB tools    │  │  - Local     │──│  - DB tools             │
│    tools     │  │  - FDA tools   │  │    tools     │  │  - FDA tools            │
│  - Claude    │  │  - Resources   │  │  - Claude    │  │  - Resources            │
│    loop      │  │                │  │    loop      │  │  + KG tools (NEW)       │
└──────────────┘  └────────────────┘  │  + Prompts   │  │  + Prompts (NEW)        │
                                      └──────────────┘  │  + graph.py (NEW)       │
                                                        └─────────────────────────┘
```

## The Knowledge Graph

Built on server startup from both data sources using NetworkX:

```
Patient nodes (private)          Drug nodes (public/FDA)
  patient:1 ──prescribed──────── drug:11788-037 (Metformin)
  patient:1 ──prescribed──────── drug:68001-335 (Lisinopril)
         │                              │
    has_condition              interacts_with (mild)
         │                              │
  condition:diabetes_type2       drug:68001-335 (Lisinopril)
  condition:hypertension                │
                                   ndc_bridge
                                        │
                               table:prescriptions ──fk── table:patients
                                                    ──fk── table:doctors
```

**34 nodes** (7 tables, 6 drugs, 12 patients, 6 conditions, 3 summaries) connected by **87 edges**.

The NDC code is the bridge — `prescriptions.drug_ndc` links clinic records to FDA drug data. The graph makes this connection traversable.

## New MCP Tools

| Tool | What it does |
|------|-------------|
| `get_graph_stats` | Node/edge counts by type, centrality scores, most connected nodes |
| `find_path` | Shortest path between two nodes (e.g., patient:1 → drug:11788-037) |
| `get_neighbors` | All connected nodes within N hops |
| `suggest_join` | FK path between tables → generates JOIN SQL |
| `get_drug_patient_overlap` | How many patients take a drug, their conditions, interactions |
| `list_graph_nodes` | List nodes by type (table, drug, patient, condition, summary) |

## MCP Prompts

Prompts are reusable templates served by the MCP server. They guide the LLM through structured analysis patterns.

| Prompt | What it does |
|--------|-------------|
| `review_patient_medications` | Patient record → prescriptions → FDA lookup → interactions → risk score → report |
| `explore_drug` | FDA data → clinic usage → adverse events → graph neighbors |
| `analyze_data_relationships` | Graph stats → centrality analysis → path finding → relationship assessment |

## Running

```bash
# Start the database (if not already running)
docker-compose up -d

# Install dependencies (adds networkx)
pip install -r requirements.txt

# Interactive mode
python3 phases/phase2-knowledge-graph/client.py

# Run all 6 test queries
python3 phases/phase2-knowledge-graph/client.py --test

# Single query
python3 phases/phase2-knowledge-graph/client.py --query "How does patient data connect to FDA drug data?"

# Run an MCP prompt
python3 phases/phase2-knowledge-graph/client.py --prompt explore_drug --args '{"drug_name": "Metformin"}'
python3 phases/phase2-knowledge-graph/client.py --prompt review_patient_medications --args '{"patient_id": "1"}'
python3 phases/phase2-knowledge-graph/client.py --prompt analyze_data_relationships
```

## What This Proves

The knowledge graph gives the LLM **deterministic answers for structural questions**. `find_path("patient:1", "drug:11788-037")` doesn't need LLM reasoning — it's a graph traversal that returns a precise path. `suggest_join(["patients", "prescriptions"])` generates SQL from FK edges — no guessing column names. `get_drug_patient_overlap("Metformin")` returns "6 patients, 83% also have hypertension" from graph aggregation.

These are questions the LLM would otherwise answer by writing speculative SQL queries, guessing at table relationships, and hoping the results make sense. The knowledge graph replaces that guesswork with structure.

Compared to Phase 1:
- **Same data sources, richer answers** — graph traversal reveals connections the LLM can reason about
- **6 new MCP tools** for graph traversal (16 total, up from 10)
- **3 MCP prompts** for structured workflows
- **Graph stats as a resource** — injected into system prompt on startup
- **NDC bridge is explicit** — the graph makes the public/private data connection traversable
