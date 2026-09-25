from pathlib import Path
from types import SimpleNamespace

from adapters.inbound import CandidateRun, JudgedRun
from adapters.mlflow import matrix
from workspaces.data_engineering.benchmarks import load_matrix_manifest

MATRIX_PATH = (
    Path(__file__).parents[3]
    / "src/workspaces/data_engineering/benchmarks/production_support"
    / "dates/09-25-26/matrix.yaml"
)
ARTIFACT_COUNT = 2
JUDGE_SCORE = 0.9


def test_publishes_parent_and_nested_matrix_runs(monkeypatch, tmp_path) -> None:
    configured: dict[str, object] = {"runs": [], "artifacts": []}

    class Run:
        def __init__(self, run_id: str) -> None:
            self.info = SimpleNamespace(run_id=run_id)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    class FakeMlflow:
        @staticmethod
        def set_tracking_uri(uri):
            configured["tracking_uri"] = uri

        @staticmethod
        def set_experiment(name):
            configured["experiment"] = name

        @staticmethod
        def start_run(*, run_name, tags, nested=False):
            configured["runs"].append((run_name, tags, nested))
            return Run("parent-run")

        @staticmethod
        def log_metrics(metrics):
            configured["metrics"] = metrics

        @staticmethod
        def log_dict(value, path):
            configured["assessment"] = (value, path)

        @staticmethod
        def log_artifact(path, artifact_path):
            configured["artifacts"].append((path, artifact_path))

    monkeypatch.setattr(matrix, "import_module", lambda _name: FakeMlflow)
    trace = tmp_path / "trace.jsonl"
    trace.write_text("{}\n", encoding="utf-8")
    assessment = tmp_path / "judge.json"
    assessment.write_text("{}", encoding="utf-8")
    candidate = CandidateRun(
        profile="sol-light",
        model="sol",
        reasoning_effort="low",
        elapsed_seconds=1,
        final_message="report",
        trace_path=trace,
        input_tokens=10,
        output_tokens=5,
    )
    result = JudgedRun(
        candidate,
        JUDGE_SCORE,
        {"overall_score": JUDGE_SCORE},
        assessment,
    )

    run_id = matrix.publish_matrix_results(
        load_matrix_manifest(MATRIX_PATH),
        (result,),
        tracking_uri="http://localhost:5000",
    )

    assert run_id == "parent-run"
    assert configured["experiment"] == "production_operations"
    assert configured["runs"][1][2] is True
    assert configured["metrics"]["judge_score"] == JUDGE_SCORE
    assert len(configured["artifacts"]) == ARTIFACT_COUNT
