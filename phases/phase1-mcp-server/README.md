# Phase 1 — MCP Server

**MCP concept:** FastMCP, `@mcp.tool()`, `@mcp.resource()`, stdio transport, automatic tool discovery.
**Architecture concept:** Separate data access from app logic. The client never sees a connection string.

## What Changed from Phase 0

Phase 0 hardcoded everything in one script. Phase 1 extracts data access into an MCP server:

```
Phase 0:                              Phase 1:
┌─────────────────────┐               ┌──────────────┐     ┌───────────────────┐
│ main.py             │               │ client.py    │     │ server.py (MCP)   │
│  - DB tools         │    ──►        │  - Local     │────►│  - DB tools       │
│  - FDA tools        │               │    tools     │     │  - FDA tools      │
│  - Format tools     │               │  - Claude    │     │  - Resources      │
│  - Claude loop      │               │    loop      │     │                   │
└─────────────────────┘               └──────────────┘     └───────────────────┘
                                       No DB string!        Has DB connection
                                       No API details!      Has FDA API access
```

The client discovers tools at runtime — it never sees a database connection string or API URL.

## Architecture

**MCP Server** (`server.py`) — exposes tools and resources via stdio transport:

| Type | Name | What it does |
|------|------|-------------|
| Resource | `clinic://tables` | Lists all tables with row counts (loaded at startup) |
| Resource | `clinic://summary/prescriptions` | Drug prescription statistics |
| Tool | `describe_table` | Column details and foreign keys |
| Tool | `run_query` | Execute arbitrary SELECT |
| Tool | `get_patient` | Patient record with conditions/allergies |
| Tool | `get_prescriptions` | Patient's prescriptions with doctor names |
| Tool | `check_interactions` | Drug interactions from clinic's curated table |
| Tool | `fda_lookup_drug` | FDA drug label info |
| Tool | `fda_adverse_events` | Individual adverse event case reports |
| Tool | `fda_adverse_event_counts` | Top reported reactions for a drug |

**Local tools** (`local_tools.py`) — stay in the app, not on the server:

| Tool | Why it's local |
|------|---------------|
| `format_report` | App-specific formatting, no data access |
| `calculate_risk_score` | Pure computation on already-retrieved data |

**Client** (`client.py`):
1. Starts MCP server as subprocess (stdio transport)
2. Discovers tools → converts to Anthropic format
3. Reads resources → injects into system prompt as context
4. Registers local tools alongside MCP tools
5. Runs the same Claude tool-calling loop — Claude sees all tools uniformly

## Resources vs Tools

This is the key MCP concept introduced in Phase 1:

- **Resources** = reference data, loaded at startup, provide context. The client reads `clinic://tables` and injects it into the system prompt so Claude knows the schema before the user asks anything.
- **Tools** = actions, called during conversation. Claude decides when to call `get_patient` or `fda_lookup_drug` based on the user's question.

## Running

```bash
# Start the database (if not already running)
docker-compose up -d

# Install dependencies (adds mcp package)
pip install -r requirements.txt

# Interactive mode
python3 phases/phase1-mcp-server/client.py

# Run all 6 test queries
python3 phases/phase1-mcp-server/client.py --test

# Single query
python3 phases/phase1-mcp-server/client.py --query "What data do we have?"
```

## What This Proves

The clinic data and FDA access are now behind an MCP boundary. The client doesn't have a database connection string or API details. It discovers and calls tools. But formatting and computation stay local — they don't need MCP because they're app-specific logic with no data access.

**This is an architecture change, not a capability change.** The LLM has the same tools and produces the same answers as Phase 0. The cost and hallucination profile are the same. What's different:

- **Separation of concerns** — data access is behind a server boundary
- **Tool discovery** — client learns what tools exist at runtime, doesn't hardcode them
- **Resources** — schema information loaded at startup and injected into the system prompt
- **Local tools coexist** — `format_report` and `calculate_risk_score` live in the app alongside MCP tools
- **Reusability** — a second app can connect to the same MCP server without reimplementing tools

The hallucination and cost improvements start in Phase 2, when the knowledge graph gives the LLM deterministic answers for structural questions it would otherwise have to guess at.
