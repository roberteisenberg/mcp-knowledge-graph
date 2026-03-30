"""Phase 3: Automated workflows — Python drives, Claude reasons.

Each workflow follows the same pattern:
1. Gather data (MCP tool calls — deterministic, cheap)
2. Analyze (Claude — LLM reasoning, expensive, only when needed)
3. Format results (local tool — deterministic)

Python controls the loop. The MCP server doesn't know or care whether
it's being called interactively or in a batch workflow.
"""

import json
from itertools import combinations

import anthropic
from mcp import ClientSession

from local_tools import format_report, calculate_risk_score


async def call_mcp(session: ClientSession, tool_name: str, arguments: dict) -> dict:
    """Call an MCP tool and return parsed JSON result."""
    result = await session.call_tool(tool_name, arguments)
    if result.isError:
        return {"error": "MCP tool error"}
    text = result.content[0].text if result.content else "{}"
    return json.loads(text)


def call_claude(client: anthropic.Anthropic, prompt: str) -> str:
    """Call Claude for reasoning — no tools, just text in / text out."""
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


# ===================================================================
# Workflow 1: Medication Safety Review
# Checks ALL patients for drug interaction risks.
# ===================================================================


async def medication_safety_review(
    session: ClientSession, client: anthropic.Anthropic
) -> str:
    """Review all patients for drug interaction risks.

    Steps:
    1. Find patients with 2+ active prescriptions (MCP — deterministic)
    2. Check each patient's interactions (MCP — deterministic)
    3. Get patient details for flagged cases (MCP — deterministic)
    4. Ask Claude to assess clinical significance (LLM — reasoning)
    5. Format report (local — deterministic)
    """
    print("  [STEP 1] Finding patients with multiple active prescriptions...")

    # Step 1: Get patients with 2+ active prescriptions
    multi_rx = await call_mcp(session, "run_query", {
        "sql": """
            SELECT patient_id, COUNT(*) as drug_count
            FROM prescriptions
            WHERE status = 'active'
            GROUP BY patient_id
            HAVING COUNT(*) >= 2
            ORDER BY drug_count DESC
        """
    })

    if not multi_rx or isinstance(multi_rx, dict) and "error" in multi_rx:
        return "Error: Could not query prescriptions."

    print(f"  [STEP 1] Found {len(multi_rx)} patients with 2+ active drugs\n")

    # Step 2: Check interactions for each patient
    print("  [STEP 2] Checking drug interactions for each patient...")
    flagged = []

    for row in multi_rx:
        pid = row["patient_id"]
        interactions = await call_mcp(session, "check_interactions", {
            "patient_id": pid
        })

        if interactions and not isinstance(interactions, dict):
            # Has interactions — flag this patient
            patient = await call_mcp(session, "get_patient", {"patient_id": pid})
            prescriptions = await call_mcp(session, "get_prescriptions", {
                "patient_id": pid
            })
            flagged.append({
                "patient": patient,
                "prescriptions": prescriptions if isinstance(prescriptions, list) else [],
                "interactions": interactions,
            })
            print(f"    Patient {pid}: {len(interactions)} interaction(s) found")
        else:
            print(f"    Patient {pid}: no interactions")

    print(f"\n  [STEP 2] {len(flagged)} patients flagged with interactions\n")

    if not flagged:
        return format_report("Medication Safety Review", [
            "No drug interaction risks found among patients with multiple active prescriptions."
        ])

    # Step 3: Ask Claude to assess each flagged case (LLM reasoning)
    print("  [STEP 3] Claude assessing clinical significance...\n")
    sections = []

    for case in flagged:
        p = case["patient"]
        name = f"{p.get('first_name', '?')} {p.get('last_name', '?')}"
        pid = p.get("patient_id", "?")
        conditions = ", ".join(p.get("conditions", [])) or "none"
        allergies = ", ".join(p.get("allergies", [])) or "none"

        active_drugs = [
            rx["drug_name"] for rx in case["prescriptions"]
            if rx.get("status") == "active"
        ]

        interaction_text = "\n".join(
            f"- {ix['drug_a_name']} + {ix['drug_b_name']} ({ix['severity']}): {ix['description']}"
            for ix in case["interactions"]
        )

        # THIS is where the LLM earns its keep — clinical reasoning
        assessment = call_claude(client, f"""You are a clinical pharmacist. Briefly assess the clinical significance
of these drug interactions for this specific patient (3-4 sentences max).

Patient: {name} (ID: {pid})
Conditions: {conditions}
Allergies: {allergies}
Active medications: {', '.join(active_drugs)}

Known interactions:
{interaction_text}

Focus on: Is this patient at elevated risk given their specific conditions?
What should be monitored? Is any action needed?""")

        print(f"    Patient {pid} ({name}): assessed")

        # Risk score (local computation — no LLM needed)
        risk = json.loads(calculate_risk_score(
            drug_count=len(active_drugs),
            interaction_count=len(case["interactions"]),
            has_allergies=bool(p.get("allergies")),
        ))

        sections.append(
            f"**Patient {pid}: {name}** (Risk: {risk['risk_level']}, Score: {risk['risk_score']})\n"
            f"Conditions: {conditions}\n"
            f"Allergies: {allergies}\n"
            f"Active drugs: {', '.join(active_drugs)}\n\n"
            f"Interactions:\n{interaction_text}\n\n"
            f"Clinical Assessment:\n{assessment}"
        )

    print(f"\n  [STEP 3] All {len(flagged)} cases assessed\n")

    # Step 4: Format report (deterministic)
    summary = (
        f"Reviewed {len(multi_rx)} patients with 2+ active prescriptions. "
        f"{len(flagged)} patients have known drug interactions requiring attention."
    )
    return format_report(
        "Medication Safety Review",
        [summary] + sections,
    )


