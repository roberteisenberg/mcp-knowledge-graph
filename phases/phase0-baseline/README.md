# Phase 0 — Baseline

**MCP concept:** None. This is the "before."

## What This Is

A single Python app with hardcoded tool functions. Claude calls them through the Anthropic SDK's native tool_use. Everything lives in one place:

- Clinic DB queries (private patient data) — via psycopg2
- FDA API calls (public drug data) — via httpx
- Report formatting (app logic) — plain Python

There are no boundaries between these. The DB connection string, the patient data, the FDA calls, and the formatting logic all coexist in `tools.py`.

## Tools

| Tool | Source | What it does |
|------|--------|-------------|
| `list_tables` | Clinic DB | Lists all tables with row counts |
| `describe_table` | Clinic DB | Columns, types, foreign keys |
| `run_query` | Clinic DB | Execute arbitrary SELECT |
| `get_patient` | Clinic DB | Patient record with conditions/allergies |
| `get_prescriptions` | Clinic DB | Patient's prescriptions with doctor names |
| `check_interactions` | Clinic DB | Drug interactions from clinic's curated table |
| `fda_lookup_drug` | FDA API | Drug label info (indications, warnings) |
| `fda_adverse_events` | FDA API | Individual adverse event case reports |
| `fda_adverse_event_counts` | FDA API | Top reported reactions for a drug |
| `format_report` | Local | Format findings into a report |

## Running

```bash
# Start the database
docker-compose up -d

# Install dependencies
pip install -r requirements.txt

# Copy and fill in your API key
cp .env.example .env

# Interactive mode
python3 phases/phase0-baseline/main.py

# Run all 6 test queries
python3 phases/phase0-baseline/main.py --test

# Single query
python3 phases/phase0-baseline/main.py --query "What data do we have?"
```

## What This Proves

It works. Claude can query the clinic database and the FDA API to answer clinical questions.

But:
- Everything is in one script. No boundaries between data access and app logic.
- The DB connection string lives in the app. Every developer sees it.
- A second app that needs clinic data has to reimplement all the tools.
- Adding a new data source means editing this code.

Phase 1 fixes the architecture by extracting data access into an MCP server. The LLM behavior doesn't change — Phase 1 is a separation of concerns, not a capability change. The hallucination and cost improvements start in Phase 2.
