# Phase 4 — Semantic Search

**MCP concept:** Embedding-based search over a knowledge graph, served as an MCP tool.
**Domain concept:** Finding clinically related concepts without exact keyword matches.

## What Changed from Phase 3

Phase 3 added automated workflows. Phase 4 adds **semantic search** — the LLM can now find relevant data by meaning, not just by exact names or graph traversal.

```
Phase 3 (structural only):          Phase 4 (structural + semantic):
  "hypertension" ─► exact match       "heart problems" ─► semantic_search
      │                                    │
  find_path, get_neighbors             embeds query, cosine similarity
      │                                    │
  follows graph edges                  finds: hypertension, amlodipine,
                                       atrial_fibrillation, cardiovascular
```

The MCP server embeds all knowledge graph entities on startup using sentence-transformers. The `semantic_search` tool is just another MCP tool — the client doesn't need to know how it works.

## The Pattern

Semantic search complements graph traversal. They solve different problems:

- **Graph traversal** (find_path, get_neighbors): follows explicit edges. "What drugs does Patient 3 take?" — deterministic, structural.
- **Semantic search**: finds conceptually related items. "Heart problems" — no node is named "heart problems", but the embedding is close to hypertension, amlodipine, atrial fibrillation.

Neither replaces the other. Graph traversal gives you precision. Semantic search gives you discovery.

## How It Works

The `SemanticIndex` embeds knowledge graph entities on server startup:

| Entity Type | Example Text Embedded |
|------------|----------------------|
| drug | "Metformin metformin hydrochloride oral antidiabetic" |
| condition | "hypertension high blood pressure cardiovascular heart" |
| patient | "patient David Brown conditions hypertension allergies penicillin" |
| table | "database table prescriptions clinic data" |
| concept | "cardiovascular heart blood pressure hypertension angina arrhythmia..." |

Concepts are synthetic entries that cluster related medical terms — they don't map to graph nodes but help bridge vocabulary gaps.

**Model:** `all-MiniLM-L6-v2` (~80MB) via sentence-transformers. Falls back to keyword matching if not installed.

**Query flow:**
1. Embed the query text
2. Cosine similarity against all document embeddings
3. Return top-N results ranked by relevance score

## Examples

```
Query: "heart problems"
Results:
  1. Cardiovascular Health (concept, 0.72)
  2. amlodipine (drug, 0.58)
  3. hypertension (condition, 0.55)
  4. atrial_fibrillation (condition, 0.51)
  5. lisinopril (drug, 0.47)

Query: "sugar medication"
Results:
  1. Metabolic Health (concept, 0.65)
  2. metformin (drug, 0.61)
  3. diabetes_type2 (condition, 0.54)
```

## Phase 3 vs Phase 4: Same Query, Different Approach

Running `"Find anything related to cardiovascular health."` against both phases shows the difference clearly.

**Phase 4 — first move:**
```
semantic_search(query='cardiovascular health heart blood pressure hypertension', limit=15)
→ hypertension (0.83), Cardiovascular Health (0.70), atrial_fibrillation (0.43), high_cholesterol...
```
Immediately knows what's relevant. Every subsequent call is targeted.

**Phase 3 — first move:**
```
run_query("SELECT DISTINCT condition FROM patients WHERE condition ILIKE '%cardio%' OR condition ILIKE '%heart%'...")
→ ERROR (wrong column name)
```
Has to *guess* what "cardiovascular" means in SQL. Fails, recovers, guesses again.

| | Phase 3 | Phase 4 |
|---|---|---|
| Tool calls | ~14 | ~12 |
| SQL errors requiring recovery | 4 | 1 |
| Hardcoded drug guesses | Metoprolol, Carvedilol, Losartan, Simvastatin, Clopidogrel, Warfarin (none in DB) | None needed |
| First useful data returned | 3rd call | 1st call |

Phase 3's LLM had to guess that "cardiovascular" maps to `'hypertension' = ANY(conditions)` and that cardiovascular drugs include Amlodipine, Lisinopril, Atorvastatin. It got there — Claude is capable enough to infer common drug names — but it also guessed six drugs that don't exist in the clinic database.

Phase 4 didn't guess. It asked the semantic index and got back ranked, real entities from the knowledge graph. Then it followed up with exact, targeted calls.

Both reports reached similar conclusions, which is the interesting part — the LLM *can* compensate for missing semantic search, but at the cost of more errors, more speculative queries, and more tokens. Semantic search turns discovery from a guessing game into a lookup.

### Second test: `"stroke risk"`

A harder test — "stroke" doesn't appear anywhere in the database. No column, no condition, no node.

**Phase 3 got there anyway.** Claude's medical training kicked in: stroke → hypertension + atrial fibrillation + diabetes. It built SQL WHERE clauses from that knowledge, found the right patients, even flagged two AFib patients without anticoagulation as critical. But it took 10 tool calls with 2 SQL errors, and it guessed drugs that don't exist (Warfarin, Clopidogrel, Aspirin).

**Phase 4's semantic search** would surface the cardiovascular concept (which includes "stroke" in its embedding text), hypertension, and atrial fibrillation — directly, ranked by relevance, on the first call.

### What the comparison actually shows

The value of semantic search isn't binary found/not-found — it's **reliability and efficiency**. A capable LLM can compensate for missing semantic search by leaning on its training data, but it does so with more guesswork, more errors, and more tokens. In medicine, where Claude is deeply knowledgeable, the LLM's own vocabulary bridges the gap. In a more specialized domain — proprietary product catalogs, internal codenames, domain-specific jargon — semantic search would be the difference between finding relevant data and missing it entirely.

| What semantic search provides | Why it matters |
|---|---|
| Grounded in actual data, not LLM training | No hallucinated entities (Phase 3 guessed 6 drugs not in DB) |
| Ranked results on first call | Fewer tool calls, lower latency and cost |
| Works regardless of LLM medical knowledge | Scales to domains where the LLM has less training |
| Deterministic for the same query | Reproducible behavior vs. LLM reasoning variance |

## Running

```bash
# Single query (semantic search available as a tool)
python3 phases/phase4-semantic/client.py --query "Find anything related to cardiovascular health."
python3 phases/phase4-semantic/client.py --query "What do we know about sugar medication?"

# Test suite
python3 phases/phase4-semantic/client.py --test

# Workflows (same as Phase 3)
python3 phases/phase4-semantic/client.py --workflow safety_review
python3 phases/phase4-semantic/client.py --workflow drug_utilization
python3 phases/phase4-semantic/client.py --workflow cohort_comparison

# Prompts (now include semantic search steps)
python3 phases/phase4-semantic/client.py --prompt explore_drug --args '{"drug_name": "Metformin"}'

# Interactive mode
python3 phases/phase4-semantic/client.py
```

## What This Proves

Semantic search is a **server-side capability** — the client sends a query string, gets back ranked results. The LLM doesn't compute embeddings or manage the index. The MCP server handles it the same way it handles SQL queries or graph traversal: as a tool.

This is the complement to the knowledge graph, not a replacement. NetworkX gives you every structural benefit from Phase 2 — path finding, neighbor discovery, join suggestion. Embeddings add conceptual discovery on top: the ability to find relevant data when the user's vocabulary doesn't match the data's vocabulary. Together, they give the LLM two ways to navigate the same knowledge: by structure and by meaning.
