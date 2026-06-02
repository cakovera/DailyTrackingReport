from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd


TABLE_NAME = "repair_rates"
DB_PATH = Path(os.getenv("REPAIR_DB_PATH", str(Path("data") / "daily_repair_rate.sqlite")))


SCHEMA = """
CREATE TABLE IF NOT EXISTS repair_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    project_no TEXT NOT NULL,
    dimensions TEXT NOT NULL,
    qty REAL NOT NULL,
    project_total_pipe_length REAL NOT NULL,
    repaired_pipes_total_length REAL NOT NULL,
    repaired_spiral_length REAL NOT NULL,
    total_repair_amount REAL NOT NULL,
    total_repair_amount_incl_skelp REAL NOT NULL,
    project_status TEXT NOT NULL,
    repair_ratio REAL NOT NULL,
    repair_ratio_incl_skelp REAL NOT NULL,
    UNIQUE(date, project_no, dimensions)
);
"""


UPSERT_SQL = """
INSERT INTO repair_rates (
    date, project_no, dimensions, qty, project_total_pipe_length,
    repaired_pipes_total_length, repaired_spiral_length, total_repair_amount,
    total_repair_amount_incl_skelp, project_status, repair_ratio,
    repair_ratio_incl_skelp
) VALUES (
    :date, :project_no, :dimensions, :qty, :project_total_pipe_length,
    :repaired_pipes_total_length, :repaired_spiral_length, :total_repair_amount,
    :total_repair_amount_incl_skelp, :project_status, :repair_ratio,
    :repair_ratio_incl_skelp
)
ON CONFLICT(date, project_no, dimensions) DO UPDATE SET
    qty = excluded.qty,
    project_total_pipe_length = excluded.project_total_pipe_length,
    repaired_pipes_total_length = excluded.repaired_pipes_total_length,
    repaired_spiral_length = excluded.repaired_spiral_length,
    total_repair_amount = excluded.total_repair_amount,
    total_repair_amount_incl_skelp = excluded.total_repair_amount_incl_skelp,
    project_status = excluded.project_status,
    repair_ratio = excluded.repair_ratio,
    repair_ratio_incl_skelp = excluded.repair_ratio_incl_skelp;
"""


def _get_config_value(name: str) -> str | None:
    env_value = os.getenv(name)
    if env_value:
        return env_value

    try:
        import streamlit as st

        return st.secrets.get(name)
    except Exception:
        return None


def get_backend_name() -> str:
    if _get_config_value("SUPABASE_URL") and _get_config_value("SUPABASE_KEY"):
        return "supabase"
    return "sqlite"


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _get_supabase_client():
    try:
        from supabase import create_client
    except ImportError as exc:
        raise RuntimeError("Supabase backend selected but 'supabase' package is not installed.") from exc

    url = _get_config_value("SUPABASE_URL")
    key = _get_config_value("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set for Supabase backend.")
    return create_client(url, key)


def init_db(conn: sqlite3.Connection | None = None) -> None:
    if get_backend_name() == "supabase":
        return

    should_close = conn is None
    conn = conn or get_connection()
    conn.execute(SCHEMA)
    conn.commit()
    if should_close:
        conn.close()


def _records_from_df(df: pd.DataFrame) -> list[dict[str, Any]]:
    write_df = df.drop(columns=["excel_row", "id"], errors="ignore").copy()
    write_df["date"] = pd.to_datetime(write_df["date"]).dt.strftime("%Y-%m-%d")
    records = write_df.where(pd.notna(write_df), None).to_dict(orient="records")
    return records


def get_existing_keys(df: pd.DataFrame, conn: sqlite3.Connection | None = None) -> set[tuple[str, str, str]]:
    if df.empty:
        return set()

    dates = sorted(set(pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")))

    if get_backend_name() == "supabase":
        client = _get_supabase_client()
        response = (
            client.table(TABLE_NAME)
            .select("date,project_no,dimensions")
            .in_("date", dates)
            .execute()
        )
        return {(row["date"], row["project_no"], row["dimensions"]) for row in response.data}

    should_close = conn is None
    conn = conn or get_connection()
    init_db(conn)
    placeholders = ",".join("?" for _ in dates)
    rows = conn.execute(
        f"SELECT date, project_no, dimensions FROM repair_rates WHERE date IN ({placeholders})",
        dates,
    ).fetchall()
    if should_close:
        conn.close()
    return {(row["date"], row["project_no"], row["dimensions"]) for row in rows}


def upsert_repair_rates(df: pd.DataFrame, conn: sqlite3.Connection | None = None) -> int:
    records = _records_from_df(df)

    if get_backend_name() == "supabase":
        client = _get_supabase_client()
        client.table(TABLE_NAME).upsert(records, on_conflict="date,project_no,dimensions").execute()
        return len(records)

    should_close = conn is None
    conn = conn or get_connection()
    init_db(conn)
    conn.executemany(UPSERT_SQL, records)
    conn.commit()
    if should_close:
        conn.close()
    return len(records)


def load_master_data(conn: sqlite3.Connection | None = None) -> pd.DataFrame:
    if get_backend_name() == "supabase":
        client = _get_supabase_client()
        response = client.table(TABLE_NAME).select("*").order("date").execute()
        df = pd.DataFrame(response.data)
    else:
        should_close = conn is None
        conn = conn or get_connection()
        init_db(conn)
        df = pd.read_sql_query("SELECT * FROM repair_rates ORDER BY date, project_no, dimensions", conn)
        if should_close:
            conn.close()

    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df
