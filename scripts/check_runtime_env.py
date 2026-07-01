#!/usr/bin/env python3
"""Print and optionally validate the ShelfAuditAI Python runtime environment."""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path
from typing import Iterable, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"

DISPLAY_PACKAGES = ("psycopg2", "streamlit", "sqlalchemy")
STARTUP_PACKAGES = (
    "psycopg2",
    "fastapi",
    "streamlit",
    "sqlalchemy",
    "pika",
    "cv2",
    "pandas",
    "ultralytics",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Python runtime dependencies.")
    parser.add_argument(
        "--require-startup",
        action="store_true",
        help="Require all packages needed by start_all.cmd and exit non-zero if any are missing.",
    )
    return parser.parse_args()


def database_mode() -> str:
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    try:
        from database import get_database_backend

        return get_database_backend()
    except Exception as exc:
        return f"error ({exc})"


def import_status(module_name: str) -> Tuple[bool, str]:
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        return False, f"MISSING ({exc.__class__.__name__}: {exc})"

    version = getattr(module, "__version__", None)
    if version:
        return True, f"ok ({version})"
    return True, "ok"


def print_package_status(package_names: Iterable[str]) -> bool:
    all_ok = True
    for package_name in package_names:
        ok, status = import_status(package_name)
        all_ok = all_ok and ok
        print(f"{package_name}: {status}")
    return all_ok


def main() -> int:
    args = parse_args()
    package_names = STARTUP_PACKAGES if args.require_startup else DISPLAY_PACKAGES

    print(f"python: {sys.executable}")
    print(f"DATABASE_URL mode: {database_mode()}")
    print(
        "SHELF_AUDIT_ANALYSIS_MODE: "
        f"{os.getenv('SHELF_AUDIT_ANALYSIS_MODE', '') or '(not set)'}"
    )

    all_ok = print_package_status(package_names)
    if args.require_startup and not all_ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
