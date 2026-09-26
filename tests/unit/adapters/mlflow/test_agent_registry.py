from types import SimpleNamespace
from typing import ClassVar

from adapters.mlflow import agent_registry
from workspaces.data_engineering.agents.prod_support import PROD_SUPPORT_DEFINITION


class FakeRun:
    def __enter__(self):
        return SimpleNamespace(info=SimpleNamespace(run_id="run-2"))

    def __exit__(self, *_args):
        return None


class FakeMlflow:
    logged: ClassVar[dict[str, object]] = {}

    @classmethod
    def set_tracking_uri(cls, value):
        cls.logged["tracking_uri"] = value

    @classmethod
    def set_experiment(cls, value):
        cls.logged["experiment"] = value

    @classmethod
    def start_run(cls, **kwargs):
        cls.logged["run"] = kwargs
        return FakeRun()

    @classmethod
    def log_dict(cls, value, path):
        cls.logged["definition"] = (value, path)


class FakeClient:
    existing = False
    created: ClassVar[list[str]] = []

    def search_registered_models(self, **_kwargs):
        return [object()] if self.existing else []

    def create_registered_model(self, name):
        self.created.append(name)

    def create_model_version(self, **kwargs):
        self.created.append(kwargs["source"])
        return SimpleNamespace(version="2")

    def set_registered_model_alias(self, name, alias, version):
        self.created.append(f"{name}:{alias}:{version}")


def test_registers_agent_definition_and_current_alias(monkeypatch) -> None:
    FakeClient.existing = False
    FakeClient.created = []
    modules = {
        "mlflow": FakeMlflow,
        "mlflow.tracking": SimpleNamespace(MlflowClient=FakeClient),
    }
    monkeypatch.setattr(agent_registry, "import_module", modules.__getitem__)

    run_id, version = agent_registry.register_agent_definition(
        PROD_SUPPORT_DEFINITION,
        tracking_uri="http://localhost:5000",
        experiment_name="production_operations",
    )

    assert (run_id, version) == ("run-2", "2")
    assert FakeClient.created[0] == "prod-support"
    assert FakeClient.created[-1] == "prod-support:agent-v4:2"


def test_reuses_existing_registered_agent(monkeypatch) -> None:
    FakeClient.existing = True
    FakeClient.created = []
    modules = {
        "mlflow": FakeMlflow,
        "mlflow.tracking": SimpleNamespace(MlflowClient=FakeClient),
    }
    monkeypatch.setattr(agent_registry, "import_module", modules.__getitem__)

    agent_registry.register_agent_definition(
        PROD_SUPPORT_DEFINITION,
        tracking_uri="sqlite:///mlflow.db",
        experiment_name="production_operations",
    )

    assert "prod-support" not in FakeClient.created
