"""Phase 2: Knowledge Graph construction.

Builds a NetworkX directed graph from both data sources:
- Private nodes: clinic DB tables, patients, prescriptions
- Public nodes: FDA drugs (keyed by NDC)
- Bridge edges: prescriptions → drugs via NDC
- Interaction edges: drug pairs from clinic's curated table + FDA data
- Condition nodes: patient conditions linked to patients and related drugs
- Summary nodes: aggregated statistics

The graph is a data structure — it doesn't enforce security.
The MCP tools that expose it do.
"""

import json
import networkx as nx
from shared.db import execute_query
from shared.fda_client import lookup_drug


def build_graph() -> nx.DiGraph:
    """Build the knowledge graph from clinic DB and FDA data."""
    G = nx.DiGraph()

    # --- Schema-level nodes: tables and their relationships ---
    _add_table_nodes(G)
    _add_fk_edges(G)

    # --- Data-level nodes ---
    _add_drug_nodes(G)
    _add_patient_nodes(G)
    _add_condition_nodes(G)
    _add_prescription_edges(G)
    _add_interaction_edges(G)
    _add_summary_nodes(G)

    return G


def _add_table_nodes(G: nx.DiGraph):
    """Add a node for each table in the clinic database."""
    tables = execute_query("""
        SELECT t.table_name,
               (SELECT COUNT(*) FROM information_schema.columns c
                WHERE c.table_name = t.table_name AND c.table_schema = 'public') as column_count
        FROM information_schema.tables t
        WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE'
        ORDER BY t.table_name
    """)
    for t in tables:
        count = execute_query(f"SELECT COUNT(*) as cnt FROM {t['table_name']}")
        G.add_node(
            f"table:{t['table_name']}",
            type="table",
            source="clinic",
            name=t["table_name"],
            column_count=t["column_count"],
            row_count=count[0]["cnt"],
        )


def _add_fk_edges(G: nx.DiGraph):
    """Add edges for foreign key relationships between tables."""
    fks = execute_query("""
        SELECT
            tc.table_name AS from_table,
            ccu.table_name AS to_table,
            kcu.column_name AS column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
    """)
    for fk in fks:
        G.add_edge(
            f"table:{fk['from_table']}",
            f"table:{fk['to_table']}",
            type="foreign_key",
            via=fk["column_name"],
        )


def _add_drug_nodes(G: nx.DiGraph):
    """Add drug nodes from prescriptions + FDA data."""
    drugs = execute_query(
        "SELECT DISTINCT drug_ndc, drug_name FROM prescriptions ORDER BY drug_name"
    )
    for drug in drugs:
        ndc = drug["drug_ndc"]
        name = drug["drug_name"]

        # Get FDA data for this drug
        fda_info = lookup_drug(name)

        node_data = {
            "type": "drug",
            "source": "fda",
            "name": name,
            "ndc": ndc,
        }
        if fda_info:
            node_data["pharm_class"] = fda_info.get("pharm_class", [])
            node_data["route"] = fda_info.get("route", "Unknown")
            node_data["indications"] = fda_info.get("indications", "")[:200]
            node_data["warnings"] = fda_info.get("warnings", "")[:200]

        G.add_node(f"drug:{ndc}", **node_data)

        # Bridge edge: prescriptions table → this drug
        G.add_edge(
            "table:prescriptions", f"drug:{ndc}",
            type="ndc_bridge",
            via="drug_ndc",
            label=f"prescriptions reference {name} via NDC {ndc}",
        )
        # Bridge edge: pharmacy_inventory → this drug
        G.add_edge(
            "table:pharmacy_inventory", f"drug:{ndc}",
            type="ndc_bridge",
            via="drug_ndc",
            label=f"inventory tracks {name} via NDC {ndc}",
        )


def _add_patient_nodes(G: nx.DiGraph):
    """Add patient nodes (private data)."""
    patients = execute_query(
        "SELECT patient_id, first_name, last_name, conditions, allergies FROM patients"
    )
    for p in patients:
        G.add_node(
            f"patient:{p['patient_id']}",
            type="patient",
            source="clinic",
            name=f"{p['first_name']} {p['last_name']}",
            patient_id=p["patient_id"],
            conditions=p["conditions"] or [],
            allergies=p["allergies"] or [],
        )


def _add_condition_nodes(G: nx.DiGraph):
    """Add condition nodes and link patients to them."""
    patients = execute_query("SELECT patient_id, conditions FROM patients")
    for p in patients:
        for condition in (p["conditions"] or []):
            # Add condition node if it doesn't exist
            cond_id = f"condition:{condition}"
            if cond_id not in G:
                G.add_node(cond_id, type="condition", source="clinic", name=condition)
            # Patient → condition
            G.add_edge(
                f"patient:{p['patient_id']}", cond_id,
                type="has_condition",
            )


