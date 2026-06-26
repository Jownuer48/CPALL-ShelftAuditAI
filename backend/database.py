import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "shelf_audit.db")


def utc_now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _table_columns(conn: sqlite3.Connection) -> Dict[str, sqlite3.Row]:
    rows = conn.execute("PRAGMA table_info(inspections)").fetchall()
    return {row["name"]: row for row in rows}


def _add_column_if_missing(
    conn: sqlite3.Connection,
    columns: Dict[str, sqlite3.Row],
    name: str,
    definition: str,
) -> None:
    if name not in columns:
        conn.execute(f"ALTER TABLE inspections ADD COLUMN {name} {definition}")
        columns[name] = conn.execute(
            "PRAGMA table_info(inspections)"
        ).fetchall()[-1]


def init_db() -> None:
    os.makedirs(BASE_DIR, exist_ok=True)

    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS inspections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                branch_code TEXT NOT NULL,
                image_name TEXT NOT NULL,
                detected_model TEXT,
                model_score REAL,
                result TEXT,
                missing_count INTEGER DEFAULT 0,
                missing_items_json TEXT DEFAULT '[]',
                status TEXT DEFAULT 'PENDING',
                error_message TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        columns = _table_columns(conn)
        _add_column_if_missing(conn, columns, "branch_code", "TEXT NOT NULL DEFAULT ''")
        _add_column_if_missing(conn, columns, "image_name", "TEXT NOT NULL DEFAULT ''")
        _add_column_if_missing(conn, columns, "detected_model", "TEXT")
        _add_column_if_missing(conn, columns, "model_score", "REAL")
        _add_column_if_missing(conn, columns, "result", "TEXT")
        _add_column_if_missing(conn, columns, "missing_count", "INTEGER DEFAULT 0")
        _add_column_if_missing(
            conn,
            columns,
            "missing_items_json",
            "TEXT DEFAULT '[]'",
        )
        _add_column_if_missing(conn, columns, "status", "TEXT DEFAULT 'PENDING'")
        _add_column_if_missing(conn, columns, "error_message", "TEXT")
        _add_column_if_missing(conn, columns, "created_at", "TEXT")
        _add_column_if_missing(conn, columns, "updated_at", "TEXT")

        now = utc_now_text()
        conn.execute("UPDATE inspections SET status = COALESCE(status, 'PENDING')")
        conn.execute("""
            UPDATE inspections
            SET status = 'DONE'
            WHERE result IN ('PASS', 'FAIL', 'UNKNOWN_MODEL')
              AND (status IS NULL OR status = '' OR status = 'PENDING')
        """)
        conn.execute("UPDATE inspections SET missing_count = COALESCE(missing_count, 0)")
        conn.execute(
            "UPDATE inspections SET missing_items_json = COALESCE(missing_items_json, '[]')"
        )
        conn.execute("UPDATE inspections SET updated_at = COALESCE(updated_at, ?)", (now,))
        conn.commit()


def create_inspection(branch_code: str, image_name: str) -> int:
    now = utc_now_text()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO inspections (
                branch_code,
                image_name,
                detected_model,
                model_score,
                result,
                missing_count,
                missing_items_json,
                status,
                error_message,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                branch_code,
                image_name,
                "",
                0.0,
                "PENDING",
                0,
                "[]",
                "PENDING",
                None,
                now,
                now,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def update_inspection_status(
    inspection_id: int,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE inspections
            SET status = ?, error_message = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, error_message, utc_now_text(), inspection_id),
        )
        conn.commit()


def update_inspection_result(
    inspection_id: int,
    detected_model: Optional[str],
    model_score: Optional[float],
    result: str,
    missing_count: int,
    missing_items: List[Dict[str, Any]],
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE inspections
            SET
                detected_model = ?,
                model_score = ?,
                result = ?,
                missing_count = ?,
                missing_items_json = ?,
                status = 'DONE',
                error_message = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (
                detected_model,
                model_score,
                result,
                missing_count,
                json.dumps(missing_items, ensure_ascii=False),
                utc_now_text(),
                inspection_id,
            ),
        )
        conn.commit()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    item = dict(row)
    raw_missing = item.get("missing_items_json") or "[]"

    try:
        item["missing_items"] = json.loads(raw_missing)
    except (TypeError, json.JSONDecodeError):
        item["missing_items"] = []

    status = item.get("status")
    if status in ["PENDING", "PROCESSING"]:
        if item.get("detected_model") == "":
            item["detected_model"] = None
        if item.get("model_score") == 0:
            item["model_score"] = None

    item["image_url"] = f"/uploads/{item.get('image_name')}"
    return item


def get_inspection(inspection_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM inspections WHERE id = ?",
            (inspection_id,),
        ).fetchone()

    if row is None:
        return None

    return _row_to_dict(row)


def get_all_inspections(limit: int = 100) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 500))

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM inspections ORDER BY id DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()

    return [_row_to_dict(row) for row in rows]