# ===================================================================
# Workflow 2: Drug Utilization Report
# Analyzes prescribing patterns across the clinic.
# ===================================================================


async def drug_utilization_report(
    session: ClientSession, client: anthropic.Anthropic
) -> str:
    """Generate a clinic-wide drug utilization report.

    Steps:
    1. Get prescription stats per drug (MCP — deterministic)
    2. Get graph-level drug overlap data (MCP — deterministic)
    3. Get FDA adverse event profiles (MCP — deterministic)
    4. Ask Claude to synthesize findings (LLM — reasoning)
    5. Format report (local — deterministic)
    """
    print("  [STEP 1] Gathering prescription statistics...")

    # Step 1: Get all drugs and their prescription counts
    drug_stats = await call_mcp(session, "run_query", {
        "sql": """
            SELECT drug_name, drug_ndc,
                   COUNT(*) as total_rx,
                   COUNT(*) FILTER (WHERE status = 'active') as active_rx,
                   COUNT(DISTINCT patient_id) as patient_count,
                   COUNT(DISTINCT doctor_id) as prescriber_count
            FROM prescriptions
            GROUP BY drug_name, drug_ndc
            ORDER BY total_rx DESC
        """
    })

    print(f"  [STEP 1] Found {len(drug_stats)} drugs in use\n")

    # Step 2: Get KG overlap data for each drug
    print("  [STEP 2] Gathering knowledge graph data per drug...")
    drug_profiles = []

    for drug in drug_stats:
        overlap = await call_mcp(session, "get_drug_patient_overlap", {
            "drug_name": drug["drug_name"]
        })

        # Step 3: Get FDA adverse event counts
        fda_adverse = await call_mcp(session, "fda_adverse_event_counts", {
            "drug_name": drug["drug_name"]
        })

        drug_profiles.append({
            "stats": drug,
            "overlap": overlap,
            "adverse_events": fda_adverse,
        })
        print(f"    {drug['drug_name']}: {drug['active_rx']} active, {drug['patient_count']} patients")

    print(f"\n  [STEP 2-3] All drug profiles gathered\n")

    # Step 4: Claude synthesizes (one LLM call for the whole report)
    print("  [STEP 4] Claude synthesizing findings...\n")

    profiles_text = ""
    for dp in drug_profiles:
        s = dp["stats"]
        o = dp["overlap"]
        profiles_text += f"\n{s['drug_name']} (NDC: {s['drug_ndc']}):\n"
        profiles_text += f"  Prescriptions: {s['total_rx']} total, {s['active_rx']} active\n"
        profiles_text += f"  Patients: {s['patient_count']}, Prescribers: {s['prescriber_count']}\n"
        if isinstance(o, dict) and "patient_conditions" in o:
            profiles_text += f"  Patient conditions: {o['patient_conditions']}\n"
            profiles_text += f"  Known interactions: {len(o.get('known_interactions', []))}\n"
        if isinstance(dp["adverse_events"], dict) and "top_reactions" in dp["adverse_events"]:
            top3 = dp["adverse_events"]["top_reactions"][:3]
            profiles_text += f"  Top FDA adverse events: {', '.join(r['reaction'] for r in top3)}\n"

    synthesis = call_claude(client, f"""You are a pharmacy director reviewing drug utilization for a clinic.
Write a concise analysis (2-3 paragraphs) covering:
1. Prescribing patterns — which drugs dominate and why
2. Safety observations — interaction risks across the formulary
3. One actionable recommendation

Drug utilization data:
{profiles_text}""")

    # Step 5: Format (deterministic)
    sections = []
    for dp in drug_profiles:
        s = dp["stats"]
        sections.append(
            f"**{s['drug_name']}** (NDC: {s['drug_ndc']})\n"
            f"Total prescriptions: {s['total_rx']} | Active: {s['active_rx']} | "
            f"Patients: {s['patient_count']} | Prescribers: {s['prescriber_count']}"
        )

    sections.append(f"**Analysis:**\n{synthesis}")

    return format_report("Drug Utilization Report", sections)


