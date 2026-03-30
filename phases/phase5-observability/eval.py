"""Phase 5: Evaluation -- score outputs against expected entities."""

import json
import os


def load_expectations() -> list[dict]:
    """Load ground truth from expectations.json."""
    path = os.path.join(os.path.dirname(__file__), "expectations.json")
    with open(path) as f:
        return json.load(f)


def _normalize(text: str) -> str:
    """Normalize for flexible matching: lowercase, collapse separators."""
    return text.lower().replace("_", " ").replace("-", " ").strip()


def _entity_in_text(entity: str, text: str) -> bool:
    """Check if an entity appears in text (case-insensitive, flexible)."""
    return _normalize(entity) in _normalize(text)


def score_query(answer: str, expectation: dict) -> dict:
    """Score a single query answer against expected entities.

    Scoring: (must_include_recall * 0.7) + (should_include_recall * 0.3)
    Penalize 0.1 per must_not_include violation.
    """
    must = expectation.get("must_include", [])
    should = expectation.get("should_include", [])
    must_not = expectation.get("must_not_include", [])

    must_found = [e for e in must if _entity_in_text(e, answer)]
    must_missing = [e for e in must if not _entity_in_text(e, answer)]

    should_found = [e for e in should if _entity_in_text(e, answer)]
    should_missing = [e for e in should if not _entity_in_text(e, answer)]

    must_not_found = [e for e in must_not if _entity_in_text(e, answer)]

    must_recall = len(must_found) / len(must) if must else 1.0
    should_recall = len(should_found) / len(should) if should else 1.0

    penalty = len(must_not_found) * 0.1
    score = max(0.0, (must_recall * 0.7 + should_recall * 0.3) - penalty)

    return {
        "query_id": expectation["query_id"],
        "must_include": {"found": must_found, "missing": must_missing},
        "should_include": {"found": should_found, "missing": should_missing},
        "must_not_include": {"violations": must_not_found},
        "score": round(score, 2),
    }
