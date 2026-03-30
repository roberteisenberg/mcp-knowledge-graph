"""Phase 0: All tools hardcoded in one file.

This is the "before" — FDA API calls, clinic DB queries, and formatting
all live in the same place. No MCP, no boundaries, no separation.
"""

import json
import sys
import os

# Add shared modules to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.db import execute_query
from shared.fda_client import lookup_drug as _fda_lookup, search_adverse_events as _fda_adverse, get_adverse_event_counts as _fda_counts


# --- Clinic DB tools (private data, no access control) ---

def list_tables() -> str:
    """List all tables in the clinic database with row counts."""
    rows = execute_query("""
        SELECT
            t.table_name,
            (SELECT COUNT(*) FROM information_schema.columns c
             WHERE c.table_name = t.table_name AND c.table_schema = 'public') as column_count
        FROM information_schema.tables t
        WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE'
        ORDER BY t.table_name
    """)
    # Get row counts separately (information_schema doesn't have them)
    for row in rows:
        count = execute_query(f"SELECT COUNT(*) as cnt FROM {row['table_name']}")
        row["row_count"] = count[0]["cnt"]
    return json.dumps(rows, default=str)


def describe_table(table_name: str) -> str:
    """Describe a table's columns, types, and constraints."""
    columns = execute_query("""
        SELECT
            c.column_name, c.data_type, c.is_nullable, c.column_default,
            c.character_maximum_length
        FROM information_schema.columns c
        WHERE c.table_schema = 'public' AND c.table_name = %s
        ORDER BY c.ordinal_position
    """, (table_name,))

    # Get foreign keys
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


def run_query(sql: str) -> str:
    """Execute a SELECT query against the clinic database."""
    if not sql.strip().upper().startswith("SELECT"):
        return json.dumps({"error": "Only SELECT queries are allowed"})
    rows = execute_query(sql)
    return json.dumps(rows[:50], default=str)  # Limit to 50 rows


def get_patient(patient_id: int) -> str:
    """Get a patient's full record including conditions and allergies."""
    rows = execute_query(
        "SELECT * FROM patients WHERE patient_id = %s", (patient_id,)
    )
    if not rows:
        return json.dumps({"error": f"Patient {patient_id} not found"})
    return json.dumps(rows[0], default=str)


def get_prescriptions(patient_id: int) -> str:
    """Get all prescriptions for a patient."""
    rows = execute_query("""
        SELECT p.*, d.first_name || ' ' || d.last_name as doctor_name
        FROM prescriptions p
        JOIN doctors d ON p.doctor_id = d.doctor_id
        WHERE p.patient_id = %s
        ORDER BY p.start_date DESC
    """, (patient_id,))
    return json.dumps(rows, default=str)


def check_interactions(patient_id: int) -> str:
    """Check for known drug interactions among a patient's active prescriptions."""
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

def fda_lookup_drug(drug_name: str) -> str:
    """Look up a drug in the FDA database by name."""
    result = _fda_lookup(drug_name)
    if result:
        return json.dumps(result, default=str)
    return json.dumps({"error": f"Drug '{drug_name}' not found in FDA database"})


def fda_adverse_events(drug_name: str, limit: int = 5) -> str:
    """Search FDA adverse event reports for a drug."""
    events = _fda_adverse(drug_name, limit)
    if events:
        return json.dumps(events, default=str)
    return json.dumps({"message": f"No adverse events found for '{drug_name}'"})


def fda_adverse_event_counts(drug_name: str) -> str:
    """Get the most common adverse reactions reported for a drug."""
    result = _fda_counts(drug_name)
    if result:
        return json.dumps(result, default=str)
    return json.dumps({"message": f"No adverse event data found for '{drug_name}'"})


# --- Local tools (app-specific) ---

def format_report(title: str, sections: list[str]) -> str:
    """Format findings into a readable report."""
    lines = [f"# {title}", ""]
    for i, section in enumerate(sections, 1):
        lines.append(f"## Section {i}")
        lines.append(section)
        lines.append("")
    return "\n".join(lines)


