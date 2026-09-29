#!/usr/bin/env python3
"""Extract Azure HTTP Content-Length headers from an Airflow task log."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

CONTENT_LENGTH = re.compile(r"['\"]Content-Length['\"]:\s*['\"](?P<bytes>\d+)['\"]")
REQUEST_URL = re.compile(r"Request URL:\s*['\"](?P<url>[^'\"]+)['\"]")
REQUEST_METHOD = re.compile(r"Request method:\s*['\"](?P<method>[A-Z]+)['\"]")


@dataclass(frozen=True)
class ContentLength:
    """A Content-Length header with its nearest request context."""

    line: int
    bytes: int
    method: str | None
    url: str | None


def extract_content_lengths(lines: Iterable[str]) -> list[ContentLength]:
    """Return every Content-Length header, preserving duplicate log records."""
    request_url: str | None = None
    request_method: str | None = None
    content_lengths: list[ContentLength] = []

    for line_number, line in enumerate(lines, start=1):
        if url_match := REQUEST_URL.search(line):
            request_url = url_match.group("url")
            request_method = None
        if method_match := REQUEST_METHOD.search(line):
            request_method = method_match.group("method")
        if length_match := CONTENT_LENGTH.search(line):
            content_lengths.append(
                ContentLength(
                    line=line_number,
                    bytes=int(length_match.group("bytes")),
                    method=request_method,
                    url=request_url,
                )
            )

    return content_lengths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log_file", type=Path, help="Captured Airflow task log")
    parser.add_argument(
        "--json", action="store_true", help="Emit JSON rather than tab-separated text"
    )
    args = parser.parse_args()

    content_lengths = extract_content_lengths(
        args.log_file.read_text(errors="replace").splitlines()
    )
    if args.json:
        print(json.dumps([asdict(entry) for entry in content_lengths], indent=2))
    else:
        print(f"Content-Length references: {len(content_lengths)}")
        print("line\tbytes\tmethod\turl")
        for entry in content_lengths:
            print(
                f"{entry.line}\t{entry.bytes}\t{entry.method or ''}\t{entry.url or ''}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
