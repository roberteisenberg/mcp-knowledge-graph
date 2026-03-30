"""Phase 1: MCP Server — clinical-intelligence

Data access (clinic DB + FDA API) extracted into an MCP server.
The server exposes tools and resources via the MCP protocol.
The client discovers and calls them — it doesn't have a DB connection
string or API details.

This is the "Web API for LLMs" — endpoints that Claude can discover
and invoke through a standardized protocol.

Run directly to test:
    python server.py

In production, the client starts this as a subprocess (stdio transport).
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dotenv import load_dotenv

load_dotenv()

from mcp.server.fastmcp import FastMCP
from shared.db import execute_query
from shared.fda_client import (
    lookup_drug as _fda_lookup,
    search_adverse_events as _fda_adverse,
    get_adverse_event_counts as _fda_counts,
)

mcp = FastMCP("clinical-intelligence")


# --- Resources (browsable, read-only context) ---
# Resources provide reference data that the client reads on startup.
# They're "here's what we have" — not actions the LLM calls mid-conversation.


@mcp.resource("clinic://tables")
def list_tables() -> str:
    """List all tables in the clinic database with column counts and row counts."""
    rows = execute_query("""
        SELECT
            t.table_name,
            (SELECT COUNT(*) FROM information_schema.columns c
             WHERE c.table_name = t.table_name AND c.table_schema = 'public') as column_count
        FROM information_schema.tables t
        WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE'
        ORDER BY t.table_name
    """)
    for row in rows:
        count = execute_query(f"SELECT COUNT(*) as cnt FROM {row['table_name']}")
        row["row_count"] = count[0]["cnt"]
    return json.dumps(rows, default=str)


@mcp.resource("clinic://summary/prescriptions")
def prescription_summary() -> str:
    """Summary statistics about prescriptions — drug counts, active vs completed."""
    rows = execute_query("""
        SELECT
            drug_name,
            COUNT(*) as total_prescriptions,
            COUNT(*) FILTER (WHERE status = 'active') as active,
            COUNT(*) FILTER (WHERE status = 'completed') as completed,
            COUNT(*) FILTER (WHERE status = 'discontinued') as discontinued,
            COUNT(DISTINCT patient_id) as unique_patients
        FROM prescriptions
        GROUP BY drug_name
        ORDER BY total_prescriptions DESC
    """)
    return json.dumps(rows, default=str)


# --- Clinic DB tools (private data) ---
# These are actions the LLM calls during conversation.


@mcp.tool()
def describe_table(table_name: str) -> str:
    """Describe a table's columns, data types, constraints, and foreign keys."""
    columns = execute_query("""
        SELECT
            c.column_name, c.data_type, c.is_nullable, c.column_default,
            c.character_maximum_length
        FROM information_schema.columns c
        WHERE c.table_schema = 'public' AND c.table_name = %s
        ORDER BY c.ordinal_position
    """, (table_name,))

    fks = execute_query("""
        SELECT
            kcu.column_name,
            ccu.table_name AS references_table,
            ccu.column_name AS references_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name = %s
    """, (table_name,))

    return json.dumps({"table": table_name, "columns": columns, "foreign_keys": fks}, default=str)


@mcp.tool()
def run_query(sql: str) -> str:
    """Execute a SELECT query against the clinic database. Returns up to 50 rows."""
    if not sql.strip().upper().startswith("SELECT"):
        return json.dumps({"error": "Only SELECT queries are allowed"})
    rows = execute_query(sql)
    return json.dumps(rows[:50], default=str)


@mcp.tool()
def get_patient(patient_id: int) -> str:
    """Get a patient's full record including demographics, conditions, and allergies."""
    rows = execute_query(
        "SELECT * FROM patients WHERE patient_id = %s", (patient_id,)
    )
    if not rows:
        return json.dumps({"error": f"Patient {patient_id} not found"})
    return json.dumps(rows[0], default=str)


@mcp.tool()
def get_prescriptions(patient_id: int) -> str:
    """Get all prescriptions for a patient, including the prescribing doctor's name."""
    rows = execute_query("""
        SELECT p.*, d.first_name || ' ' || d.last_name as doctor_name
        FROM prescriptions p
        JOIN doctors d ON p.doctor_id = d.doctor_id
        WHERE p.patient_id = %s
        ORDER BY p.start_date DESC
    """, (patient_id,))
    return json.dumps(rows, default=str)


@mcp.tool()
def check_interactions(patient_id: int) -> str:
    """Check for known drug interactions among a patient's active prescriptions using the clinic's curated interaction database."""
    rows = execute_query("""
        SELECT di.*
        FROM drug_interactions di
        WHERE EXISTS (
            SELECT 1 FROM prescriptions p1
            WHERE p1.patient_id = %s AND p1.status = 'active'
            AND p1.drug_ndc = di.drug_a_ndc
        )
        AND EXISTS (
            SELECT 1 FROM prescriptions p2
            WHERE p2.patient_id = %s AND p2.status = 'active'
            AND p2.drug_ndc = di.drug_b_ndc
        )
    """, (patient_id, patient_id))
    return json.dumps(rows, default=str)


# --- FDA API tools (public data) ---


@mcp.tool()
def fda_lookup_drug(drug_name: str) -> str:
    """Look up a drug in the FDA openFDA database. Returns label information including indications, warnings, and known interactions."""
    result = _fda_lookup(drug_name)
    if result:
        return json.dumps(result, default=str)
    return json.dumps({"error": f"Drug '{drug_name}' not found in FDA database"})


@mcp.tool()
def fda_adverse_events(drug_name: str, limit: int = 5) -> str:
    """Search FDA adverse event reports (FAERS) for a specific drug. Returns individual case reports."""
    events = _fda_adverse(drug_name, limit)
    if events:
        return json.dumps(events, default=str)
    return json.dumps({"message": f"No adverse events found for '{drug_name}'"})


@mcp.tool()
def fda_adverse_event_counts(drug_name: str) -> str:
    """Get the top 10 most commonly reported adverse reactions for a drug from FDA data."""
    result = _fda_counts(drug_name)
    if result:
        return json.dumps(result, default=str)
    return json.dumps({"message": f"No adverse event data found for '{drug_name}'"})


if __name__ == "__main__":
    mcp.run()