# --- Tool registry for Claude ---

TOOLS = [
    {
        "name": "list_tables",
        "description": "List all tables in the clinic database with column counts and row counts.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "describe_table",
        "description": "Describe a table's columns, data types, constraints, and foreign keys.",
        "input_schema": {
            "type": "object",
            "properties": {"table_name": {"type": "string", "description": "Name of the table to describe"}},
            "required": ["table_name"],
        },
    },
    {
        "name": "run_query",
        "description": "Execute a SELECT query against the clinic database. Returns up to 50 rows.",
        "input_schema": {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "SQL SELECT query to execute"}},
            "required": ["sql"],
        },
    },
    {
        "name": "get_patient",
        "description": "Get a patient's full record including demographics, conditions, and allergies.",
        "input_schema": {
            "type": "object",
            "properties": {"patient_id": {"type": "integer", "description": "Patient ID"}},
            "required": ["patient_id"],
        },
    },
    {
        "name": "get_prescriptions",
        "description": "Get all prescriptions for a patient, including the prescribing doctor's name.",
        "input_schema": {
            "type": "object",
            "properties": {"patient_id": {"type": "integer", "description": "Patient ID"}},
            "required": ["patient_id"],
        },
    },
    {
        "name": "check_interactions",
        "description": "Check for known drug interactions among a patient's active prescriptions using the clinic's curated interaction database.",
        "input_schema": {
            "type": "object",
            "properties": {"patient_id": {"type": "integer", "description": "Patient ID"}},
            "required": ["patient_id"],
        },
    },
    {
        "name": "fda_lookup_drug",
        "description": "Look up a drug in the FDA openFDA database. Returns label information including indications, warnings, and known interactions.",
        "input_schema": {
            "type": "object",
            "properties": {"drug_name": {"type": "string", "description": "Drug name to look up"}},
            "required": ["drug_name"],
        },
    },
    {
        "name": "fda_adverse_events",
        "description": "Search FDA adverse event reports (FAERS) for a specific drug. Returns individual case reports.",
        "input_schema": {
            "type": "object",
            "properties": {
                "drug_name": {"type": "string", "description": "Drug name to search"},
                "limit": {"type": "integer", "description": "Max reports to return (default 5)", "default": 5},
            },
            "required": ["drug_name"],
        },
    },
    {
        "name": "fda_adverse_event_counts",
        "description": "Get the top 10 most commonly reported adverse reactions for a drug from FDA data.",
        "input_schema": {
            "type": "object",
            "properties": {"drug_name": {"type": "string", "description": "Drug name"}},
            "required": ["drug_name"],
        },
    },
    {
        "name": "format_report",
        "description": "Format findings into a structured report with a title and sections.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Report title"},
                "sections": {"type": "array", "items": {"type": "string"}, "description": "Report sections"},
            },
            "required": ["title", "sections"],
        },
    },
]

# Map tool names to functions
TOOL_FUNCTIONS = {
    "list_tables": lambda **kwargs: list_tables(),
    "describe_table": lambda **kwargs: describe_table(kwargs["table_name"]),
    "run_query": lambda **kwargs: run_query(kwargs["sql"]),
    "get_patient": lambda **kwargs: get_patient(kwargs["patient_id"]),
    "get_prescriptions": lambda **kwargs: get_prescriptions(kwargs["patient_id"]),
    "check_interactions": lambda **kwargs: check_interactions(kwargs["patient_id"]),
    "fda_lookup_drug": lambda **kwargs: fda_lookup_drug(kwargs["drug_name"]),
    "fda_adverse_events": lambda **kwargs: fda_adverse_events(kwargs["drug_name"], kwargs.get("limit", 5)),
    "fda_adverse_event_counts": lambda **kwargs: fda_adverse_event_counts(kwargs["drug_name"]),
    "format_report": lambda **kwargs: format_report(kwargs["title"], kwargs["sections"]),
}
