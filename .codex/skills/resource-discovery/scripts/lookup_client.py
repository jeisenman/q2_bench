#!/usr/bin/env python3
"""Look up a provisioned client UUID and refresh the local quick lookup."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import resource_discovery_api as api

CACHE_PATH = (
    Path(__file__).resolve().parents[1] / "references" / "client-guuid-lookup.json"
)


def load_cache() -> dict[str, dict[str, Any]]:
    if not CACHE_PATH.exists():
        return {}
    payload = json.loads(CACHE_PATH.read_text())
    if not isinstance(payload, dict):
        raise SystemExit(f"error: expected an object in {CACHE_PATH}")
    return {key: value for key, value in payload.items() if isinstance(value, dict)}


def save_cache(cache: dict[str, dict[str, Any]]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")


def records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client_uuid", help="Provisioned PrecisionLender client UUID.")
    parser.add_argument("--env-file", default=api.DEFAULT_ENV_FILE)
    parser.add_argument(
        "--confirm-name",
        help=(
            "Store this explicit user-confirmed fallback when the API has no "
            "unique name."
        ),
    )
    args = parser.parse_args()

    env_values = api.load_env_file(Path(args.env_file))
    token = api.fetch_token(
        api.env("RESOURCE_DISCOVERY_TENANT_ID", env_values),
        api.env("RESOURCE_DISCOVERY_CLIENT_ID", env_values),
        api.env("RESOURCE_DISCOVERY_CLIENT_SECRET", env_values),
        api.env("RESOURCE_DISCOVERY_SCOPE", env_values),
    )
    base_url = api.env("RESOURCE_DISCOVERY_BASE_URL", env_values)
    response = api.get_resource(
        api.build_url(
            base_url, "/api/v1/clients", [f"provisionedClientId={args.client_uuid}"]
        ),
        token,
    )

    cache = load_cache()
    entry = cache.get(args.client_uuid, {})
    names = sorted(
        {
            record["name"]
            for record in records(response)
            if isinstance(record.get("name"), str)
        }
    )
    entry["last_checked"] = date.today().isoformat()
    existing_user_confirmed_name = (
        entry.get("name") if entry.get("source") == "user-confirmed" else None
    )
    if len(names) == 1:
        entry.update(
            {
                "name": names[0],
                "source": "resource-discovery-api",
                "api_status": "unique-match",
            }
        )
    elif args.confirm_name:
        entry.update(
            {
                "name": args.confirm_name,
                "source": "user-confirmed",
                "api_status": "no-unique-match",
            }
        )
        entry.pop("api_names", None)
    elif isinstance(existing_user_confirmed_name, str):
        entry.update(
            {
                "name": existing_user_confirmed_name,
                "source": "user-confirmed",
                "api_status": "no-unique-match" if not names else "ambiguous",
            }
        )
    else:
        entry.pop("name", None)
        entry["source"] = "unresolved"
        entry["api_status"] = "no-unique-match" if not names else "ambiguous"
        if names:
            entry["api_names"] = names
        else:
            entry.pop("api_names", None)
    cache[args.client_uuid] = entry
    save_cache(cache)

    print(json.dumps(response, indent=2, sort_keys=True))
    if entry.get("name"):
        summary = (
            f"Quick lookup: {entry['name']} "
            f"({entry['source']}; API {entry['api_status']})"
        )
        print(summary)
    else:
        print(f"Quick lookup: no confirmed name (API {entry['api_status']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
