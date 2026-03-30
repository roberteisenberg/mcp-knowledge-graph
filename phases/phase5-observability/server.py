"""Phase 4: MCP Server — Knowledge Graph + Semantic Search

Builds on Phase 3 by adding:
- Semantic search via sentence-transformer embeddings over the knowledge graph
- "heart problems" finds hypertension, amlodipine, atrial_fibrillation
  without exact keyword matches

The graph bridges public FDA drug data and private clinic records
through NDC codes. The MCP tools expose traversal. Semantic search
adds conceptual discovery on top of structural traversal.
"""

import json
import sys
import os
from contextlib import asynccontextmanager

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dotenv import load_dotenv

load_dotenv()

import networkx as nx
from mcp.server.fastmcp import FastMCP
from shared.db import execute_query
from shared.fda_client import (
    lookup_drug as _fda_lookup,
    search_adverse_events as _fda_adverse,
    get_adverse_event_counts as _fda_counts,
)
from graph import build_graph, graph_stats
from embeddings import SemanticIndex, EMBEDDINGS_AVAILABLE

KG: nx.DiGraph = None
SEMANTIC: SemanticIndex = None


@asynccontextmanager
async def lifespan(server: FastMCP):
    """Build knowledge graph and semantic index on startup."""
    global KG, SEMANTIC

    KG = build_graph()
    stats = graph_stats(KG)
    print(
        f"Knowledge graph built: {stats['total_nodes']} nodes, "
        f"{stats['total_edges']} edges",
        file=sys.stderr,
    )

    SEMANTIC = SemanticIndex()
    SEMANTIC.build_from_graph(KG)
    print(
        f"Semantic index built: {len(SEMANTIC.documents)} documents, "
        f"embeddings={'real' if EMBEDDINGS_AVAILABLE else 'keyword-fallback'}",
        file=sys.stderr,
    )

    yield {}


mcp = FastMCP("clinical-intelligence", lifespan=lifespan)


# ===================================================================
# Resources (same as Phase 3 + graph stats)
# ===================================================================


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


@mcp.resource("clinic://graph/stats")
def kg_stats_resource() -> str:
    """Knowledge graph summary: node/edge counts, types, most connected nodes."""
    if KG is None:
        return json.dumps({"error": "Knowledge graph not yet built"})
    return json.dumps(graph_stats(KG), default=str)


# ===================================================================
# Clinic DB tools (same as Phase 3)
# ===================================================================


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


# ===================================================================
# FDA API tools (same as Phase 3)
# ===================================================================


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


# ===================================================================
# Knowledge Graph tools (same as Phase 3)
# ===================================================================


@mcp.tool()
def get_graph_stats() -> str:
    """Get knowledge graph statistics: node/edge counts by type, most connected nodes, centrality scores."""
    if KG is None:
        return json.dumps({"error": "Knowledge graph not yet built"})
    return json.dumps(graph_stats(KG), default=str)


@mcp.tool()
def find_path(from_node: str, to_node: str) -> str:
    """Find the shortest path between two nodes in the knowledge graph.

    Node IDs use prefixes: table:patients, drug:11788-037, patient:1,
    condition:diabetes_type2, summary:drug_usage.

    Example: find_path("table:patients", "drug:11788-037") shows how
    patient data connects to FDA drug data through the NDC bridge.
    """
    if KG is None:
        return json.dumps({"error": "Knowledge graph not yet built"})

    if from_node not in KG:
        return json.dumps({"error": f"Node '{from_node}' not found in graph"})
    if to_node not in KG:
        return json.dumps({"error": f"Node '{to_node}' not found in graph"})

    try:
        path = nx.shortest_path(KG, from_node, to_node)
        # Build detailed path with edge info
        steps = []
        for i in range(len(path) - 1):
            edge_data = KG.edges[path[i], path[i + 1]]
            node_data = KG.nodes[path[i]]
            steps.append({
                "from": path[i],
                "from_type": node_data.get("type", "unknown"),
                "to": path[i + 1],
                "edge_type": edge_data.get("type", "unknown"),
                "edge_detail": edge_data.get("via") or edge_data.get("label", ""),
            })
        return json.dumps({
            "path": path,
            "length": len(path) - 1,
            "steps": steps,
        }, default=str)
    except nx.NetworkXNoPath:
        return json.dumps({"error": f"No path between '{from_node}' and '{to_node}'"})


