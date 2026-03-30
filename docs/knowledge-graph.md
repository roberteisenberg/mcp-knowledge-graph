# The Knowledge Graph — What It Is, What It Does, and Why It Matters

## What It Is

The knowledge graph (KG) is a NetworkX `DiGraph` — a directed graph data structure held in memory. It's built on server startup from two sources:

- **Clinic PostgreSQL database** — patients, prescriptions, doctors, conditions, drug interactions
- **FDA openFDA API** — drug labels, classifications, adverse event data

The graph has **34 nodes** and **87 edges** across 5 node types:

| Node type | Count | Source | Examples |
|-----------|-------|--------|----------|
| table | 7 | clinic DB schema | `table:prescriptions`, `table:patients` |
| drug | 6 | FDA + clinic | `drug:11788-037` (Metformin) |
| patient | 12 | clinic DB | `patient:1` (Jane Doe) |
| condition | 6 | clinic DB (extracted from patient arrays) | `condition:hypertension` |
| summary | 3 | aggregated from clinic DB | `summary:drug_usage` |

Connected by 5 edge types:

| Edge type | Count | What it represents |
|-----------|-------|--------------------|
| prescribed | 28 | patient → drug (from prescriptions table) |
| has_condition | 27 | patient → condition (extracted from arrays) |
| interacts_with | 14 | drug ↔ drug (from drug_interactions table, bidirectional) |
| ndc_bridge | 12 | table → drug (prescriptions/inventory link to FDA via NDC) |
| foreign_key | 6 | table → table (schema relationships) |

## How It Differs from the Relational Database

The clinic database already has foreign keys — those are relationships too. The KG differs in three ways:

**1. Cross-source edges that don't exist in any single database.**
There's no FK from `prescriptions` to the FDA API. The NDC bridge is constructed by the graph — connecting a clinic prescription row to FDA drug data from an external API. You can't `JOIN` across a database and a REST API, but you can traverse a graph that spans both.

**2. Denormalized data pulled into first-class nodes.**
`patients.conditions` is a text array column — `["diabetes_type2", "hypertension"]` buried inside a row. The KG extracts each condition into its own node with edges to every patient who has it. Now "which patients share hypertension?" is a single graph traversal instead of a SQL query against array columns.

**3. Aggregate/summary nodes alongside raw data.**
`summary:drug_usage` sits in the graph with pre-computed stats (Metformin: 6 patients, 5 active). A database doesn't have this unless you create materialized views. The graph mixes schema-level, data-level, and summary-level information in one traversable structure.

## What NetworkX Provides

NetworkX is the Python library that implements the graph data structure and algorithms. Every KG traversal tool calls NetworkX under the hood:

| MCP Tool | NetworkX underneath |
|----------|-------------------|
| `find_path(a, b)` | `nx.shortest_path(G, a, b)` |
| `get_neighbors(node, depth)` | BFS using `G.successors()` and `G.predecessors()` |
| `get_graph_stats()` | `nx.degree_centrality(G)`, `G.number_of_nodes()` |
| `suggest_join(tables)` | `nx.shortest_path()` following FK edges |
| `get_drug_patient_overlap()` | `G.predecessors()` traversal + node attribute reads |
| `list_graph_nodes()` | `G.nodes(data=True)` iteration |

It's not a database — it's an in-memory data structure. For 34 nodes this is trivial. NetworkX scales comfortably to hundreds of thousands of nodes. Beyond that you'd reach for a graph database like Neo4j.

## What the KG Provided with Our Small Dataset (12 patients, 6 drugs)

Even at this scale, the KG delivered tangible results that the relational database alone did not:

**Centrality analysis** — Graph algorithms identified Lisinopril and Metformin as the two most connected nodes (centrality: 0.4242 each). This reflects their dual role: heavily prescribed AND involved in multiple drug interactions. SQL can tell you "Metformin has the most prescriptions" but it can't tell you "Metformin is the most connected entity in your entire system when you consider prescriptions, interactions, conditions, and FDA data together." That's a graph algorithm.

**Cross-source traversal in one hop** — `get_drug_patient_overlap("Metformin")` returned: 6 patients, 83% also have hypertension, 3 known interactions with co-prescribed drugs — all from a single graph traversal. In Phase 1 (no KG), this required 3-4 separate tool calls: query prescriptions, query patient conditions, query interactions, aggregate.

**Relationship discovery** — `get_neighbors("condition:hypertension", depth=2)` instantly revealed that hypertension connects to 9 patients who connect to 5 different drugs. The LLM didn't need to know which tables to query or how to join them — the graph already encoded the connections.

