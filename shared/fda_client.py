"""FDA openFDA API client for drug lookups and adverse events."""

import json
import os
import httpx

FDA_BASE_URL = "https://api.fda.gov"
CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "fda-cache-seed.json")


def _load_cache() -> dict:
    """Load pre-fetched FDA data for offline use."""
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH) as f:
            return json.load(f)
    return {}


def _fda_get(endpoint: str, params: dict) -> dict | None:
    """Make a GET request to the FDA API with fallback to cache."""
    try:
        response = httpx.get(
            f"{FDA_BASE_URL}{endpoint}",
            params=params,
            timeout=10.0,
        )
        if response.status_code == 200:
            return response.json()
        return None
    except (httpx.RequestError, httpx.TimeoutException):
        return None


def lookup_drug(name: str) -> dict | None:
    """Look up a drug by name. Returns label information."""
    result = _fda_get("/drug/label.json", {
        "search": f'openfda.brand_name:"{name}"+openfda.generic_name:"{name}"',
        "limit": 1,
    })

    if result and result.get("results"):
        drug = result["results"][0]
        openfda = drug.get("openfda", {})
        return {
            "brand_name": openfda.get("brand_name", ["Unknown"])[0],
            "generic_name": openfda.get("generic_name", ["Unknown"])[0],
            "manufacturer": openfda.get("manufacturer_name", ["Unknown"])[0],
            "product_ndc": openfda.get("product_ndc", []),
            "route": openfda.get("route", ["Unknown"])[0],
            "substance_name": openfda.get("substance_name", []),
            "pharm_class": openfda.get("pharm_class_epc", []),
            "indications": (drug.get("indications_and_usage") or ["Not available"])[0][:500],
            "warnings": (drug.get("warnings") or drug.get("warnings_and_cautions") or ["Not available"])[0][:500],
            "drug_interactions_text": (drug.get("drug_interactions") or ["Not available"])[0][:500],
            "adverse_reactions": (drug.get("adverse_reactions") or ["Not available"])[0][:500],
        }

    # Fallback to cache
    cache = _load_cache()
    return cache.get("drugs", {}).get(name.lower())


def search_adverse_events(drug_name: str, limit: int = 5) -> list[dict]:
    """Search FDA adverse event reports for a drug."""
    result = _fda_get("/drug/event.json", {
        "search": f'patient.drug.openfda.generic_name:"{drug_name}"',
        "limit": limit,
    })

    if result and result.get("results"):
        events = []
        for report in result["results"]:
            patient = report.get("patient", {})
            reactions = [r.get("reactionmeddrapt", "Unknown")
                         for r in patient.get("reaction", [])]
            drugs = [d.get("medicinalproduct", "Unknown")
                     for d in patient.get("drug", [])]
            events.append({
                "report_id": report.get("safetyreportid"),
                "serious": report.get("serious") == "1",
                "reactions": reactions,
                "drugs_involved": drugs,
                "patient_age": patient.get("patientonsetage"),
                "patient_sex": {"1": "Male", "2": "Female"}.get(
                    patient.get("patientsex"), "Unknown"
                ),
            })
        return events

    return []


def get_adverse_event_counts(drug_name: str) -> dict | None:
    """Get count of adverse events for a drug by reaction type."""
    result = _fda_get("/drug/event.json", {
        "search": f'patient.drug.openfda.generic_name:"{drug_name}"',
        "count": "patient.reaction.reactionmeddrapt.exact",
        "limit": 10,
    })

    if result and result.get("results"):
        return {
            "drug": drug_name,
            "top_reactions": [
                {"reaction": r["term"], "count": r["count"]}
                for r in result["results"]
            ],
            "total_reports": result.get("meta", {}).get("results", {}).get("total"),
        }

    return None
