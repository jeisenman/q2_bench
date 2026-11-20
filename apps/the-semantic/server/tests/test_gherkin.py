"""Read-only Gherkin API boundaries and committed-source parity."""

import json
import subprocess
from pathlib import Path

import pytest
from flask import Flask, jsonify

from semantic_api import gherkin
from semantic_api.validation import APIError


@pytest.fixture
def api():
    app = Flask(__name__)
    app.register_blueprint(gherkin.gherkin_blueprint())

    @app.errorhandler(APIError)
    def error(value):
        return jsonify(
            error={"code": value.code, "message": value.message}
        ), value.status

    return app.test_client()


def test_vector_and_capabilities_never_spawn_or_read_checkout(api, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No child or filesystem read is permitted.")

    monkeypatch.setattr(gherkin, "_bridge", forbidden)
    monkeypatch.setattr(Path, "is_file", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert api.get("/api/research/v1/gherkin/capabilities").json == gherkin.CAPABILITIES
    result = api.get("/api/research/v1/gherkin/features?mode=vector&query=capital")
    assert result.status_code == 409
    assert result.json["error"]["code"] == "gherkin_vector_disabled"


@pytest.mark.parametrize(
    "query",
    [
        "offset=-1",
        "offset=10001",
        "offset=01",
        "offset=1&offset=2",
        "mode=unknown",
        "root=/private",
        "query=",
        "commit=HEAD",
        "query=%00private",
        "path=../read.feature&commit=" + "a" * 40,
    ],
)
def test_invalid_search_fails_before_host(api, monkeypatch, query):
    monkeypatch.setattr(gherkin, "_bridge", lambda _: pytest.fail("Host must not run."))
    assert api.get("/api/research/v1/gherkin/features?" + query).status_code == 400


def test_feature_identity_and_escaped_path_are_exact(api, monkeypatch):
    captured = []
    monkeypatch.setattr(
        gherkin, "_bridge", lambda value: captured.append(value) or value
    )
    commit = "a" * 40
    result = api.get(
        "/api/research/v1/gherkin/feature",
        query_string={"path": "specs/a & b.feature", "commit": commit},
    )
    assert result.status_code == 200
    assert captured == [
        {
            "operation": "gherkin.feature",
            "path": "specs/a & b.feature",
            "commit": commit,
        }
    ]
    for path in ("../bad.feature", "/bad.feature", "bad\\name.feature", "a//b.feature"):
        assert (
            api.get(
                "/api/research/v1/gherkin/feature",
                query_string={"path": path, "commit": commit},
            ).status_code
            == 400
        )
    assert len(captured) == 1


def test_committed_counts_pages_and_feature_pin(api, tmp_path, monkeypatch):
    def git(*args):
        return (
            subprocess.check_output(
                ["git", "-C", str(tmp_path), *args], stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )

    git("init", "-q")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.invalid")
    for index in range(27):
        (tmp_path / f"item-{index:02}.feature").write_text(
            "Feature: Capital\n  Scenario: Bound evidence\n    Given retained source\n"
        )
    (tmp_path / "link.feature").symlink_to("item-00.feature")
    git("add", ".")
    git("commit", "-qm", "fixture")
    commit = git("rev-parse", "HEAD")
    monkeypatch.setenv("SEMANTIC_GHERKIN_ROOT", str(tmp_path))
    first = api.get(
        "/api/research/v1/gherkin/features?query=CAPITAL&mode=keyword&offset=0"
    )
    assert first.status_code == 200, first.json
    assert first.json["commit"] == commit
    assert first.json["count"] == 27
    assert len(first.json["features"]) == 25
    assert first.json["has_more"] is True
    (tmp_path / "item-00.feature").write_text(
        "Uncommitted source must not replace evidence."
    )
    second = api.get(
        "/api/research/v1/gherkin/features",
        query_string={"query": "capital", "offset": 25, "commit": commit},
    )
    assert second.json["commit"] == commit
    assert len(second.json["features"]) == 2
    assert second.json["count"] == 27
    assert second.json["has_more"] is False
    feature = api.get(
        "/api/research/v1/gherkin/feature",
        query_string={"path": "item-00.feature", "commit": commit},
    )
    assert "Feature: Capital" in feature.json["text"]
    assert feature.json["commit"] == commit
    assert (
        api.get(
            "/api/research/v1/gherkin/feature",
            query_string={"path": "link.feature", "commit": commit},
        ).status_code
        == 503
    )


def test_missing_host_and_invalid_or_oversized_output_are_safe(
    api, tmp_path, monkeypatch
):
    monkeypatch.setattr(gherkin, "BRIDGE", tmp_path / "missing.cjs")
    result = api.get("/api/research/v1/gherkin/features")
    assert result.status_code == 503
    assert "build:host" in result.json["error"]["message"]
    bridge = tmp_path / "fixture.cjs"
    monkeypatch.setattr(gherkin, "BRIDGE", bridge)
    for program in (
        "process.stdout.write('private invalid output')",
        "process.stdout.write('x'.repeat(2097153))",
    ):
        bridge.write_text(program)
        result = api.get("/api/research/v1/gherkin/features")
        assert result.status_code == 503
        assert "private" not in str(result.json)


def test_host_capabilities_and_vector_error_without_checkout(monkeypatch):
    monkeypatch.setenv("SEMANTIC_GHERKIN_ROOT", "/absent-gherkin-source")
    for value, code in (
        ({"operation": "gherkin.capabilities"}, None),
        (
            {
                "operation": "gherkin.search",
                "query": "capital",
                "offset": 0,
                "mode": "vector",
            },
            "gherkin_vector_disabled",
        ),
    ):
        output = subprocess.run(
            ["node", str(gherkin.BRIDGE)],
            input=json.dumps(value),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        result = json.loads(output.stdout)
        if code:
            assert output.returncode == 1
            assert result["error"]["code"] == code
        else:
            assert output.returncode == 0
            assert result == gherkin.CAPABILITIES
