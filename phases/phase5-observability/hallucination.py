"""Phase 5: Hallucination detection.

Compares entities in the final answer against entities that appeared
in tool results. An entity mentioned in the answer but absent from
all tool results is a hallucination candidate.

Two detection modes:
1. Known-entity grounding: check which known KG entities the answer mentions,
   and whether they appeared in tool results for this query.
2. Drug name heuristic: catch drug-like words in the answer that aren't
   in the known entity set at all (the Phase 3 problem -- guessing drugs
   that don't exist in our database).
"""

import re

# Common drug name suffixes for heuristic detection
_DRUG_SUFFIXES = (
    "pril", "olol", "statin", "dipine", "formin", "sartan",
    "zepam", "pine", "mab", "zole", "cillin", "mycin",
    "oxine", "prazole", "azine", "tidine",
)


def detect_hallucinations(trace, known_entities: set[str]) -> dict:
    """Compare answer entities against tool result entities.

    Args:
        trace: A Trace object with .answer and .tool_spans
        known_entities: Set of entity names from list_graph_nodes (built at startup)

    Returns:
        {
            "mentioned_known": [...],      entities from our KG that appear in the answer
            "grounded": [...],             also found in tool results
            "ungrounded": [...],           in answer + KG but NOT in tool results
            "unknown_drugs": [...],        drug-like words not in our KG at all
            "hallucination_count": int,    ungrounded + unknown_drugs
        }
    """
    answer_lower = trace.answer.lower()
    tool_text = " ".join(s.tool_result for s in trace.tool_spans).lower()

    # 1. Known-entity grounding
    mentioned = set()
    for entity in known_entities:
        if entity.lower() in answer_lower:
            mentioned.add(entity)

    grounded = set()
    ungrounded = set()
    for entity in mentioned:
        if entity.lower() in tool_text:
            grounded.add(entity)
        else:
            ungrounded.add(entity)

    # 2. Drug name heuristic -- catch guessed drug names not in our system
    known_lower = {e.lower() for e in known_entities}
    unknown_drugs = set()
    for match in re.finditer(r"\b([A-Z][a-z]{3,})\b", trace.answer):
        word = match.group(1)
        if word.lower() in known_lower:
            continue
        if any(word.lower().endswith(suffix) for suffix in _DRUG_SUFFIXES):
            # Check it's not in tool results either
            if word.lower() not in tool_text:
                unknown_drugs.add(word)

    return {
        "mentioned_known": sorted(mentioned),
        "grounded": sorted(grounded),
        "ungrounded": sorted(ungrounded),
        "unknown_drugs": sorted(unknown_drugs),
        "hallucination_count": len(ungrounded) + len(unknown_drugs),
    }
