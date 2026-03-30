"""Database connection helper for the clinic database."""

import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    """Create a new database connection using environment variables."""
    return psycopg2.connect(
        host=os.getenv("CLINIC_DB_HOST", "localhost"),
        port=int(os.getenv("CLINIC_DB_PORT", "5432")),
        dbname=os.getenv("CLINIC_DB_NAME", "clinic"),
        user=os.getenv("CLINIC_DB_USER", "clinic_user"),
        password=os.getenv("CLINIC_DB_PASSWORD", "clinic_pass"),
    )


def execute_query(sql: str, params: tuple = None) -> list[dict]:
    """Execute a SELECT query and return results as a list of dicts."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()
