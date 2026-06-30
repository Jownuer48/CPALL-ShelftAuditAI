#!/usr/bin/env python3
"""Inspect and optionally mark stuck PENDING inspection rows as failed."""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "backend" / "shelf_audit.db"
PENDING_STATUS = "PENDING"
FAILED_STATUS = "FAILED"
FAIL_RESULT = "FAIL"
CLEANUP_REASON = "Marked failed by admin cleanup because job was stuck in PENDING."
USEFUL_COLUMNS = [
    "id",
    "image_name",
    "file_path",
    "status",
    "result",
    "created_at",
    "updated_at",
    "annotated_image_name",
]
REASON_COLUMNS = ["error_message", "reason"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find rows stuck in PENDING status and optionally mark them FAILED. "
            "Dry-run is the default."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually update PENDING rows to FAILED. Default only prints rows.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help=f"SQLite database path. Default: {DB_PATH}",
    )
    return parser.parse_args()


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    return [str(row["name"]) for row in rows]


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({quote_identifier(table)})").fetchall()
    return [str(row["name"]) for row in rows]


def status_tables(conn: sqlite3.Connection) -> dict[str, list[str]]:
    tables: dict[str, list[str]] = {}
    for table in table_names(conn):
        columns = table_columns(conn, table)
        if "status" in columns:
            tables[table] = columns
    return tables


def display_columns(columns: list[str]) -> list[str]:
    selected = [column for column in USEFUL_COLUMNS if column in columns]
    if selected:
        return selected
    return ["status"]


def pending_rows(
    conn: sqlite3.Connection,
    table: str,
    columns: list[str],
) -> list[sqlite3.Row]:
    selected = display_columns(columns)
    order_by = "id" if "id" in columns else "rowid"
    sql = (
        f"SELECT rowid AS __rowid__, {', '.join(quote_identifier(column) for column in selected)} "
        f"FROM {quote_identifier(table)} "
        "WHERE status = ? "
        f"ORDER BY {quote_identifier(order_by)}"
    )
    return conn.execute(sql, (PENDING_STATUS,)).fetchall()


def format_value(value: Any) -> str:
    if value is None:
        return "NULL"
    return str(value)


def print_pending_row(table: str, row: sqlite3.Row) -> None:
    visible = {key: row[key] for key in row.keys() if key != "__rowid__"}
    details = ", ".join(
        f"{key}={format_value(value)}" for key, value in visible.items()
    )
    print(f"  {table} rowid={row['__rowid__']}: {details}")


def update_pending_rows(
    conn: sqlite3.Connection,
    table: str,
    columns: list[str],
) -> int:
    assignments = ["status = ?"]
    values: list[Any] = [FAILED_STATUS]

    if "result" in columns:
        assignments.append("result = ?")
        values.append(FAIL_RESULT)

    for reason_column in REASON_COLUMNS:
        if reason_column in columns:
            assignments.append(f"{quote_identifier(reason_column)} = ?")
            values.append(CLEANUP_REASON)

    if "updated_at" in columns:
        assignments.append("updated_at = ?")
        values.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    values.append(PENDING_STATUS)
    sql = (
        f"UPDATE {quote_identifier(table)} "
        f"SET {', '.join(assignments)} "
        "WHERE status = ?"
    )
    cursor = conn.execute(sql, values)
    return int(cursor.rowcount)


def main() -> int:
    args = parse_args()
    db_path = args.db if args.db.is_absolute() else REPO_ROOT / args.db
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"Database: {db_path}")
    print(f"Mode: {mode}")

    with connect(db_path) as conn:
        tables = status_tables(conn)
        if not tables:
            print("No tables with a status column were found.")
            return 0

        print("Tables with status column:")
        for table in tables:
            print(f"  {table}")

        total_pending = 0
        pending_by_table: dict[str, int] = {}
        print("Pending rows:")
        for table, columns in tables.items():
            rows = pending_rows(conn, table, columns)
            pending_by_table[table] = len(rows)
            total_pending += len(rows)
            if not rows:
                print(f"  {table}: none")
                continue

            for row in rows:
                print_pending_row(table, row)

        print(f"Total PENDING rows: {total_pending}")

        if not args.apply:
            print("Dry-run only. Re-run with --apply to mark pending rows FAILED.")
            return 0

        updated_total = 0
        for table, columns in tables.items():
            if pending_by_table.get(table, 0) <= 0:
                continue
            updated_count = update_pending_rows(conn, table, columns)
            updated_total += updated_count
            print(f"Updated {table}: {updated_count} row(s)")

        conn.commit()
        print(f"Total updated rows: {updated_total}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
