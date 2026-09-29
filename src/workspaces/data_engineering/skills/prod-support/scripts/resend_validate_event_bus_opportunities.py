#!/usr/bin/env python3
"""Extract, route, and resend recoverable EventBus opportunities in modular stages."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterable
from pathlib import Path

from playwright.sync_api import Page, sync_playwright
from validate_event_bus_opportunities import parse_payloads

DEFAULT_LOOKUP = (
    Path(__file__).resolve().parents[2]
    / "resource-discovery"
    / "references"
    / "client-guuid-lookup.json"
)
ENVIRONMENT_URLS = {
    "US01": "https://us01-app.precisionlender.com/Admin/Troubleshooting/ResendOpportunitySnapshots",
    "US02": "https://us02-app.precisionlender.com/Admin/Troubleshooting/ResendOpportunitySnapshots",
    "ENT01": "https://bacprod.precisionlender.com/Admin/Troubleshooting/ResendOpportunitySnapshots",
}
MAX_IDS_PER_SUBMISSION = 1000


def read_text(path: str) -> str:
    return sys.stdin.read() if path == "-" else Path(path).read_text()


def extract_recoverable(log_text: str) -> dict[str, list[str]]:
    """Return sorted, deduplicated recoverable IDs grouped by client UUID."""
    grouped = parse_payloads(log_text)
    return {
        client_id: sorted(recoverability[True])
        for client_id, recoverability in sorted(grouped.items())
        if recoverability[True]
    }


def load_batches(path: str) -> dict[str, list[str]]:
    payload = json.loads(read_text(path))
    if not isinstance(payload, dict):
        raise ValueError("The batch JSON must be an object keyed by client UUID.")
    return {
        str(client_id).lower(): sorted({str(value).lower() for value in values})
        for client_id, values in payload.items()
        if isinstance(values, list) and values
    }


def resolve_client(client_id: str, lookup_path: Path) -> dict[str, str]:
    """Resolve a client name and supported PLApp environment from the cached lookup."""
    lookup = json.loads(lookup_path.read_text())
    entry = lookup.get(client_id)
    if not isinstance(entry, dict) or entry.get("api_status") != "unique-match":
        raise ValueError(f"{client_id}: Resource Discovery has no unique match.")

    environments = {
        str(resource_set.get("environment", "")).upper()
        for resource_set in entry.get("resource_sets", [])
        if str(resource_set.get("service", "")).lower() == "plapp"
        and str(resource_set.get("environment", "")).upper() in ENVIRONMENT_URLS
    }
    if len(environments) != 1:
        found = ", ".join(sorted(environments)) or "none"
        raise ValueError(
            f"{client_id}: expected one supported PLApp environment in Resource Discovery; found {found}."
        )

    environment = environments.pop()
    return {
        "client_id": client_id,
        "name": str(entry["name"]),
        "environment": environment,
        "url": ENVIRONMENT_URLS[environment],
    }


def chunked(
    values: list[str], size: int = MAX_IDS_PER_SUBMISSION
) -> Iterable[list[str]]:
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


def select_client(page: Page, client: dict[str, str]) -> None:
    option = page.locator("#clientId option").filter(has_text=client["name"])
    matches = option.count()
    if matches != 1:
        raise RuntimeError(
            f"{client['client_id']}: expected one client option named {client['name']!r}; found {matches}."
        )
    option_value = option.first.get_attribute("value")
    if not option_value:
        raise RuntimeError(
            f"{client['client_id']}: the matching client option has no value."
        )
    page.locator("#clientId").select_option(option_value)


def submit_batch(
    page: Page, client: dict[str, str], opportunity_ids: list[str]
) -> None:
    page.goto(client["url"], wait_until="domcontentloaded")
    if page.url.split("/", 3)[2].lower() != client["url"].split("/", 3)[2].lower():
        raise RuntimeError(
            f"{client['client_id']}: authentication redirected away from the expected host."
        )

    select_client(page, client)
    page.locator("#ids").fill(",".join(opportunity_ids))
    page.locator('input[type="submit"][value="Resend"]').click()
    page.wait_for_load_state("domcontentloaded")

    status = page.locator("label").filter(has_text="Status:").first.inner_text().strip()
    if status != "Status: Successful":
        raise RuntimeError(
            f"{client['client_id']}: resend was not confirmed; UI reported {status!r}."
        )


def resend(
    batches: dict[str, list[str]],
    lookup_path: Path,
    profile_dir: Path,
    headless: bool,
) -> None:
    clients = {
        client_id: resolve_client(client_id, lookup_path) for client_id in batches
    }
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile_dir),
            channel="chrome",
            headless=headless,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            for client_id, opportunity_ids in batches.items():
                client = clients[client_id]
                for batch_number, batch in enumerate(chunked(opportunity_ids), start=1):
                    submit_batch(page, client, batch)
                    print(
                        f"Resent {len(batch)} opportunities for {client['name']} "
                        f"({client_id}) in {client['environment']}, batch {batch_number}."
                    )
        finally:
            context.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser(
        "extract", help="Extract recoverable IDs from an Airflow task log."
    )
    extract_parser.add_argument(
        "--log-file", required=True, help="Task log path, or - for stdin."
    )
    extract_parser.add_argument(
        "--output", type=Path, help="Write batch JSON to this path."
    )

    lookup_parser = subparsers.add_parser(
        "lookup", help="Resolve batch clients through the cached lookup table."
    )
    lookup_parser.add_argument("--batch-file", required=True)
    lookup_parser.add_argument("--lookup-file", type=Path, default=DEFAULT_LOOKUP)

    resend_parser = subparsers.add_parser(
        "resend", help="Submit batch JSON through the PL resend UI."
    )
    resend_parser.add_argument("--batch-file", required=True)
    resend_parser.add_argument("--lookup-file", type=Path, default=DEFAULT_LOOKUP)
    resend_parser.add_argument(
        "--profile-dir",
        type=Path,
        default=Path.home() / ".cache" / "pl-prod-support-playwright",
        help="Persistent Chrome profile; sign in once when the browser opens.",
    )
    resend_parser.add_argument("--headless", action="store_true")

    run_parser = subparsers.add_parser(
        "run", help="Extract, resend, wait five seconds, then exit for re-check."
    )
    run_parser.add_argument("--log-file", required=True)
    run_parser.add_argument("--lookup-file", type=Path, default=DEFAULT_LOOKUP)
    run_parser.add_argument(
        "--profile-dir",
        type=Path,
        default=Path.home() / ".cache" / "pl-prod-support-playwright",
    )
    run_parser.add_argument("--headless", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "extract":
            batches = extract_recoverable(read_text(args.log_file))
            rendered = json.dumps(batches, indent=2) + "\n"
            if args.output:
                args.output.write_text(rendered)
            else:
                print(rendered, end="")
        elif args.command == "lookup":
            batches = load_batches(args.batch_file)
            print(
                json.dumps(
                    [
                        resolve_client(client_id, args.lookup_file)
                        for client_id in batches
                    ],
                    indent=2,
                )
            )
        elif args.command == "resend":
            resend(
                load_batches(args.batch_file),
                args.lookup_file,
                args.profile_dir,
                args.headless,
            )
        else:
            batches = extract_recoverable(read_text(args.log_file))
            resend(batches, args.lookup_file, args.profile_dir, args.headless)
            time.sleep(5)
            print(
                "Five-second wait complete. Re-run failure discovery to acquire remaining red tasks."
            )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
