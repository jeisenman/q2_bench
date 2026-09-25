import asyncio

from mcp_servers.prod_support import (
    prod_support_definition,
    prod_support_prompt,
    run_prod_support,
)


def test_mcp_tool_runs_prod_support_agent() -> None:
    result = asyncio.run(
        run_prod_support(
            prompt="Investigate the orders pipeline.",
            service="orders",
            correlation_id="incident-1",
        )
    )

    assert result["correlation_id"] == "incident-1"
    assert "PROD SUPPORT" in result["output"]
    assert "- Good" in result["output"]
    assert result["tool_calls"] == (
        "discover_airflow_failures",
        "fetch_airflow_task_log",
        "classify_failure",
    )


def test_mcp_resource_and_prompt_describe_agent() -> None:
    definition = asyncio.run(prod_support_definition())
    prompt = prod_support_prompt("Pipeline failed.")

    assert "production" in definition.lower()
    assert "Request: Pipeline failed." in prompt