@mcp.tool()
def get_neighbors(node: str, depth: int = 1) -> str:
    """Get all nodes connected to a given node within N hops.

    Node IDs use prefixes: table:patients, drug:11788-037, patient:1,
    condition:diabetes_type2, summary:drug_usage.
    """
    if KG is None:
        return json.dumps({"error": "Knowledge graph not yet built"})

    if node not in KG:
        return json.dumps({"error": f"Node '{node}' not found in graph"})

    depth = min(depth, 3)  # Cap at 3 to avoid huge results

    # BFS to find neighbors within depth
    visited = set()
    current_level = {node}
    result_by_level = {}

    for d in range(1, depth + 1):
        next_level = set()
        for n in current_level:
            for neighbor in set(KG.successors(n)) | set(KG.predecessors(n)):
                if neighbor not in visited and neighbor != node:
                    next_level.add(neighbor)
        visited.update(next_level)
        if next_level:
            result_by_level[d] = [
                {
                    "node": n,
                    "type": KG.nodes[n].get("type", "unknown"),
                    "name": KG.nodes[n].get("name", n),
                }
                for n in sorted(next_level)
            ]
        current_level = next_level

    return json.dumps({
        "center": node,
        "center_type": KG.nodes[node].get("type", "unknown"),
        "depth_searched": depth,
        "neighbors_by_depth": result_by_level,
        "total_neighbors": sum(len(v) for v in result_by_level.values()),
    }, default=str)


@mcp.tool()
def suggest_join(tables: list[str]) -> str:
    """Given a list of table names, find the foreign key path between them and suggest a JOIN query.

    Example: suggest_join(["patients", "prescriptions", "doctors"])
    """
    if KG is None:
        return json.dumps({"error": "Knowledge graph not yet built"})

    table_nodes = [f"table:{t}" for t in tables]
    for tn in table_nodes:
        if tn not in KG:
            return json.dumps({"error": f"Table '{tn.replace('table:', '')}' not found"})

    if len(tables) < 2:
        return json.dumps({"error": "Need at least 2 tables"})

    # Find FK paths between consecutive table pairs
    joins = []
    for i in range(len(table_nodes) - 1):
        try:
            path = nx.shortest_path(KG, table_nodes[i], table_nodes[i + 1])
            for j in range(len(path) - 1):
                edge = KG.edges[path[j], path[j + 1]]
                if edge.get("type") == "foreign_key":
                    from_table = path[j].replace("table:", "")
                    to_table = path[j + 1].replace("table:", "")
                    col = edge.get("via", "")
                    joins.append({
                        "from_table": from_table,
                        "to_table": to_table,
                        "join_column": col,
                        "clause": f"JOIN {to_table} ON {from_table}.{col} = {to_table}.{col}",
                    })
        except nx.NetworkXNoPath:
            joins.append({
                "error": f"No FK path from {tables[i]} to {tables[i + 1]}"
            })

    # Build the full query suggestion
    if joins and all("clause" in j for j in joins):
        base = tables[0]
        join_clauses = "\n  ".join(j["clause"] for j in joins)
        sql = f"SELECT *\nFROM {base}\n  {join_clauses}"
    else:
        sql = None

    return json.dumps({
        "tables": tables,
        "joins": joins,
        "suggested_sql": sql,
    }, default=str)


@mcp.tool()
def get_drug_patient_overlap(drug_name: str) -> str:
    """Get summary statistics for a drug: how many patients are on it, conditions of those patients, interactions.

    Returns aggregate data, not individual patient records.
    """
    if KG is None:
        return json.dumps({"error": "Knowledge graph not yet built"})

    # Find the drug node
    drug_node = None
    for node, data in KG.nodes(data=True):
        if data.get("type") == "drug" and data.get("name", "").lower() == drug_name.lower():
            drug_node = node
            break

    if not drug_node:
        return json.dumps({"error": f"Drug '{drug_name}' not found in knowledge graph"})

    # Find patients prescribed this drug (via incoming 'prescribed' edges)
    patient_nodes = []
    for pred in KG.predecessors(drug_node):
        edge = KG.edges[pred, drug_node]
        if edge.get("type") == "prescribed" and KG.nodes[pred].get("type") == "patient":
            patient_nodes.append(pred)

    # Aggregate conditions of those patients
    condition_counts = {}
    for pn in patient_nodes:
        for cond in KG.nodes[pn].get("conditions", []):
            condition_counts[cond] = condition_counts.get(cond, 0) + 1

    # Find interactions for this drug
    interactions = []
    for succ in KG.successors(drug_node):
        edge = KG.edges[drug_node, succ]
        if edge.get("type") == "interacts_with":
            interactions.append({
                "other_drug": KG.nodes[succ].get("name", succ),
                "severity": edge.get("severity", "unknown"),
                "description": edge.get("description", ""),
            })

    return json.dumps({
        "drug": drug_name,
        "ndc": KG.nodes[drug_node].get("ndc"),
        "patient_count": len(patient_nodes),
        "patient_conditions": condition_counts,
        "known_interactions": interactions,
        "drug_info": {
            "pharm_class": KG.nodes[drug_node].get("pharm_class", []),
            "route": KG.nodes[drug_node].get("route", "Unknown"),
        },
    }, default=str)


