"""The 6 constant test queries used across all phases."""

TEST_QUERIES = [
    {
        "id": 1,
        "query": "What data do we have?",
        "tests": "Baseline discovery — how well does the system describe its own data.",
    },
    {
        "id": 2,
        "query": "Tell me about our prescription data and how it connects to drug information.",
        "tests": "Cross-source depth — can it explain the bridge between clinic and FDA data.",
    },
    {
        "id": 3,
        "query": "Are any of our patients on drugs that have known FDA interaction warnings?",
        "tests": "The money query — requires cross-referencing private prescriptions with public drug data.",
    },
    {
        "id": 4,
        "query": "Find anything related to cardiovascular health.",
        "tests": "Semantic breadth — can it find relevant data across multiple tables and sources.",
    },
    {
        "id": 5,
        "query": "Review Patient 1's current medications for potential risks.",
        "tests": "Full integration — specific patient lookup + FDA data + interaction check + reasoning.",
    },
    {
        "id": 6,
        "query": "What are the most critical data relationships in our system?",
        "tests": "Graph analysis — understanding the schema structure and what connects to what.",
    },
]
