from adapters.inbound.trace_compaction import compact_trace_for_judge, redact_text

MAX_COMPACT_OUTPUT = 3_000
EXPECTED_COMPACT_EVENTS = 2


def test_keeps_started_events_and_omits_warnings_and_large_output() -> None:
    events = (
        {"type": "item.started", "item": {"type": "command_execution"}},
        {
            "type": "item.completed",
            "item": {
                "type": "error",
                "message": "Codex is ignoring unrecognized configuration settings",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "type": "command_execution",
                "command": "inspect",
                "aggregated_output": "x" * 10_000,
            },
        },
    )

    compact = compact_trace_for_judge(events)

    assert len(compact) == EXPECTED_COMPACT_EVENTS
    assert compact[0]["type"] == "item.started"
    item = compact[1]["item"]
    assert isinstance(item, dict)
    output = item["aggregated_output"]
    assert isinstance(output, str)
    assert len(output) < MAX_COMPACT_OUTPUT
    assert "characters omitted" in output


def test_redacts_secret_keys_and_credential_text() -> None:
    events = (
        {
            "type": "item.completed",
            "authorization": "Bearer top-secret",
            "password": "nested-secret",
            "item": {
                "type": "command_execution",
                "aggregated_output": (
                    "aws_access_key_id=ASIAABCDEFGHIJKLMNOP "
                    "aws_secret_access_key=secret-value "
                    "aws_session_token=session-value"
                ),
            },
        },
    )

    compact = compact_trace_for_judge(events)
    encoded = str(compact)

    assert compact[0]["authorization"] == "[REDACTED]"
    assert compact[0]["password"] == "[REDACTED]"
    assert "ASIAABCDEFGHIJKLMNOP" not in encoded
    assert "secret-value" not in encoded
    assert "session-value" not in encoded
    assert "serialized-secret" not in redact_text('{"password":"serialized-secret"}')
    assert "secret-value" not in redact_text("aws_secret_access_key=secret-value")
    token_canaries = (
        '{"access_token":"access-secret","refresh_token":"refresh-secret",'
        '"api_key":"api-secret"}'
    )
    redacted = redact_text(token_canaries)
    assert "access-secret" not in redacted
    assert "refresh-secret" not in redacted
    assert "api-secret" not in redacted
