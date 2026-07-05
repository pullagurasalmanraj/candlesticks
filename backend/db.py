import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import os

# -------------------------------------------------
# Load environment variables from .env
# -------------------------------------------------
# Load environment variables from root and local paths
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"), override=False)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=False)
load_dotenv(override=False)

# -------------------------------------------------
# Database configuration
# -------------------------------------------------
# Prioritize PG* variables or fall back to DB_* variables
DB_CONFIG = {
    "dbname": os.getenv("PGDATABASE") or os.getenv("DB_NAME") or "trading_db",
    "user": os.getenv("PGUSER") or os.getenv("DB_USER") or "postgres",
    "password": os.getenv("PGPASSWORD") or os.getenv("DB_PASSWORD") or "postgres",
    "host": os.getenv("PGHOST") or os.getenv("DB_HOST") or "127.0.0.1",
    "port": os.getenv("PGPORT") or os.getenv("DB_PORT") or "5432",
}

# -------------------------------------------------
# Connection helper
# -------------------------------------------------
def get_db_conn():
    """
    Returns a new PostgreSQL connection.
    Caller must close it.
    """
    return psycopg2.connect(
        **DB_CONFIG,
        cursor_factory=RealDictCursor
    )


# -------------------------------------------------
# SQL Execution & Helper Utils
# -------------------------------------------------
def read_sql_safe(sql, conn, params=None):
    """
    Replaces pd.read_sql for raw psycopg2 RealDictCursor connections.
    pd.read_sql with psycopg2 returns column names as data values.
    RealDictCursor returns dict rows --- pd.DataFrame handles them natively.
    Also converts Decimal -> float and None -> NaN.
    """
    import decimal
    import pandas as pd

    with conn.cursor() as cur:
        cur.execute(sql, params or [])
        rows = cur.fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(r) for r in rows])
    for col in df.columns:
        first_valid = next((v for v in df[col] if v is not None), None)
        if isinstance(first_valid, (decimal.Decimal, int, float)):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def chunk_execute(cur, sql, rows, chunk_size=5000):
    """Batch execute_values in chunks to avoid memory spikes."""
    import math
    import numpy as np
    from psycopg2.extras import execute_values

    def _to_db_scalar(v):
        # psycopg2 does not reliably adapt numpy scalar types (numpy>=2 can
        # render repr like np.float64(...)), so normalize to native Python.
        if isinstance(v, np.generic):
            v = v.item()
        # Normalize NaN/Inf to NULL for safer inserts across numeric columns.
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return v

    total = len(rows)
    for offset in range(0, total, chunk_size):
        chunk = rows[offset : offset + chunk_size]
        cleaned = [tuple(_to_db_scalar(x) for x in row) for row in chunk]
        execute_values(cur, sql, cleaned)