**Path finding** — `find_path("patient:1", "drug:68001-335")` returned a single `prescribed` edge, confirming Jane Doe takes Lisinopril. But `find_path("table:patients", "drug:11788-037")` would require traversing through the prescriptions table — making the NDC bridge explicit and visible.

**What it did NOT dramatically improve:**
- Patient medication reviews (Phase 1's `get_patient` + `get_prescriptions` + `check_interactions` already handled this well)
- Simple interaction checks (the `drug_interactions` table was already queryable)
- Direct FDA lookups (still just API calls)

At 12 patients, the LLM could brute-force most of what the KG does by issuing multiple SQL queries. The KG made it faster and more discoverable, but not categorically different.

## What the KG Would Provide at Scale

The value inflection point is roughly when the LLM can no longer brute-force relationships through sequential queries. Some projections:

### 1,000 patients, 50 drugs

**Interaction risk detection becomes impractical without the graph.** With 50 drugs and ~2,000 active prescriptions, checking every patient's drug pairs against every known interaction is O(n²) per patient. The graph pre-computes interaction edges — traversal is O(1) per edge. The `summary:interaction_risks` node gives an instant count instead of a full-table scan.

**Condition clustering reveals population health patterns.** With enough patients, condition nodes become hubs. "Hypertension connects to 430 patients who are collectively on 12 different drugs with 8 interaction pairs" — that's a single graph traversal that would require multiple complex SQL queries with array unnesting.

**Cross-source value compounds.** FDA adverse event data becomes meaningful at population scale. "23% of our metformin patients have reported adverse reactions that match the top 5 FDA FAERS signals" — the graph connects clinic outcomes to FDA safety data through drug nodes.

### 10,000+ patients, 200+ drugs

**Graph algorithms reveal non-obvious patterns:**
- **Community detection** — clusters of patients with similar drug/condition profiles (useful for cohort analysis)
- **Betweenness centrality** — drugs that bridge otherwise disconnected patient populations (important for formulary decisions)
- **Connected components** — isolated subgraphs where a group of patients shares a unique drug/condition combination

**Aggregation at multiple levels becomes essential.** Summary nodes become the primary interface — no one is browsing 10,000 patient nodes. The three-tier model (public nodes → summary nodes → private nodes) maps to real access patterns: dashboards show aggregates, clinical records show details.

**The LLM's query planning improves.** With a large graph, the LLM can use `get_graph_stats()` to understand the landscape, `get_neighbors()` to narrow scope, and `find_path()` to discover connections — instead of guessing which SQL queries to run. The graph acts as a map of the data.

### Additional capabilities that emerge at scale

- **Temporal edges** — prescription start/end dates become edge attributes. Graph traversal can answer "what changed in the last 30 days?" across all patients.
- **Similarity edges** — patients with overlapping drug/condition profiles can be linked. "Patients like this one" becomes a graph traversal.
- **Risk propagation** — a new FDA safety signal for Drug X propagates through the graph to identify all affected patients, their co-prescribed drugs, and potential interaction cascades.

## NetworkX vs Embeddings — Who Does What

This is an important distinction. In our current implementation (Phase 2), **100% of the KG benefits come from NetworkX**. Embeddings haven't been added yet — they arrive in Phase 4.

They solve completely different problems:

| | NetworkX (Phase 2) | Embeddings (Phase 4) |
|---|---|---|
| **What it does** | Graph structure and traversal | Semantic similarity |
| **Question it answers** | "What connects A to B?" | "What's similar to X?" |
| **How it works** | Nodes, edges, algorithms (BFS, shortest path, centrality) | Vector similarity (cosine distance) |
| **Data type** | Structured relationships (FKs, prescriptions, interactions) | Unstructured text (drug descriptions, clinical notes) |
| **Example** | "Find the path from patient:1 to drug:11788-037" | "Find anything related to heart problems" |

**NetworkX gives you structure.** It knows that Metformin connects to Lisinopril through an `interacts_with` edge with severity "mild". It can compute centrality, find shortest paths, detect clusters.

**Embeddings give you meaning.** They know that "cardiovascular health" is semantically related to "hypertension", "blood_pressure", "amlodipine", and "atrial_fibrillation" — even though those strings share no keywords.

Phase 2 handles test queries 1, 2, 3, 5, and 6 well with just NetworkX. Test query 4 ("Find anything related to cardiovascular health") is where embeddings will make a real difference — right now it's keyword matching at best.

In a production system you'd use both: embeddings to find semantically relevant nodes, then graph traversal to explore their connections. The embedding finds the starting points; the graph finds the paths.
