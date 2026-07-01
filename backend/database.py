from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import unquote

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)
DB_PATH = os.path.join(BASE_DIR, "shelf_audit.db")
DEFAULT_DATABASE_URL = "sqlite:///backend/shelf_audit.db"

POSTGRES_PREFIXES = (
    "postgresql://",
    "postgresql+psycopg2://",
    "postgres://",
)


def utc_now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_database_url() -> str:
    return (os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL).strip()


def get_database_backend(database_url: Optional[str] = None) -> str:
    url = (database_url or get_database_url()).lower()
    if url.startswith("sqlite:"):
        return "sqlite"
    if url.startswith(POSTGRES_PREFIXES):
        return "postgres"
    raise ValueError(
        "Unsupported DATABASE_URL. Use sqlite:///... or "
        "postgresql+psycopg2://user:password@host:5432/dbname."
    )


def _normalize_postgres_url(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg2://"):
        return "postgresql://" + database_url[len("postgresql+psycopg2://") :]
    return database_url


def _sqlite_path_from_url(database_url: str) -> str:
    if database_url == DEFAULT_DATABASE_URL:
        return DB_PATH

    if database_url == "sqlite:///:memory:":
        return ":memory:"

    if not database_url.startswith("sqlite:///"):
        raise ValueError("SQLite DATABASE_URL must use sqlite:///path/to/file.db")

    raw_path = unquote(database_url[len("sqlite:///") :])
    if raw_path.startswith("/") and len(raw_path) > 2 and raw_path[2] == ":":
        raw_path = raw_path[1:]

    if not os.path.isabs(raw_path):
        raw_path = os.path.join(REPO_ROOT, raw_path)

    return os.path.abspath(raw_path)


def _postgres_query(sql: str) -> str:
    return sql.replace("?", "%s")


class QueryResult:
    def __init__(self, cursor: Any, backend: str):
        self._cursor = cursor
        self._backend = backend

    @property
    def lastrowid(self) -> Optional[int]:
        if self._backend == "sqlite":
            return self._cursor.lastrowid
        return None

    def fetchone(self) -> Any:
        return self._cursor.fetchone()

    def fetchall(self) -> List[Any]:
        return self._cursor.fetchall()


class DatabaseConnection:
    def __init__(self, raw_connection: Any, backend: str):
        self._raw_connection = raw_connection
        self.backend = backend

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> QueryResult:
        if self.backend == "postgres":
            cursor = self._raw_connection.cursor()
            cursor.execute(_postgres_query(sql), params)
            return QueryResult(cursor, self.backend)

        cursor = self._raw_connection.execute(sql, params)
        return QueryResult(cursor, self.backend)

    def commit(self) -> None:
        self._raw_connection.commit()

    def rollback(self) -> None:
        self._raw_connection.rollback()

    def close(self) -> None:
        self._raw_connection.close()

    def __enter__(self) -> "DatabaseConnection":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()


def get_connection() -> DatabaseConnection:
    database_url = get_database_url()
    backend = get_database_backend(database_url)

    if backend == "sqlite":
        sqlite_path = _sqlite_path_from_url(database_url)
        if sqlite_path != ":memory:":
            os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)

        conn = sqlite3.connect(sqlite_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return DatabaseConnection(conn, backend)

    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError as exc:
        raise RuntimeError(
            "PostgreSQL DATABASE_URL requires psycopg2-binary. "
            "Run: backend\\.venv\\Scripts\\pip.exe install -r backend\\requirements.txt"
        ) from exc

    conn = psycopg2.connect(
        _normalize_postgres_url(database_url),
        cursor_factory=RealDictCursor,
    )
    return DatabaseConnection(conn, backend)


def _table_columns(conn: DatabaseConnection) -> Dict[str, Any]:
    if conn.backend == "postgres":
        rows = conn.execute(
            """
            SELECT column_name AS name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'inspections'
            """
        ).fetchall()
        return {row["name"]: row for row in rows}

    rows = conn.execute("PRAGMA table_info(inspections)").fetchall()
    return {row["name"]: row for row in rows}


def _add_column_if_missing(
    conn: DatabaseConnection,
    columns: Dict[str, Any],
    name: str,
    definition: str,
) -> None:
    if name not in columns:
        conn.execute(f"ALTER TABLE inspections ADD COLUMN {name} {definition}")
        columns[name] = {"name": name}


def _create_inspections_table_sql(backend: str) -> str:
    if backend == "postgres":
        return """
            CREATE TABLE IF NOT EXISTS inspections (
                id SERIAL PRIMARY KEY,
                branch_code TEXT NOT NULL,
                image_name TEXT NOT NULL,
                detected_model TEXT,
                model_score REAL,
                result TEXT,
                missing_count INTEGER DEFAULT 0,
                missing_items_json TEXT DEFAULT '[]',
                status TEXT DEFAULT 'PENDING',
                error_message TEXT,
                annotated_image_name TEXT,
                created_at TEXT DEFAULT (CURRENT_TIMESTAMP::text),
                updated_at TEXT DEFAULT (CURRENT_TIMESTAMP::text)
            )
            """

    return """
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
                annotated_image_name TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """


def init_db() -> None:
    os.makedirs(BASE_DIR, exist_ok=True)

    with get_connection() as conn:
        conn.execute(_create_inspections_table_sql(conn.backend))

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
        _add_column_if_missing(conn, columns, "annotated_image_name", "TEXT")
        _add_column_if_missing(conn, columns, "created_at", "TEXT")
        _add_column_if_missing(conn, columns, "updated_at", "TEXT")

        now = utc_now_text()
        conn.execute("UPDATE inspections SET status = COALESCE(status, 'PENDING')")
        conn.execute(
            """
            UPDATE inspections
            SET status = 'DONE'
            WHERE result IN ('PASS', 'FAIL', 'UNKNOWN_MODEL')
              AND (status IS NULL OR status = '' OR status = 'PENDING')
            """
        )
        conn.execute("UPDATE inspections SET missing_count = COALESCE(missing_count, 0)")
        conn.execute(
            "UPDATE inspections SET missing_items_json = COALESCE(missing_items_json, '[]')"
        )
        conn.execute("UPDATE inspections SET updated_at = COALESCE(updated_at, ?)", (now,))
        conn.commit()


def create_inspection(branch_code: str, image_name: str) -> int:
    now = utc_now_text()

    with get_connection() as conn:
        insert_sql = """
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
            """
        if conn.backend == "postgres":
            insert_sql += " RETURNING id"

        cursor = conn.execute(
            insert_sql,
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

        if conn.backend == "postgres":
            row = cursor.fetchone()
            inspection_id = int(row["id"])
        else:
            inspection_id = int(cursor.lastrowid or 0)

        conn.commit()
        return inspection_id


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
    annotated_image_name: Optional[str] = None,
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
                annotated_image_name = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                detected_model,
                model_score,
                result,
                missing_count,
                json.dumps(missing_items, ensure_ascii=False),
                annotated_image_name,
                utc_now_text(),
                inspection_id,
            ),
        )
        conn.commit()


def _row_to_dict(row: Any) -> Dict[str, Any]:
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

    item["image_url"] = f"/files/uploads/{item.get('image_name')}"

    annotated_image_name = item.get("annotated_image_name")
    item["annotated_image_url"] = (
        f"/files/annotated/{annotated_image_name}" if annotated_image_name else None
    )
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
