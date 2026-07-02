#!/usr/bin/env python3
"""Check ShelfAuditAI readiness endpoints."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

DEFAULT_BASE_URL = "http://localhost:8000"
ENDPOINTS = [
    ("overall", "/health"),
    ("database", "/health/db"),
    ("rabbitmq", "/health/rabbitmq"),
    ("models", "/health/models"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check backend health endpoints.")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Backend base URL. Default: {DEFAULT_BASE_URL}",
    )
    return parser.parse_args()


def fetch_json(url: str) -> Tuple[bool, Dict[str, Any]]:
    try:
        with urlopen(url, timeout=20) as response:
            body = response.read().decode("utf-8")
            return True, json.loads(body)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return False, {"status": "error", "message": f"HTTP {exc.code}: {body}"}
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return False, {"status": "error", "message": str(exc)}


def print_component(name: str, payload: Dict[str, Any]) -> None:
    status = payload.get("status", "unknown")
    message = payload.get("message", "")
    print(f"{name}: {status}")
    if message:
        print(f"  message: {message}")

    if name == "overall":
        print(f"  analysis_mode: {payload.get('analysis_mode', '-')}")
        print(f"  timestamp: {payload.get('timestamp', '-')}")
    elif name == "database":
        print(f"  mode: {payload.get('mode', '-')}")
    elif name == "rabbitmq":
        print(f"  host: {payload.get('host', '-')}")
        print(f"  port: {payload.get('port', '-')}")
        print(f"  queue: {payload.get('queue', '-')}")
    elif name == "models":
        missing = payload.get("missing") or []
        if missing:
            print(f"  missing: {', '.join(str(item) for item in missing)}")
        for model in payload.get("models", []):
            print(
                "  model: "
                f"{model.get('name')} "
                f"status={model.get('status')} "
                f"size={model.get('size_bytes')} "
                f"path={model.get('path')}"
            )


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    results: Dict[str, Dict[str, Any]] = {}
    had_request_error = False

    for name, path in ENDPOINTS:
        ok, payload = fetch_json(f"{base_url}{path}")
        had_request_error = had_request_error or not ok
        results[name] = payload

    print(f"Base URL: {base_url}")
    for name, _path in ENDPOINTS:
        print_component(name, results[name])

    overall_status = str(results.get("overall", {}).get("status", "error"))
    if had_request_error or overall_status == "error":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
