from pathlib import Path

import pytest

from adapters.mlflow.assistant import (
    BedrockAssistantConfigurator,
    CodexAssistantConfigurator,
    MlflowAssistantConfigurationError,
)


def test_configure_selects_native_codex_provider(tmp_path: Path) -> None:
    config_path = tmp_path / "assistant" / "config.json"

    provider = CodexAssistantConfigurator().configure(
        model="default",
        config_path=config_path,
    )

    config = config_path.read_text(encoding="utf-8")
    assert provider == "codex"
    assert '"codex"' in config
    assert '"model": "default"' in config
    assert '"selected": true' in config
    assert '"mlflow_gateway"' not in config


class FakeTransport:
    def __init__(self) -> None:
        self.secrets: list[dict[str, object]] = []
        self.models: list[dict[str, object]] = []
        self.endpoints: list[dict[str, object]] = []
        self.posts: list[tuple[str, dict[str, object]]] = []

    def get(self, path: str) -> dict[str, object]:
        if path.endswith("secrets/list"):
            return {"secrets": self.secrets}
        if path.endswith("model-definitions/list"):
            return {"model_definitions": self.models}
        return {"endpoints": self.endpoints}

    def post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        self.posts.append((path, payload))
        if path.endswith("secrets/create"):
            secret = {
                "secret_id": "secret-1",
                "secret_name": payload["secret_name"],
            }
            self.secrets.append(secret)
            return {"secret": secret}
        if path.endswith("model-definitions/create"):
            model = {
                "model_definition_id": "model-1",
                "name": payload["name"],
                "model_name": payload["model_name"],
            }
            self.models.append(model)
            return {"model_definition": model}
        if path.endswith("model-definitions/update"):
            self.models[0]["model_name"] = payload["model_name"]
            return {"model_definition": self.models[0]}
        self.endpoints.append({"name": payload["name"]})
        return {"endpoint": self.endpoints[0]}


def test_configure_creates_bedrock_gateway_and_assistant_config(
    tmp_path: Path,
) -> None:
    transport = FakeTransport()
    config_path = tmp_path / "assistant" / "config.json"
    configurator = BedrockAssistantConfigurator(transport)

    endpoint = configurator.configure(
        model="us.anthropic.claude-sonnet-4-6",
        region="us-east-2",
        config_path=config_path,
    )

    assert endpoint == "bedrock-assistant"
    assert [path.rsplit("/", maxsplit=1)[-1] for path, _ in transport.posts] == [
        "create",
        "create",
        "create",
    ]
    assert '"mlflow_gateway"' in config_path.read_text(encoding="utf-8")
    assert '"allow_edit_files": false' in config_path.read_text(encoding="utf-8")


def test_configure_is_idempotent_and_updates_model(tmp_path: Path) -> None:
    transport = FakeTransport()
    configurator = BedrockAssistantConfigurator(transport)
    config_path = tmp_path / "config.json"
    configurator.configure(
        model="us.anthropic.claude-sonnet-4-6",
        region="us-east-2",
        config_path=config_path,
    )

    configurator.configure(
        model="us.anthropic.claude-sonnet-5",
        region="us-east-2",
        config_path=config_path,
    )

    assert transport.models[0]["model_name"] == "us.anthropic.claude-sonnet-5"
    assert sum(path.endswith("endpoints/create") for path, _ in transport.posts) == 1


def test_configure_rejects_incomplete_gateway_response(tmp_path: Path) -> None:
    class IncompleteTransport(FakeTransport):
        def post(
            self,
            path: str,
            payload: dict[str, object],
        ) -> dict[str, object]:
            if path.endswith("secrets/create"):
                return {}
            return super().post(path, payload)

    configurator = BedrockAssistantConfigurator(IncompleteTransport())

    with pytest.raises(
        MlflowAssistantConfigurationError,
        match="gateway secret response is missing secret",
    ):
        configurator.configure(
            model="us.anthropic.claude-sonnet-4-6",
            region="us-east-2",
            config_path=tmp_path / "config.json",
        )
