"""Phase 4: Semantic search over the knowledge graph using embeddings.

Embeds drug names, conditions, table descriptions, and clinical concepts.
Semantic search finds related items even when exact keywords don't match:
- "heart problems" → hypertension, amlodipine, blood_pressure, atrial_fibrillation
- "sugar medication" → metformin, diabetes_type2, HbA1c
"""

import json
import numpy as np
from typing import Optional

# Try to import sentence-transformers; fall back to keyword matching
try:
    from sentence_transformers import SentenceTransformer
    _model = None

    def _get_model():
        global _model
        if _model is None:
            _model = SentenceTransformer("all-MiniLM-L6-v2")
        return _model

    def _embed(texts: list[str]) -> np.ndarray:
        return _get_model().encode(texts, normalize_embeddings=True)

    EMBEDDINGS_AVAILABLE = True

except ImportError:
    EMBEDDINGS_AVAILABLE = False

    def _embed(texts: list[str]) -> np.ndarray:
        """Fallback: TF-IDF-like keyword vectors."""
        # Build vocabulary from all texts
        vocab = {}
        for text in texts:
            for word in text.lower().split():
                if word not in vocab:
                    vocab[word] = len(vocab)

        # Create simple bag-of-words vectors
        vectors = np.zeros((len(texts), len(vocab)))
        for i, text in enumerate(texts):
            for word in text.lower().split():
                vectors[i, vocab[word]] = 1.0

        # Normalize
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1
        return vectors / norms


class SemanticIndex:
    """Embeds knowledge graph entities and supports similarity search."""

    def __init__(self):
        self.documents: list[dict] = []
        self.embeddings: Optional[np.ndarray] = None

    def build_from_graph(self, G) -> None:
        """Build the semantic index from a NetworkX knowledge graph."""
        self.documents = []

        for node, data in G.nodes(data=True):
            node_type = data.get("type", "unknown")
            name = data.get("name", node)

            if node_type == "drug":
                text = f"{name} {' '.join(data.get('pharm_class', []))} "
                text += f"{data.get('indications', '')} {data.get('route', '')}"

            elif node_type == "condition":
                text = f"{name} medical condition clinical"
                # Expand common conditions with related terms
                expansions = {
                    "hypertension": "high blood pressure cardiovascular heart",
                    "diabetes_type2": "blood sugar glucose insulin metabolic",
                    "high_cholesterol": "lipid cholesterol cardiovascular statin",
                    "hypothyroidism": "thyroid hormone endocrine",
                    "gerd": "acid reflux gastric stomach digestive",
                    "atrial_fibrillation": "heart rhythm cardiac arrhythmia cardiovascular",
                }
                text += " " + expansions.get(name, "")

            elif node_type == "patient":
                conditions = " ".join(data.get("conditions", []))
                allergies = " ".join(data.get("allergies", []))
                text = f"patient {name} conditions {conditions} allergies {allergies}"

            elif node_type == "table":
                text = f"database table {name} clinic data"

            elif node_type == "summary":
                text = f"summary statistics {name} aggregate"

            else:
                continue

            self.documents.append({
                "id": node,
                "type": node_type,
                "name": name,
                "text": text.strip(),
            })

        # Add some clinical concept entries that don't map directly to nodes
        extra_concepts = [
            {"id": "concept:cardiovascular", "type": "concept", "name": "Cardiovascular Health",
             "text": "cardiovascular heart blood pressure hypertension angina arrhythmia atrial fibrillation stroke cardiac"},
            {"id": "concept:metabolic", "type": "concept", "name": "Metabolic Health",
             "text": "metabolic diabetes blood sugar glucose insulin HbA1c obesity weight"},
            {"id": "concept:gastrointestinal", "type": "concept", "name": "Gastrointestinal Health",
             "text": "gastrointestinal stomach acid reflux GERD ulcer digestive nausea"},
            {"id": "concept:drug_safety", "type": "concept", "name": "Drug Safety",
             "text": "drug interaction adverse event side effect contraindication warning safety risk"},
        ]
        self.documents.extend(extra_concepts)

        # Compute embeddings
        texts = [doc["text"] for doc in self.documents]
        self.embeddings = _embed(texts)

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Search for items semantically similar to the query."""
        if self.embeddings is None or len(self.documents) == 0:
            return []

        # Embed query
        query_vec = _embed([query])

        # Cosine similarity (embeddings are already normalized)
        similarities = np.dot(self.embeddings, query_vec.T).flatten()

        # Rank
        ranked = sorted(
            enumerate(similarities), key=lambda x: x[1], reverse=True
        )

        results = []
        for idx, score in ranked:
            doc = self.documents[idx]
            results.append({
                "id": doc["id"],
                "type": doc["type"],
                "name": doc["name"],
                "relevance": round(float(score), 4),
            })
            if len(results) >= limit:
                break

        return results
