"""Phase 2: Local tools — same as Phase 1.

These stay in the app, not on the MCP server.
"""

import json


def format_report(title: str, sections: list[str]) -> str:
    """Format findings into a readable report."""
    lines = [f"# {title}", ""]
    for i, section in enumerate(sections, 1):
        lines.append(f"## Section {i}")
        lines.append(section)
        lines.append("")
    return "\n".join(lines)


def calculate_risk_score(drug_count: int, interaction_count: int, has_allergies: bool) -> str:
    """Calculate a simple medication risk score based on a patient's profile."""
    score = 0
    score += drug_count * 10
    score += interaction_count * 25
    if has_allergies:
        score += 15

    if score >= 60:
        level = "HIGH"
    elif score >= 30:
        level = "MODERATE"
    else:
        level = "LOW"

    return json.dumps({
        "risk_score": score,
        "risk_level": level,
        "factors": {
            "drug_count": drug_count,
            "interaction_count": interaction_count,
            "has_allergies": has_allergies,
        },
    })


LOCAL_TOOLS = [
    {
        "name": "format_report",
        "description": "Format findings into a structured report with a title and sections.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Report title"},
                "sections": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Report sections as text",
                },
            },
            "required": ["title", "sections"],
        },
    },
    {
        "name": "calculate_risk_score",
        "description": "Calculate a medication risk score for a patient based on drug count, known interactions, and allergy status. Use after retrieving patient data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "drug_count": {"type": "integer", "description": "Number of active prescriptions"},
                "interaction_count": {"type": "integer", "description": "Number of known drug interactions"},
                "has_allergies": {"type": "boolean", "description": "Whether the patient has documented allergies"},
            },
            "required": ["drug_count", "interaction_count", "has_allergies"],
        },
    },
]

LOCAL_TOOL_FUNCTIONS = {
    "format_report": lambda **kwargs: format_report(kwargs["title"], kwargs["sections"]),
    "calculate_risk_score": lambda **kwargs: calculate_risk_score(
        kwargs["drug_count"], kwargs["interaction_count"], kwargs["has_allergies"]
    ),
}
