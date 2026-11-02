"""Compare original Spark functions against independent Go IR predictions."""

import ast
import __future__
import collections
import concurrent.futures
import datetime
import hashlib
import math

from pyspark.sql import functions as F
from pyspark.sql.types import StringType


def select_function(source: str, name: str) -> ast.FunctionDef:
    """Select exactly one qualified original function without importing its module."""
    parts = name.split(".")
    body = ast.parse(source).body
    for part in parts[:-1]:
        candidates = [n for n in body if isinstance(n, ast.ClassDef) and n.name == part]
        if len(candidates) != 1:
            raise ValueError(f"ambiguous class identity: {name}")
        body = candidates[0].body
    found = [n for n in body if isinstance(n, ast.FunctionDef) and n.name == parts[-1]]
    if len(found) != 1 or found[0].decorator_list:
        raise ValueError(f"missing, ambiguous or decorated function: {name}")
    return found[0]


def normalize(value: object) -> object:
    """Normalize transport number/date encodings without rounding float results."""
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        if not math.isfinite(value):
            raise ValueError("nonfinite output outside semantic profile")
        return float(value)
    if value is None or isinstance(value, (str, bool)):
        return value
    raise TypeError(f"unsupported output value: {type(value)}")


def bag(rows: list[dict]) -> collections.Counter:
    """Retain duplicate multiplicities while ignoring relational row order."""
    return collections.Counter(
        json.dumps(normalize(row), sort_keys=True, allow_nan=False) for row in rows
    )


def compare_case(prediction: dict, session: object) -> dict:
    """Execute original source and compare its entire output bag with Go output."""
    case = prediction["case"]
    method = case["method"]
    receipt = method["source"]
    source = PAYLOAD["sources"][receipt["commit"] + ":" + receipt["path"]]
    if hashlib.sha256(source.encode()).hexdigest() != receipt["sha256"]:
        raise ValueError("original source digest mismatch")
    if method["status"] != "compiled":
        raise ValueError("unknown methods cannot participate as compiled cases")
    namespace = {"F": F, "StringType": StringType}
    for statement in ast.parse(source).body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name):
            try:
                namespace[statement.targets[0].id] = ast.literal_eval(statement.value)
            except (ValueError, TypeError):
                pass  # Constructors and computed globals are never executed.
    for definition in [*method.get("library", {}).values(), method]:
        if definition["source"] != receipt:
            raise ValueError("cross-file helper closure requires separate source bindings")
        node = select_function(source, definition["function"])
        module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
        exec(compile(module, receipt["path"], "exec", flags=__future__.annotations.compiler_flag), namespace)
    bindings = case["bindings"]
    arguments = dict(bindings.get("scalars") or {})
    for name, rows in bindings["tables"].items():
        schema = session.createDataFrame([], schema=case["spark_schemas"][name]).schema
        converted = []
        for row in rows:
            values = dict(row)
            for field in schema.fields:
                if field.dataType.typeName() in {"double", "float"} and values.get(field.name) is not None:
                    values[field.name] = float(values[field.name])
            converted.append(values)
        arguments[name] = session.createDataFrame(converted, schema=schema)
    if case.get("clause"):
        evidence = case["clause"]
        original_receipt = evidence["source"]
        original = PAYLOAD["sources"][original_receipt["commit"] + ":" + original_receipt["path"]].encode()
        if hashlib.sha256(original).hexdigest() != original_receipt["sha256"]:
            raise ValueError("original clause source digest mismatch")
        fragment = original[evidence["start_byte"]:evidence["end_byte"]].decode()
        expression = ast.parse(fragment, mode="eval")
        if not isinstance(expression.body, ast.Call):
            raise ValueError("clause must be one complete original call")
        output = eval(compile(expression, original_receipt["path"], "eval"), namespace, arguments)
    else:
        output = namespace[node.name](**arguments)
    is_tuple = method["steps"][-1]["expression"]["kind"] == "table_tuple"
    frames = list(output) if is_tuple else [output]
    ports = method["outputs"]
    if len(frames) != len(ports):
        raise ValueError("original output port arity mismatch")
    compared = {}
    for port, frame in zip(ports, frames):
        collected = frame.limit(10001).collect()
        if len(collected) > 10000:
            raise ValueError("original output exceeds comparison row bound")
        observed = [row.asDict(recursive=True) for row in collected]
        predicted_bag = bag(prediction["predicted_outputs"][port["name"]])
        observed_bag = bag(observed)
        schema_matches = sorted(frame.columns) == sorted(prediction["predicted_schemas"][port["name"]])
        compared[port["name"]] = {
            "status": "pass" if predicted_bag == observed_bag and schema_matches else "fail",
            "schema_matches": schema_matches,
            "predicted_count": sum(predicted_bag.values()),
            "observed_count": len(observed),
            "missing": dict(predicted_bag - observed_bag),
            "unexpected": dict(observed_bag - predicted_bag),
        }
        frequencies = {}
        for column in case.get("observe_columns", []):
            if column not in frame.columns:
                raise ValueError(f"observed column missing: {column}")
            counts = collections.Counter(json.dumps(normalize(row[column]), sort_keys=True) for row in observed)
            frequencies[column] = dict(counts) if len(counts) <= 20 else {"counts_omitted": True, "distinct_values": len(counts)}
        if frequencies:
            compared[port["name"]]["observed_value_counts"] = frequencies
        if case.get("observe_rows"):
            if len(case.get("observe_columns", [])) > 10:
                raise ValueError("observed row sample exceeds ten columns")
            compared[port["name"]]["observed_examples"] = [
                {column: normalize(row[column]) for column in case["observe_columns"]}
                for row in observed[:16]
            ]
    equal = all(result["status"] == "pass" for result in compared.values())
    return {
        "id": case["id"],
        "method_id": method["id"],
        "source": case.get("clause", {}).get("source", receipt),
        "bindings_sha256": prediction["bindings_sha256"],
        "prediction_sha256": prediction["prediction_sha256"],
        "status": "pass" if equal else "fail",
        "outputs": compared,
    }


if PAYLOAD["format"] != "q2-formal-comparison/v2":
    raise ValueError("require the signed-zero preserving comparison protocol")
session = spark.newSession()
session.conf.set("spark.sql.session.timeZone", "UTC")
session.conf.set("spark.sql.ansi.enabled", "false")
session.conf.set("spark.sql.shuffle.partitions", "2")
def compare_safely(prediction: dict) -> dict:
    """Retain an individual failure while other bounded clause cases complete."""
    try:
        return compare_case(prediction, session)
    except Exception as error:
        return {"id": prediction["case"]["id"], "status": "error", "error": str(error)[:2000]}


with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
    results = list(executor.map(compare_safely, PAYLOAD["predictions"]))
passed = sum(result["status"] == "pass" for result in results)
dbutils.notebook.exit(json.dumps({
    "format": "q2-formal-comparison-result/v2",
    "status": "pass_scoped" if passed == len(results) else "fail",
    "spark_version": session.version,
    "passed": passed,
    "failed": len(results) - passed,
    "whole_job_coverage": False,
    "results": results,
}, sort_keys=True))
