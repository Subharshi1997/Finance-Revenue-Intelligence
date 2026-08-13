"""Builds the SQLite finance database from the cleaned tables in
data/processed/ and applies sql/schema.sql (tables, constraints, indexes).

Run from the project root:
    python -m src.utils.db
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"
SCHEMA_PATH = ROOT / "sql" / "schema.sql"
DB_PATH = ROOT / "data" / "finance_ops.db"

# Parent-before-child load order, matching the foreign keys in schema.sql.
TABLE_LOAD_ORDER = [
    "merchants",
    "contracts",
    "transactions",
    "invoices",
    "payments",
    "refunds",
    "credit_notes",
    "collection_activity",
    "disputes",
]


def get_engine(db_path: Path = DB_PATH):
    return create_engine(f"sqlite:///{db_path}")


def apply_schema(engine) -> None:
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys = OFF"))
        for statement in schema_sql.split(";"):
            statement = statement.strip()
            if statement:
                conn.execute(text(statement))


def load_table(engine, table_name: str) -> int:
    df = pd.read_csv(PROCESSED_DIR / f"{table_name}.csv")
    if "invoice_error_flag" in df.columns:
        df["invoice_error_flag"] = df["invoice_error_flag"].astype(int)
    df.to_sql(table_name, engine, if_exists="append", index=False)
    return len(df)


def build_database() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()

    engine = get_engine()
    print(f"Applying schema to {DB_PATH}")
    apply_schema(engine)

    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys = ON"))

    for table in TABLE_LOAD_ORDER:
        n = load_table(engine, table)
        print(f"  loaded {table}: {n:,} rows")

    with engine.connect() as conn:
        fk_violations = conn.execute(text("PRAGMA foreign_key_check")).fetchall()
    if fk_violations:
        raise RuntimeError(f"Foreign key violations found after load: {fk_violations}")
    print("Foreign key check passed: no violations.")


if __name__ == "__main__":
    build_database()
