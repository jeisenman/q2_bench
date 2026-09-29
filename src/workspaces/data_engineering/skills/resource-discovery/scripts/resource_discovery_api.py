#!/usr/bin/env python3
"""Read from the internal Resource Discovery API using Azure client credentials."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_ENV_FILE = ".env"


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def env(name: str, env_file_values: dict[str, str]) -> str:
    value = os.environ.get(name, env_file_values.get(name))
    if value:
        return value
    raise SystemExit(f"error: {name} is required")


def fetch_token(tenant_id: str, client_id: str, client_secret: str, scope: str) -> str:
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    body = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
            "scope": scope,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        token_url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    payload = read_json(request)
    token = payload.get("access_token")
    if not isinstance(token, str):
        raise SystemExit("error: token response did not include access_token")
    return token


def read_json(request: urllib.request.Request) -> Any:
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"error: HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise SystemExit(f"error: request failed: {error.reason}") from error

    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return data.decode("utf-8", errors="replace")


def build_url(base_url: str, path: str, params: list[str]) -> str:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    query_pairs = []
    for param in params:
        if "=" not in param:
            raise SystemExit(f"error: query parameter must be key=value: {param}")
        key, value = param.split("=", 1)
        query_pairs.append((key, value))
    if query_pairs:
        separator = "&" if urllib.parse.urlparse(url).query else "?"
        url = url + separator + urllib.parse.urlencode(query_pairs)
    return url


def get_resource(url: str, token: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        method="GET",
    )
    return read_json(request)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Call the internal Resource Discovery API with Azure client credentials."
        )
    )
    parser.add_argument("path", help="API path to GET, for example /resources")
    parser.add_argument(
        "--env-file",
        default=DEFAULT_ENV_FILE,
        help="Credential env file to read before calling the API.",
    )
    parser.add_argument(
        "--query",
        action="append",
        default=[],
        help="Query parameter as key=value. Can be provided multiple times.",
    )
    args = parser.parse_args()

    env_file_values = load_env_file(Path(args.env_file))
    client_id = env("RESOURCE_DISCOVERY_CLIENT_ID", env_file_values)
    client_secret = env("RESOURCE_DISCOVERY_CLIENT_SECRET", env_file_values)
    tenant_id = env("RESOURCE_DISCOVERY_TENANT_ID", env_file_values)
    scope = env("RESOURCE_DISCOVERY_SCOPE", env_file_values)
    base_url = env("RESOURCE_DISCOVERY_BASE_URL", env_file_values)

    token = fetch_token(tenant_id, client_id, client_secret, scope)
    result = get_resource(build_url(base_url, args.path, args.query), token)
    if isinstance(result, str):
        print(result)
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
