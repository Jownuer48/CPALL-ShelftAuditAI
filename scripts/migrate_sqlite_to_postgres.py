#!/usr/bin/env python3
"""Copy existing inspection records from SQLite into PostgreSQL."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
DEFAULT_SQLITE_DB = BACKEND_DIR / "shelf_audit.db"
DEFAULT_POSTGRES_URL = (
    "postgresql+psycopg2://shelf_user:shelf_password@localhost:5432/shelf_audit"
)

INSPECTION_COLUMNS = [
    "id",
    "branch_code",
    "image_name",
    "detected_model",
    "model_score",
    "result",
    "missing_count",
    "missing_items_json",
    "status",
    "error_message",
    "annotated_image_name",
    "created_at",
    "updated_at",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate inspection rows from backend/shelf_audit.db to PostgreSQL."
    )
    parser.add_argument(
        "--sqlite-db",
        type=Path,
        default=DEFAULT_SQLITE_DB,
        help=f"Source SQLite database. Default: {DEFAULT_SQLITE_DB}",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL") or DEFAULT_POSTGRES_URL,
        help="Target PostgreSQL URL. Defaults to DATABASE_URL or local Docker Compose Postgres.",
    )
    return parser.parse_args()


def normalize_postgres_url(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg2://"):
        return "postgresql://" + database_url[len("postgresql+psycopg2://") :]
    return database_url


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def ensure_postgres_schema(database_url: str) -> None:
    os.environ["DATABASE_URL"] = database_url
    sys.path.insert(0, str(BACKEND_DIR))

    from database import init_db

    init_db()


def connect_sqlite(sqlite_db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(sqlite_db)
    conn.row_factory = sqlite3.Row
    return conn


def connect_postgres(database_url: str):
    try:
        import psycopg2
    except ImportError as exc:
        raise RuntimeError(
            "psycopg2-binary is required. Install backend/requirements.txt first."
        ) from exc

    return psycopg2.connect(normalize_postgres_url(database_url))


def sqlite_table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'inspections'"
    ).fetchone()
    return row is not None


def sqlite_columns(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("PRAGMA table_info(inspections)").fetchall()
    return {row["name"] for row in rows}


def postgres_columns(conn: Any) -> set[str]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'inspections'
            """
        )
        return {row[0] for row in cursor.fetchall()}


def fetch_sqlite_rows(
    conn: sqlite3.Connection,
    columns: List[str],
) -> List[sqlite3.Row]:
    column_sql = ", ".join(columns)
    return conn.execute(f"SELECT {column_sql} FROM inspections ORDER BY id").fetchall()


def reset_postgres_sequence(conn: Any) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT setval(
                pg_get_serial_sequence('inspections', 'id'),
                GREATEST(COALESCE((SELECT MAX(id) FROM inspections), 1), 1),
                (SELECT COUNT(*) FROM inspections) > 0
            )
            """
        )
    conn.commit()


def migrate(sqlite_db: Path, database_url: str) -> Dict[str, int]:
    sqlite_db = resolve_path(sqlite_db)
    if not sqlite_db.exists():
        raise FileNotFoundError(f"SQLite database not found: {sqlite_db}")

    if database_url.lower().startswith("sqlite:"):
        raise ValueError("Target database URL must be PostgreSQL, not SQLite.")

    ensure_postgres_schema(database_url)

    summary = {"copied": 0, "skipped": 0, "errors": 0}
    sqlite_conn = None
    pg_conn = None

    try:
        sqlite_conn = connect_sqlite(sqlite_db)
        pg_conn = connect_postgres(database_url)

        if not sqlite_table_exists(sqlite_conn):
            print("SQLite inspections table was not found. Nothing to migrate.")
            return summary

        source_columns = sqlite_columns(sqlite_conn)
        target_columns = postgres_columns(pg_conn)
        copy_columns = [
            column
            for column in INSPECTION_COLUMNS
            if column in source_columns and column in target_columns
        ]

        if "id" not in copy_columns:
            raise RuntimeError("Both source and target inspections tables must have an id column.")

        rows = fetch_sqlite_rows(sqlite_conn, copy_columns)
        if not rows:
            print("SQLite inspections table is empty. Nothing to migrate.")
            return summary

        column_sql = ", ".join(copy_columns)
        placeholders = ", ".join(["%s"] * len(copy_columns))
        insert_sql = (
            f"INSERT INTO inspections ({column_sql}) "
            f"VALUES ({placeholders}) "
            "ON CONFLICT (id) DO NOTHING"
        )

        for row in rows:
            values = [row[column] for column in copy_columns]
            row_id = row["id"]
            try:
                with pg_conn.cursor() as cursor:
                    cursor.execute(insert_sql, values)
                    if cursor.rowcount == 0:
                        summary["skipped"] += 1
                    else:
                        summary["copied"] += 1
                pg_conn.commit()
            except Exception as exc:
                pg_conn.rollback()
                summary["errors"] += 1
                print(f"ERROR id={row_id}: {exc}")

        reset_postgres_sequence(pg_conn)
        return summary
    finally:
        if sqlite_conn is not None:
            sqlite_conn.close()
        if pg_conn is not None:
            pg_conn.close()


def main() -> int:
    args = parse_args()
    database_url = args.database_url.strip()

    try:
        summary = migrate(args.sqlite_db, database_url)
    except Exception as exc:
        print(f"Migration failed: {exc}")
        return 1

    print("Migration summary")
    print(f"copied : {summary['copied']}")
    print(f"skipped: {summary['skipped']}")
    print(f"errors : {summary['errors']}")
    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
