from pathlib import Path
from types import SimpleNamespace

from adapters.inbound import CandidateRun, JudgedRun
from adapters.mlflow import matrix
from workspaces.data_engineering.benchmarks import load_matrix_run

ROOT = Path(__file__).parents[3]
AGENTS_PATH = ROOT / "src/workspaces/data_engineering/benchmarks/agent-manifest.yaml"
BENCHMARK_PATH = (
    ROOT
    / "src/workspaces/data_engineering/benchmarks/production_support"
    / "dates/09-25-26/evaluation.yaml"
)
CASES_PATH = BENCHMARK_PATH.with_name("cases.yaml")
ARTIFACT_COUNT = 2
CAPABILITY_SCORE = 0.6
JUDGE_SCORE = 0.9


def test_publishes_parent_and_nested_matrix_runs(monkeypatch, tmp_path) -> None:
    configured: dict[str, object] = {"runs": [], "artifacts": [], "spans": []}

    class Run:
        def __init__(self, run_id: str) -> None:
            self.info = SimpleNamespace(run_id=run_id)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    class Span:
        def __init__(self, name, span_type, attributes, run_id):
            self.record = {
                "name": name,
                "span_type": span_type,
                "attributes": attributes,
                "run_id": run_id,
            }

        def __enter__(self):
            configured["spans"].append(self.record)
            return self

        def __exit__(self, *_args):
            return None

        def set_inputs(self, value):
            self.record["inputs"] = value

        def set_outputs(self, value):
            self.record["outputs"] = value

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

        @staticmethod
        def start_span(
            *,
            name,
            span_type,
            attributes,
            run_id=None,
        ):
            return Span(name, span_type, attributes, run_id)

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
        {
            "overall_score": JUDGE_SCORE,
            "capability_scores": [
                {
                    "role": "worker",
                    "model": "luna",
                    "capability": "log-analysis, evidence synthesis & reporting",
                    "score": CAPABILITY_SCORE,
                }
            ],
        },
        assessment,
    )

    run_id = matrix.publish_matrix_results(
        load_matrix_run(
            BENCHMARK_PATH,
            AGENTS_PATH,
            CASES_PATH,
            "prod-support-us-ca-2026-09-25",
        ),
        (result,),
        tracking_uri="http://localhost:5000",
    )

    assert run_id == "parent-run"
    assert configured["experiment"] == "production_operations"
    assert configured["runs"][1][2] is True
    assert configured["metrics"]["judge_score"] == JUDGE_SCORE
    capability_metric = "capability.worker.log_analysis_evidence_synthesis_reporting"
    assert configured["metrics"][capability_metric] == CAPABILITY_SCORE
    assert len(configured["artifacts"]) == ARTIFACT_COUNT
    assert [span["span_type"] for span in configured["spans"]] == [
        "WORKFLOW",
        "AGENT",
        "EVALUATOR",
    ]
    assert configured["spans"][0]["run_id"] == "parent-run"
    assert configured["spans"][0]["outputs"]["overall_score"] == JUDGE_SCORE
