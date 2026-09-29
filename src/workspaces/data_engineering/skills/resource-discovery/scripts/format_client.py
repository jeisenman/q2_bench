#!/usr/bin/env python3
"""Format cached client identities for production-support messages."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

DEFAULT_LOOKUP = (
    Path(__file__).resolve().parents[1] / "references" / "client-guuid-lookup.json"
)
AUTHORITATIVE_SOURCES = {"resource-discovery-api", "user-confirmed"}


def load_lookup(path: Path) -> dict[str, dict[str, Any]]:
    """Load the non-secret client lookup."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"expected a JSON object in {path}")
    return payload


def format_identity(
    client_uuid: str,
    entry: dict[str, Any] | None,
    style: str,
) -> dict[str, Any]:
    """Return one resolved or unresolved client label."""
    normalized = str(UUID(client_uuid))
    source = entry.get("source") if entry else None
    api_status = entry.get("api_status") if entry else "missing"
    name = entry.get("name") if entry else None
    resolved = (
        isinstance(name, str)
        and bool(name.strip())
        and source in AUTHORITATIVE_SOURCES
        and (api_status == "unique-match" or source == "user-confirmed")
    )
    if resolved:
        suffix = normalized if style == "developer" else normalized[:3]
        label = f"{name} ({suffix})"
    else:
        suffix = normalized if style == "developer" else normalized[:3]
        label = f"Unresolved client ({suffix})"
    return {
        "uuid": normalized,
        "name": name if resolved else None,
        "resolved": resolved,
        "label": label,
        "source": source or "missing",
        "api_status": api_status,
        "prod_support_ignore": bool(entry and entry.get("prod_support_ignore")),
    }


def main() -> int:
    """Format one or more UUIDs from the maintained lookup."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client_uuid", nargs="+")
    parser.add_argument(
        "--style",
        choices=("developer", "channel"),
        default="developer",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--lookup", type=Path, default=DEFAULT_LOOKUP)
    args = parser.parse_args()
    try:
        lookup = load_lookup(args.lookup)
        results = [
            format_identity(value, lookup.get(str(UUID(value))), args.style)
            for value in args.client_uuid
        ]
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    if args.json:
        selected: object = results[0] if len(results) == 1 else results
        print(json.dumps(selected, indent=2, sort_keys=True))
    else:
        for result in results:
            print(result["label"])
    return 0 if all(result["resolved"] for result in results) else 2


if __name__ == "__main__":
    sys.exit(main())