def _add_prescription_edges(G: nx.DiGraph):
    """Add edges from patients to their prescribed drugs."""
    prescriptions = execute_query("""
        SELECT patient_id, drug_ndc, drug_name, dosage, frequency, status
        FROM prescriptions
    """)
    for rx in prescriptions:
        G.add_edge(
            f"patient:{rx['patient_id']}", f"drug:{rx['drug_ndc']}",
            type="prescribed",
            drug_name=rx["drug_name"],
            dosage=rx["dosage"],
            frequency=rx["frequency"],
            status=rx["status"],
        )


def _add_interaction_edges(G: nx.DiGraph):
    """Add drug interaction edges from the clinic's curated table."""
    interactions = execute_query("SELECT * FROM drug_interactions")
    for ix in interactions:
        G.add_edge(
            f"drug:{ix['drug_a_ndc']}", f"drug:{ix['drug_b_ndc']}",
            type="interacts_with",
            severity=ix["severity"],
            description=ix["description"],
            recommendation=ix.get("clinical_recommendation", ""),
        )
        # Add reverse edge too — interactions are bidirectional
        G.add_edge(
            f"drug:{ix['drug_b_ndc']}", f"drug:{ix['drug_a_ndc']}",
            type="interacts_with",
            severity=ix["severity"],
            description=ix["description"],
            recommendation=ix.get("clinical_recommendation", ""),
        )


def _add_summary_nodes(G: nx.DiGraph):
    """Add aggregated summary nodes."""
    # Drug usage summary
    usage = execute_query("""
        SELECT drug_name, drug_ndc, COUNT(*) as prescription_count,
               COUNT(DISTINCT patient_id) as patient_count,
               COUNT(*) FILTER (WHERE status = 'active') as active_count
        FROM prescriptions
        GROUP BY drug_name, drug_ndc
        ORDER BY prescription_count DESC
    """)
    G.add_node(
        "summary:drug_usage",
        type="summary",
        source="clinic",
        name="Drug Usage Statistics",
        data={row["drug_name"]: {
            "prescriptions": row["prescription_count"],
            "patients": row["patient_count"],
            "active": row["active_count"],
        } for row in usage},
    )

    # Condition prevalence
    conditions = execute_query("""
        SELECT unnest(conditions) as condition, COUNT(*) as patient_count
        FROM patients
        GROUP BY condition
        ORDER BY patient_count DESC
    """)
    G.add_node(
        "summary:conditions",
        type="summary",
        source="clinic",
        name="Condition Prevalence",
        data={row["condition"]: row["patient_count"] for row in conditions},
    )

    # Interaction risk summary
    at_risk = execute_query("""
        SELECT COUNT(DISTINCT p1.patient_id) as patients_at_risk
        FROM prescriptions p1
        JOIN prescriptions p2 ON p1.patient_id = p2.patient_id
            AND p1.prescription_id < p2.prescription_id
            AND p1.status = 'active' AND p2.status = 'active'
        JOIN drug_interactions di
            ON (p1.drug_ndc = di.drug_a_ndc AND p2.drug_ndc = di.drug_b_ndc)
            OR (p1.drug_ndc = di.drug_b_ndc AND p2.drug_ndc = di.drug_a_ndc)
    """)
    G.add_node(
        "summary:interaction_risks",
        type="summary",
        source="clinic",
        name="Interaction Risk Summary",
        data={"patients_with_interaction_risks": at_risk[0]["patients_at_risk"] if at_risk else 0},
    )


def graph_stats(G: nx.DiGraph) -> dict:
    """Compute summary statistics about the graph."""
    # Count nodes by type
    node_types = {}
    for _, data in G.nodes(data=True):
        t = data.get("type", "unknown")
        node_types[t] = node_types.get(t, 0) + 1

    # Count edges by type
    edge_types = {}
    for _, _, data in G.edges(data=True):
        t = data.get("type", "unknown")
        edge_types[t] = edge_types.get(t, 0) + 1

    # Degree centrality — most connected nodes
    centrality = nx.degree_centrality(G)
    top_nodes = sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "total_nodes": G.number_of_nodes(),
        "total_edges": G.number_of_edges(),
        "node_types": node_types,
        "edge_types": edge_types,
        "most_connected": [
            {"node": node, "centrality": round(score, 4),
             "type": G.nodes[node].get("type", "unknown")}
            for node, score in top_nodes
        ],
    }
