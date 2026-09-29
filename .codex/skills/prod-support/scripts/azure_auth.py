"""Authenticate Azure CLI for production Log Analytics queries."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROLE = "data-engineering"
PRODUCTION_SUBSCRIPTION_ID = "71aa0ec0-8411-43a2-9908-ddd2add764eb"
PRODUCTION_SUBSCRIPTION_NAME = "PrecisionLender Production"
REQUIRED_VARS = (
    "DATA_ENGINEERING_AZURE_CLIENT_ID",
    "DATA_ENGINEERING_AZURE_CLIENT_SECRET",
    "DATA_ENGINEERING_AZURE_TENANT_ID",
)


def load_dotenv(env_file: Path = Path(".env")) -> None:
    """Load local credentials without overriding explicitly exported values."""
    if not env_file.is_file():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key.isidentifier() or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def _active_account() -> dict[str, object] | None:
    """Return the active Azure account or report why it is unavailable."""
    result = subprocess.run(
        ["az", "account", "show", "--output", "json"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        print(
            "No active Azure CLI login. Run `az login`, then grant access to "
            f"subscription {PRODUCTION_SUBSCRIPTION_ID}.",
            file=sys.stderr,
        )
        return None
    try:
        account = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("Azure CLI returned invalid account information.", file=sys.stderr)
        return None
    return account if isinstance(account, dict) else None


def _select_production_subscription() -> bool:
    """Select the required production subscription for the active identity."""
    result = subprocess.run(
        [
            "az",
            "account",
            "set",
            "--subscription",
            PRODUCTION_SUBSCRIPTION_ID,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        print(
            "Azure CLI does not have access to production subscription "
            f"{PRODUCTION_SUBSCRIPTION_ID}. Run `az login`, then grant access.",
            file=sys.stderr,
        )
        return False
    return True


def ensure_azure_login(*, dry_run: bool = False) -> bool:
    """Use the configured service principal or an active production CLI login."""
    load_dotenv()
    missing = [name for name in REQUIRED_VARS if not os.environ.get(name)]
    if missing and len(missing) != len(REQUIRED_VARS):
        print(
            f"Incomplete Azure {ROLE} environment variables: " + ", ".join(missing),
            file=sys.stderr,
        )
        return False
    if not shutil.which("az"):
        print(
            "az is not available; install Azure CLI before resource discovery.",
            file=sys.stderr,
        )
        return False

    if len(missing) == len(REQUIRED_VARS):
        account = _active_account()
        if account is None:
            return False
        if account.get("id") != PRODUCTION_SUBSCRIPTION_ID:
            if not _select_production_subscription():
                return False
            account = _active_account()
            if account is None:
                return False
        if account.get("id") != PRODUCTION_SUBSCRIPTION_ID:
            print(
                "Azure CLI is not using required production subscription "
                f"{PRODUCTION_SUBSCRIPTION_ID}.",
                file=sys.stderr,
            )
            return False
        print(
            "Using active Azure CLI login on production subscription "
            f"{PRODUCTION_SUBSCRIPTION_ID} ({PRODUCTION_SUBSCRIPTION_NAME})."
        )
        return True

    command = [
        "az",
        "login",
        "--service-principal",
        "--username",
        os.environ["DATA_ENGINEERING_AZURE_CLIENT_ID"],
        "--password",
        os.environ["DATA_ENGINEERING_AZURE_CLIENT_SECRET"],
        "--tenant",
        os.environ["DATA_ENGINEERING_AZURE_TENANT_ID"],
        "--output",
        "none",
    ]
    if dry_run:
        print(
            "+ az login --service-principal "
            '--username "$DATA_ENGINEERING_AZURE_CLIENT_ID" '
            '--password "$DATA_ENGINEERING_AZURE_CLIENT_SECRET" '
            '--tenant "$DATA_ENGINEERING_AZURE_TENANT_ID" --output none'
        )
        return True
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode:
        print(
            f"Azure service-principal login failed: {result.stderr.strip()}",
            file=sys.stderr,
        )
        return False
    if not _select_production_subscription():
        print(
            "Azure service principal cannot access production subscription.",
            file=sys.stderr,
        )
        return False
    print(
        "Authenticated Azure CLI as data-engineering on production subscription "
        f"{PRODUCTION_SUBSCRIPTION_ID}."
    )
    return True
