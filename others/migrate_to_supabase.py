"""
migrate_to_supabase.py — one-time migration of the project's data into a
Supabase Postgres database.

Data source for each table, in order of preference:
  1. A CSV under Data/ (as in the original script), if present.
  2. Otherwise, the same-named table in the local SQLite database at
     App/data/smart_tourism.db — which is what this project actually ships
     with, so nothing needs to be exported to CSV by hand first.
  3. If neither exists, that table is skipped (reported, not an error).

This file lives in Tourism Project/others/ (a sibling of App/, not inside
it), so every path below is resolved from the file's own location — it
works no matter which directory you happen to run it from:

    pip install -r requirements-migration.txt
    python others/migrate_to_supabase.py
"""

import os
import sqlite3
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Resolved from this file's own location, not the current working
# directory — a previous version used bare relative paths ("App/data/...",
# ".env"), which only resolved correctly if launched from exactly the
# right folder. Since this script actually lives in Tourism Project/others/
# (one level below the project root, not inside it), running it as its own
# docstring instructed — "from the project root" — with those relative
# paths would look for Tourism Project/others/App/... and
# Tourism Project/others/.env, neither of which exists. That's very likely
# why SUPABASE_DB_URL was never found on prior runs.
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # .../Tourism Project
SQLITE_DB_PATH = PROJECT_ROOT / "App" / "data" / "smart_tourism.db"
DATA_DIR = PROJECT_ROOT / "Data"


def load_table(table_name: str, csv_path: Path, sqlite_conn) -> "pd.DataFrame | None":
    """CSV first (if it exists), else the same-named table in the local
    SQLite database, else None (nothing available for this table)."""
    if csv_path.exists():
        return pd.read_csv(csv_path)
    if sqlite_conn is not None:
        try:
            return pd.read_sql_query(f"SELECT * FROM {table_name}", sqlite_conn)
        except Exception:
            return None
    return None


def migrate():
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(PROJECT_ROOT / "App" / "ml1.env")

    db_url = os.getenv("SUPABASE_DB_URL")

    if not db_url:
        print(f"Error: SUPABASE_DB_URL not found in {PROJECT_ROOT / '.env'}!")
        return

    print("Connecting to Supabase PostgreSQL...")
    engine = create_engine(db_url)

    with engine.connect() as conn:
        print("Connected successfully! Testing query:", conn.execute(text("SELECT 1")).fetchall())

    sqlite_conn = None
    if SQLITE_DB_PATH.exists():
        sqlite_conn = sqlite3.connect(f"file:{SQLITE_DB_PATH.as_posix()}?mode=ro", uri=True)
        print(f"Found local SQLite database at {SQLITE_DB_PATH} — will use it for any table without a CSV.\n")
    else:
        print(f"Note: no SQLite database found at {SQLITE_DB_PATH} — only Data/*.csv files (if any) will be used.\n")

    # Map of tables to upload: table_name -> CSV path (checked first, then
    # the SQLite table of the same name). Table names match what
    # App/backend/predict.py queries today, so the backend could be pointed
    # at Supabase later without renaming anything.
    datasets = {
        "other_spots": DATA_DIR / "other spots.csv",
        "spot_visitors": DATA_DIR / "crowd_data.csv",
        "trip_budget_prediction": DATA_DIR / "trip_budget_prediction_dataset.csv",
        "transport_mode_dataset": DATA_DIR / "transport_mode_dataset.csv",
        "climate_dataset": DATA_DIR / "climate.csv",
        "accommodations": DATA_DIR / "accommodations.csv",
        "amenities": DATA_DIR / "nearby_amenities.csv",
        "festivals_geocoded": DATA_DIR / "etl" / "load" / "festivals_geocoded.csv",
    }

    print("Starting automated migration to Supabase...\n")

    for table_name, csv_path in datasets.items():
        df = load_table(table_name, csv_path, sqlite_conn)
        if df is None:
            print(f"  Skipped: no CSV at {csv_path} and no '{table_name}' table in the local SQLite database")
            continue

        source = "CSV" if os.path.exists(csv_path) else "SQLite"

        # Sanitize column names
        df.columns = [c.strip().lower().replace(" ", "_").replace("-", "_") for c in df.columns]

        # Ensure id column exists for primary key
        if "id" not in df.columns:
            df.insert(0, "id", range(1, len(df) + 1))

        df.to_sql(table_name, engine, if_exists="replace", index=False)

        # Add Primary Key constraint in PostgreSQL
        with engine.connect() as conn:
            trans = conn.begin()
            try:
                conn.execute(text(f'ALTER TABLE "{table_name}" ADD PRIMARY KEY (id);'))
                trans.commit()
            except Exception:
                trans.rollback()

        print(f"  OK: Uploaded table '{table_name}' from {source} ({len(df)} rows)")

    if sqlite_conn is not None:
        sqlite_conn.close()

    # Create user_interactions table. Dropped and recreated (not just
    # CREATE TABLE IF NOT EXISTS) because earlier runs of this script may
    # have created it with an old spot_id-based schema; this rebuilds it
    # with spot_name (TEXT), matching how every other part of the app
    # identifies spots.
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(text("DROP TABLE IF EXISTS user_interactions;"))
            conn.execute(text("""
            CREATE TABLE user_interactions (
                id SERIAL PRIMARY KEY,
                spot_name TEXT NOT NULL,
                action_type VARCHAR(50) NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """))
            trans.commit()
            print("  OK: Created table 'user_interactions'")
        except Exception as e:
            trans.rollback()
            print(f"  Error creating user_interactions: {e}")

    # Update .streamlit/secrets.toml
    streamlit_dir = PROJECT_ROOT / "App" / "frontend" / ".streamlit"
    streamlit_dir.mkdir(parents=True, exist_ok=True)
    secrets_path = streamlit_dir / "secrets.toml"

    secrets_content = f"""[connections.db]
url = "{db_url}"
"""
    secrets_path.write_text(secrets_content, encoding="utf-8")
    print(f"\nOK: Updated Streamlit database secrets in {secrets_path}")

    print("\nMigration completed successfully! Tables are now live in Supabase PostgreSQL.")


if __name__ == "__main__":
    migrate()