@mcp.tool()
def list_graph_nodes(node_type: str = "") -> str:
    """List all nodes in the knowledge graph, optionally filtered by type.

    Types: table, drug, patient, condition, summary.
    """
    if KG is None:
        return json.dumps({"error": "Knowledge graph not yet built"})

    nodes = []
    for node, data in KG.nodes(data=True):
        if node_type and data.get("type") != node_type:
            continue
        nodes.append({
            "id": node,
            "type": data.get("type", "unknown"),
            "name": data.get("name", node),
        })

    return json.dumps({
        "count": len(nodes),
        "nodes": sorted(nodes, key=lambda n: (n["type"], n["id"])),
    }, default=str)


# ===================================================================
# Semantic search (NEW in Phase 4)
# ===================================================================


@mcp.tool()
def semantic_search(query: str, limit: int = 10) -> str:
    """Search the knowledge graph by meaning, not just keywords.

    Examples: "heart problems" finds hypertension, amlodipine, atrial_fibrillation.
    "sugar medication" finds metformin, diabetes_type2, HbA1c.
    """
    if SEMANTIC is None:
        return json.dumps({"error": "Semantic index not yet built"})

    results = SEMANTIC.search(query, limit=limit)

    return json.dumps({
        "query": query,
        "embeddings_mode": "sentence-transformers" if EMBEDDINGS_AVAILABLE else "keyword-fallback",
        "results": results,
    }, default=str)


# ===================================================================
# MCP Prompts (same as Phase 3 + semantic search step)
# ===================================================================


@mcp.prompt()
def review_patient_medications(patient_id: str) -> str:
    """Structured medication review — get prescriptions, check FDA data, assess interactions, calculate risk."""
    return f"""Perform a comprehensive medication review for Patient {patient_id}:

1. Get the patient's record using get_patient (check conditions and allergies)
2. Get their prescriptions using get_prescriptions
3. Check for known interactions using check_interactions
4. For each active medication, look up FDA information using fda_lookup_drug
5. Use semantic_search to find related clinical concepts
6. Calculate the risk score using calculate_risk_score with:
   - drug_count = number of active prescriptions
   - interaction_count = number of interactions found
   - has_allergies = whether the patient has any documented allergies
7. Format results using format_report

Your report should include:
- Patient demographics, conditions, and allergies
- Each active medication with dosage and prescriber
- FDA warnings relevant to this patient's conditions
- Any drug interactions found (with severity)
- Related concepts from semantic search
- Overall risk assessment and recommendations"""


@mcp.prompt()
def explore_drug(drug_name: str) -> str:
    """Comprehensive drug exploration — FDA data, clinic usage, adverse events, semantic connections."""
    return f"""Provide a comprehensive profile of {drug_name}:

1. Look up FDA label information using fda_lookup_drug
2. Get clinic usage statistics using get_drug_patient_overlap
3. Get the top adverse reactions using fda_adverse_event_counts
4. Use get_neighbors on the drug node to see what it connects to in our knowledge graph
5. Use semantic_search to find related concepts and drugs

Your profile should include:
- Drug classification and indications
- Key warnings from the FDA label
- How many of our patients are on this drug
- Common conditions among patients taking this drug
- Known interactions with other drugs in our system
- Most commonly reported adverse reactions
- Semantically related concepts"""


@mcp.prompt()
def analyze_data_relationships() -> str:
    """Analyze the structure of the knowledge graph — what connects to what and why it matters."""
    return """Analyze the data relationships in our clinical intelligence system:

1. Get the knowledge graph statistics using get_graph_stats
2. Identify the most connected nodes and explain why they're central
3. Use find_path to show how patient data connects to FDA drug data
   (e.g., find_path from "table:patients" to a drug node)
4. Use find_path to show how prescriptions connect to outcomes
5. List the condition nodes and explain what they link
6. Use semantic_search with a few queries to show how concepts connect beyond graph edges

Your analysis should cover:
- The overall structure (how many nodes/edges, what types)
- Which nodes are most central and why
- How private clinic data bridges to public FDA data (the NDC connection)
- The most important relationships for clinical decision-making
- How semantic search reveals connections that graph traversal alone misses"""


if __name__ == "__main__":
    mcp.run()
