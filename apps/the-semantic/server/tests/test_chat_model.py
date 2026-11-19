"""The production bridge uses one fixed executable and redacts diagnostics."""

import json

import pytest

from semantic_api import chat_model
from semantic_api.validation import APIError


@pytest.mark.parametrize(
    "mode", ["ok", "fail", "malformed", "oversized", "invalid_shape"]
)
def test_bridge_process_output_and_failure_boundaries(tmp_path, monkeypatch, mode):
    executable = tmp_path / "fixture-bridge"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import json,os,sys\n"
        "assert os.environ['SEMANTIC_OWNED_PROCESS_GROUP'] == '1'\n"
        "request=json.load(sys.stdin)\n"
        "assert request == {'instructions':'system','input':'question'}\n"
        "assert sys.argv[1:] == ['complete','--model','gpt-6.1-sol','--timeout-seconds','180']\n"
        + {
            "ok": "print(json.dumps({'output':json.dumps({'message':'Question?','proposal':None})}))\n",
            "fail": "print('private-provider',file=sys.stderr);sys.exit(1)\n",
            "malformed": "print('private-provider')\n",
            "oversized": "print('private-provider' * 30000)\n",
            "invalid_shape": "print(json.dumps({'output':'{}'}))\n",
        }[mode]
    )
    executable.chmod(0o700)
    monkeypatch.setattr(chat_model, "BINARY", executable)
    if mode == "ok":
        assert chat_model.codex_runner(
            {"instructions": "system", "input": "question"}
        ) == {"message": "Question?", "proposal": None}
    else:
        with pytest.raises(APIError) as caught:
            chat_model.codex_runner({"instructions": "system", "input": "question"})
        assert "private" not in str(caught.value)


def test_parser_rejects_non_json_and_missing_fields():
    for value in (
        "not json",
        "{}",
        json.dumps({"message": "x", "proposal": None, "extra": True}),
    ):
        with pytest.raises((ValueError, APIError)):
            chat_model.parse_answer(value)


def test_bridge_timeout_kills_owned_child(tmp_path, monkeypatch):
    executable = tmp_path / "fixture-sleeper"
    executable.write_text("#!/bin/sh\nsleep 30\n")
    executable.chmod(0o700)
    monkeypatch.setattr(chat_model, "BINARY", executable)
    times = iter((0, 181))
    monkeypatch.setattr(chat_model.time, "monotonic", lambda: next(times))
    original = chat_model.subprocess.Popen
    children = []

    def spawn(*args, **kwargs):
        child = original(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(chat_model.subprocess, "Popen", spawn)
    with pytest.raises(APIError, match="Codex turn failed"):
        chat_model.codex_runner({"instructions": "system", "input": "question"})
    assert len(children) == 1 and children[0].poll() is not None
