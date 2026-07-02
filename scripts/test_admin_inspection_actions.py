#!/usr/bin/env python3
"""Print or call admin inspection action endpoints."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "http://localhost:8000"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show curl commands or call admin inspection action endpoints."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--inspection-id", type=int)
    parser.add_argument(
        "--call",
        choices=("pending", "mark-failed", "retry"),
        help="Optionally call one endpoint instead of only printing curl commands.",
    )
    return parser.parse_args()


def clean_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def print_curl_commands(base_url: str, inspection_id: Optional[int]) -> None:
    print("List pending inspections:")
    print(f'curl "{base_url}/api/admin/inspections/pending"')
    print()

    sample_id = inspection_id if inspection_id is not None else 123
    print("Mark one inspection failed:")
    print(f'curl -X POST "{base_url}/api/admin/inspections/{sample_id}/mark-failed"')
    print()

    print("Retry one inspection:")
    print(f'curl -X POST "{base_url}/api/admin/inspections/{sample_id}/retry"')
    if inspection_id is None:
        print()
        print("Tip: pass --inspection-id to replace the sample id.")


def request_json(url: str, method: str = "GET") -> int:
    request = Request(url, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            parsed = json.loads(body) if body else {}
            print(json.dumps(parsed, indent=2, ensure_ascii=False))
            return 0
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}: {body}")
        return 1
    except URLError as exc:
        print(f"Request failed: {exc}")
        return 1


def main() -> int:
    args = parse_args()
    base_url = clean_base_url(args.base_url)

    if not args.call:
        print_curl_commands(base_url, args.inspection_id)
        return 0

    if args.call == "pending":
        return request_json(f"{base_url}/api/admin/inspections/pending")

    if args.inspection_id is None:
        print("--inspection-id is required for mark-failed and retry.")
        return 2

    if args.call == "mark-failed":
        url = f"{base_url}/api/admin/inspections/{args.inspection_id}/mark-failed"
        return request_json(url, method="POST")

    if args.call == "retry":
        url = f"{base_url}/api/admin/inspections/{args.inspection_id}/retry"
        return request_json(url, method="POST")

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
