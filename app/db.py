"""Accès base de données SÉCURISÉ : connexion en lecture seule + validation des requêtes."""
import re
import sqlite3
from pathlib import Path

from . import config

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|pragma|vacuum|reindex)\b", re.I)

DOMAIN_HINTS = (
    "\nHints (demo sales DB): revenue = SUM(oi.quantity * p.unit_price * (1 - oi.discount)); "
    "margin = SUM(oi.quantity * (p.unit_price * (1 - oi.discount) - p.cost)); "
    "month = strftime('%Y-%m', o.order_date). Amounts are in MAD."
)


def connect_ro(path=None):
    p = Path(path or config.DB_PATH).resolve()
    return sqlite3.connect(f"{p.as_uri()}?mode=ro", uri=True, check_same_thread=False)


def validate_sql(query: str) -> str:
    q = (query or "").strip().rstrip(";").strip()
    if not q:
        raise ValueError("Empty query.")
    if ";" in q:
        raise ValueError("Only one statement is allowed.")
    if not re.match(r"^(select|with)\b", q, re.I):
        raise ValueError("Only SELECT queries are allowed.")
    if FORBIDDEN.search(q):
        raise ValueError("Forbidden keyword detected: read-only access.")
    return q


def run_query(conn, query, max_rows=None):
    max_rows = max_rows or config.MAX_ROWS
    cur = conn.execute(validate_sql(query))
    cols = [d[0] for d in cur.description]
    rows = [list(r) for r in cur.fetchmany(max_rows + 1)]
    truncated = len(rows) > max_rows
    return cols, rows[:max_rows], truncated


def schema_description(conn) -> str:
    out = []
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    for t in tables:
        cols = [f"{c[1]} {c[2]}" for c in conn.execute(f"PRAGMA table_info({t})")]
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        sample = conn.execute(f"SELECT * FROM {t} LIMIT 2").fetchall()
        out.append(f"TABLE {t} ({n} rows): {', '.join(cols)}\n  sample: {sample}")
    return "\n".join(out) + DOMAIN_HINTS
