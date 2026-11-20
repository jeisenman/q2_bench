"""Bounded read-only adapter to the shared committed-Git Gherkin reader."""

import json
import os
import re
import selectors
import signal
import subprocess
import time
from pathlib import Path

from flask import Blueprint, request

from .validation import APIError

CAPABILITIES = {
    "keyword": {"enabled": True},
    "vector": {"enabled": False, "reason": "Vector search is disabled."},
}
BRIDGE = Path(__file__).resolve().parents[2] / "dist-host/gherkin-read.cjs"
MAX_OUTPUT = 2_097_152


def _bridge(value: dict) -> dict:
    """Run the fixed host entry once with bounded output and an owned lifetime."""
    if not BRIDGE.is_file():
        raise APIError(
            "gherkin_unavailable",
            "Build the Gherkin host with npm run build:host.",
            503,
        )
    child = None
    try:
        child = subprocess.Popen(
            ["node", str(BRIDGE)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        assert child.stdin is not None and child.stdout is not None
        child.stdin.write(json.dumps(value, ensure_ascii=False).encode())
        child.stdin.close()
        output = bytearray()
        deadline = time.monotonic() + 8
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                for key, _ in selector.select(min(remaining, 0.2)):
                    block = os.read(key.fd, 8192)
                    if not block:
                        selector.unregister(key.fileobj)
                    output.extend(block)
                    if len(output) > MAX_OUTPUT:
                        raise ValueError("Response exceeds limit.")
            child.wait(timeout=max(0.001, deadline - time.monotonic()))
        if child.returncode != 0:
            raise ValueError("Host read failed.")
        result = json.loads(output)
        if not isinstance(result, dict) or "error" in result:
            raise ValueError("Invalid host response.")
        return result
    except (OSError, ValueError, TimeoutError, subprocess.TimeoutExpired) as error:
        raise APIError(
            "gherkin_unavailable",
            "Committed Gherkin source could not be read within its size or time limit.",
            503,
        ) from error
    finally:
        if child is not None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
            if child.stdout is not None:
                child.stdout.close()
            if child.stdin is not None and not child.stdin.closed:
                child.stdin.close()


def _parameters(allowed: set[str]) -> dict[str, str]:
    values = request.args
    if set(values) - allowed or any(len(values.getlist(key)) != 1 for key in values):
        raise APIError("invalid_query", "Unsupported or duplicate Gherkin parameters.")
    return values.to_dict()


def _commit(value: str) -> str:
    if not re.fullmatch("[0-9a-f]{40}", value):
        raise APIError("invalid_query", "A full lowercase source commit is required.")
    return value


def _feature_path(value: str) -> str:
    if (
        not 1 <= len(value) <= 2048
        or not value.endswith(".feature")
        or "\\" in value
        or re.search(r"[\x00-\x1f\x7f]", value)
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise APIError("invalid_query", "A tracked relative feature path is required.")
    return value


def gherkin_blueprint() -> Blueprint:
    """Expose finite source reads through the existing research API only."""
    blueprint = Blueprint("gherkin", __name__, url_prefix="/api/research/v1/gherkin")

    @blueprint.get("/capabilities")
    def capabilities() -> dict:
        _parameters(set())
        return CAPABILITIES

    @blueprint.get("/features")
    def features() -> dict:
        args = _parameters({"offset", "query", "commit", "mode"})
        mode = args.get("mode", "keyword")
        if mode not in ("keyword", "vector"):
            raise APIError("invalid_query", "Search mode must be keyword or vector.")
        if mode == "vector":
            raise APIError("gherkin_vector_disabled", "Vector search is disabled.", 409)
        offset = args.get("offset", "0")
        if not re.fullmatch(r"0|[1-9][0-9]{0,4}", offset) or int(offset) > 10000:
            raise APIError(
                "invalid_query", "Offset must be an integer from 0 to 10000."
            )
        value = {"operation": "gherkin.list", "offset": int(offset)}
        if "commit" in args:
            value["commit"] = _commit(args["commit"])
        if "query" in args:
            query = args["query"].strip()
            if not 1 <= len(query) <= 200 or re.search(r"[\x00-\x1f\x7f]", query):
                raise APIError(
                    "invalid_query", "A literal query of 1..200 characters is required."
                )
            value.update(operation="gherkin.search", query=query, mode=mode)
        return _bridge(value)

    @blueprint.get("/feature")
    def feature() -> dict:
        args = _parameters({"path", "commit"})
        if set(args) != {"path", "commit"}:
            raise APIError("invalid_query", "Feature reads require path and commit.")
        return _bridge(
            {
                "operation": "gherkin.feature",
                "path": _feature_path(args["path"]),
                "commit": _commit(args["commit"]),
            }
        )

    return blueprint
