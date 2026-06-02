from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from database import DB_PATH, get_backend_name, upsert_repair_rates


def main() -> None:
    if get_backend_name() != "supabase":
        raise SystemExit("Supabase secrets are not configured. Migration requires SUPABASE_URL and SUPABASE_KEY.")

    sqlite_path = Path(DB_PATH)
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite database not found: {sqlite_path}")

    with sqlite3.connect(sqlite_path) as conn:
        df = pd.read_sql_query("SELECT * FROM repair_rates ORDER BY date, project_no, dimensions", conn)

    if df.empty:
        print("No SQLite rows to migrate.")
        return

    migrated = upsert_repair_rates(df)
    print(f"Migrated {migrated} rows from {sqlite_path} to Supabase.")


if __name__ == "__main__":
    main()