# ===================================================================
# Workflow 3: Patient Cohort Comparison
# Compares two condition cohorts across drugs, outcomes, interactions.
# ===================================================================


async def patient_cohort_comparison(
    session: ClientSession,
    client: anthropic.Anthropic,
    condition_a: str = "diabetes_type2",
    condition_b: str = "hypertension",
) -> str:
    """Compare two patient cohorts by condition.

    Steps:
    1. Get patients for each condition (MCP — deterministic)
    2. Get prescriptions for each cohort (MCP — deterministic)
    3. Find overlap patients (Python — deterministic)
    4. Ask Claude to compare (LLM — reasoning)
    5. Format report (local — deterministic)
    """
    print(f"  [STEP 1] Finding patients with {condition_a} vs {condition_b}...")

    # Step 1: Get KG neighbors for each condition
    cohort_a = await call_mcp(session, "get_neighbors", {
        "node": f"condition:{condition_a}", "depth": 1
    })
    cohort_b = await call_mcp(session, "get_neighbors", {
        "node": f"condition:{condition_b}", "depth": 1
    })

    patients_a = set()
    patients_b = set()

    if isinstance(cohort_a, dict):
        for nodes in cohort_a.get("neighbors_by_depth", {}).values():
            for n in nodes:
                if n.get("type") == "patient":
                    patients_a.add(n["node"])

    if isinstance(cohort_b, dict):
        for nodes in cohort_b.get("neighbors_by_depth", {}).values():
            for n in nodes:
                if n.get("type") == "patient":
                    patients_b.add(n["node"])

    overlap = patients_a & patients_b

    print(f"  [STEP 1] {condition_a}: {len(patients_a)} patients, "
          f"{condition_b}: {len(patients_b)} patients, "
          f"overlap: {len(overlap)}\n")

    # Step 2: Get drug usage for each cohort
    print("  [STEP 2] Gathering prescription data per cohort...")

    async def get_cohort_drugs(patient_nodes):
        drugs = {}
        for pnode in patient_nodes:
            pid = int(pnode.split(":")[1])
            rxs = await call_mcp(session, "get_prescriptions", {"patient_id": pid})
            if isinstance(rxs, list):
                for rx in rxs:
                    if rx.get("status") == "active":
                        name = rx["drug_name"]
                        drugs[name] = drugs.get(name, 0) + 1
        return drugs

    drugs_a = await get_cohort_drugs(patients_a)
    drugs_b = await get_cohort_drugs(patients_b)

    print(f"    {condition_a} drugs: {drugs_a}")
    print(f"    {condition_b} drugs: {drugs_b}\n")

    # Step 3: Claude compares (LLM reasoning)
    print("  [STEP 3] Claude comparing cohorts...\n")

    comparison = call_claude(client, f"""You are a clinical analyst. Compare these two patient cohorts concisely (2-3 paragraphs).

Cohort A: {condition_a} ({len(patients_a)} patients)
  Active drugs: {json.dumps(drugs_a)}

Cohort B: {condition_b} ({len(patients_b)} patients)
  Active drugs: {json.dumps(drugs_b)}

Overlap: {len(overlap)} patients have BOTH conditions

Compare: prescribing patterns, drug overlap, potential risks from managing both conditions.
Note any concerns about patients in the overlap group.""")

    # Step 4: Format
    sections = [
        f"**{condition_a.replace('_', ' ').title()}**: {len(patients_a)} patients\n"
        f"Active drugs: {', '.join(f'{d} ({c})' for d, c in sorted(drugs_a.items(), key=lambda x: -x[1]))}",

        f"**{condition_b.replace('_', ' ').title()}**: {len(patients_b)} patients\n"
        f"Active drugs: {', '.join(f'{d} ({c})' for d, c in sorted(drugs_b.items(), key=lambda x: -x[1]))}",

        f"**Overlap**: {len(overlap)} patients have both conditions "
        f"({round(len(overlap) / max(len(patients_a | patients_b), 1) * 100)}% of combined population)",

        f"**Analysis:**\n{comparison}",
    ]

    return format_report(
        f"Cohort Comparison: {condition_a.replace('_', ' ').title()} vs {condition_b.replace('_', ' ').title()}",
        sections,
    )


# Registry of available workflows
WORKFLOWS = {
    "safety_review": {
        "name": "Medication Safety Review",
        "description": "Check all patients for drug interaction risks",
        "function": medication_safety_review,
    },
    "drug_utilization": {
        "name": "Drug Utilization Report",
        "description": "Analyze prescribing patterns across the clinic",
        "function": drug_utilization_report,
    },
    "cohort_comparison": {
        "name": "Patient Cohort Comparison",
        "description": "Compare diabetes vs hypertension patient cohorts",
        "function": patient_cohort_comparison,
    },
}
