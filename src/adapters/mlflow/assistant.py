"""Configure the MLflow UI assistant provider."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class MlflowAssistantConfigurationError(RuntimeError):
    """Raised when the MLflow assistant cannot be configured."""

    @classmethod
    def request_failed(
        cls,
        method: str,
        url: str,
        reason: str,
    ) -> MlflowAssistantConfigurationError:
        """Create an actionable HTTP configuration error."""
        return cls(f"MLflow assistant request failed: {method} {url}: {reason}")

    @classmethod
    def missing_field(
        cls,
        resource: str,
        field: str,
    ) -> MlflowAssistantConfigurationError:
        """Create an error for an incomplete MLflow response."""
        return cls(f"MLflow {resource} response is missing {field}")


class JsonTransport(Protocol):
    """Minimal JSON transport used by assistant provisioning."""

    def get(self, path: str) -> dict[str, object]:
        """Fetch a JSON object."""

    def post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        """Post a JSON object and return the response."""


@dataclass(frozen=True, slots=True)
class UrlJsonTransport:
    """HTTP transport for one MLflow tracking server."""

    base_url: str

    def get(self, path: str) -> dict[str, object]:
        """Fetch a JSON object from MLflow."""
        return self._request("GET", path, None)

    def post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        """Post a JSON object to MLflow."""
        return self._request("POST", path, payload)

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None,
    ) -> dict[str, object]:
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        data = None if payload is None else json.dumps(payload).encode()
        request = Request(
            url,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=30) as response:
                raw = json.loads(response.read())
        except HTTPError as error:
            reason = error.read().decode(errors="replace")
            raise MlflowAssistantConfigurationError.request_failed(
                method,
                url,
                reason,
            ) from error
        except (URLError, TimeoutError) as error:
            raise MlflowAssistantConfigurationError.request_failed(
                method,
                url,
                str(error),
            ) from error
        if not isinstance(raw, dict):
            raise MlflowAssistantConfigurationError.request_failed(
                method,
                url,
                "expected a JSON object",
            )
        return raw


@dataclass(frozen=True, slots=True)
class CodexAssistantConfigurator:
    """Select MLflow's native Codex assistant provider."""

    provider_name: str = "codex"

    def configure(self, *, model: str, config_path: Path) -> str:
        """Persist Codex as the selected MLflow assistant provider."""
        _write_assistant_config(config_path, self.provider_name, model)
        return self.provider_name


@dataclass(frozen=True, slots=True)
class BedrockAssistantConfigurator:
    """Provision an idempotent Bedrock endpoint for the MLflow assistant."""

    transport: JsonTransport
    endpoint_name: str = "bedrock-assistant"
    secret_name: str = "bedrock-default-chain"
    model_definition_name: str = "bedrock-assistant-model"

    def configure(self, *, model: str, region: str, config_path: Path) -> str:
        """Create or update gateway resources and select the assistant provider."""
        secret_id = self._ensure_secret(region)
        model_definition_id = self._ensure_model_definition(secret_id, model)
        self._ensure_endpoint(model_definition_id)
        self._write_assistant_config(config_path)
        return self.endpoint_name

    def _ensure_secret(self, region: str) -> str:
        resources = self.transport.get("/api/3.0/mlflow/gateway/secrets/list").get(
            "secrets", []
        )
        existing = _find_named(resources, self.secret_name, "secret_name")
        if existing is None:
            response = self.transport.post(
                "/api/3.0/mlflow/gateway/secrets/create",
                {
                    "secret_name": self.secret_name,
                    "secret_value": {},
                    "provider": "bedrock",
                    "auth_config": {
                        "auth_mode": "default_chain",
                        "aws_region_name": region,
                    },
                },
            )
            existing = _mapping_field(response, "secret", "gateway secret")
        return _string_field(existing, "secret_id", "gateway secret")

    def _ensure_model_definition(self, secret_id: str, model: str) -> str:
        resources = self.transport.get(
            "/api/3.0/mlflow/gateway/model-definitions/list"
        ).get("model_definitions", [])
        existing = _find_named(resources, self.model_definition_name, "name")
        if existing is None:
            response = self.transport.post(
                "/api/3.0/mlflow/gateway/model-definitions/create",
                {
                    "name": self.model_definition_name,
                    "secret_id": secret_id,
                    "provider": "bedrock",
                    "model_name": model,
                },
            )
            existing = _mapping_field(
                response,
                "model_definition",
                "gateway model definition",
            )
        elif existing.get("model_name") != model:
            model_definition_id = _string_field(
                existing,
                "model_definition_id",
                "gateway model definition",
            )
            response = self.transport.post(
                "/api/3.0/mlflow/gateway/model-definitions/update",
                {
                    "model_definition_id": model_definition_id,
                    "secret_id": secret_id,
                    "provider": "bedrock",
                    "model_name": model,
                },
            )
            existing = _mapping_field(
                response,
                "model_definition",
                "gateway model definition",
            )
        return _string_field(
            existing,
            "model_definition_id",
            "gateway model definition",
        )

    def _ensure_endpoint(self, model_definition_id: str) -> None:
        resources = self.transport.get("/api/3.0/mlflow/gateway/endpoints/list").get(
            "endpoints", []
        )
        if _find_named(resources, self.endpoint_name, "name") is not None:
            return
        self.transport.post(
            "/api/3.0/mlflow/gateway/endpoints/create",
            {
                "name": self.endpoint_name,
                "model_configs": [
                    {
                        "model_definition_id": model_definition_id,
                        "linkage_type": "PRIMARY",
                        "weight": 1.0,
                    }
                ],
                "usage_tracking": True,
            },
        )

    def _write_assistant_config(self, path: Path) -> None:
        _write_assistant_config(path, "mlflow_gateway", self.endpoint_name)


def _write_assistant_config(path: Path, provider: str, model: str) -> None:
    """Persist one selected MLflow assistant provider."""
    config = {
        "projects": {},
        "providers": {
            provider: {
                "model": model,
                "selected": True,
                "base_url": None,
                "permissions": {
                    "allow_edit_files": False,
                    "allow_read_docs": True,
                    "full_access": False,
                },
                "skills": {"type": "global", "custom_path": None},
            }
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def _find_named(
    resources: object,
    name: str,
    field: str,
) -> dict[str, object] | None:
    if not isinstance(resources, list):
        return None
    return next(
        (
            item
            for item in resources
            if isinstance(item, dict) and item.get(field) == name
        ),
        None,
    )


def _mapping_field(
    response: dict[str, object],
    field: str,
    resource: str,
) -> dict[str, object]:
    value = response.get(field)
    if not isinstance(value, dict):
        raise MlflowAssistantConfigurationError.missing_field(resource, field)
    return value


def _string_field(
    resource: dict[str, object],
    field: str,
    resource_name: str,
) -> str:
    value = resource.get(field)
    if not isinstance(value, str):
        raise MlflowAssistantConfigurationError.missing_field(
            resource_name,
            field,
        )
    return value
