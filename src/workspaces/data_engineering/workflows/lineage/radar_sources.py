"""Static source readers for the cross-repository RADAR pipeline."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from workspaces.data_engineering.workflows.lineage.enrichments import (
    SourceLocation,
)

RUN_FILE_FOLDERS = frozenset(
    {
        "ApplicationInput",
        "RelationshipServiceInput",
        "MappingResults",
        "TransformResults",
        "EngineResults",
        "DataEngineering",
        "DatabaseOutput",
    }
)
_ATTRIBUTE = re.compile(r'(\w+)="([^"]*)"')
DYNAMIC_FILE_ARGUMENT = 2
_DYNAMIC_FILE_FUNCTIONS = frozenset(
    {
        "load_extracted_client_file",
        "output_extracted_client_file",
    }
)
_STAGE_TOKEN = {
    "extract": re.compile(r"(?:^|_)extract_", re.IGNORECASE),
    "mapping": re.compile(r"(?:^|_)map_", re.IGNORECASE),
    "transform": re.compile(r"(?:^|_)(?:v2_)?transform_", re.IGNORECASE),
}


@dataclass(frozen=True, slots=True)
class RunFileContract:
    """One run-relative file declared by DataIngress."""

    path: str
    source: SourceLocation


@dataclass(frozen=True, slots=True)
class FileReference:
    """A generated file helper resolved to one run-relative path."""

    path: str
    library_source: SourceLocation
    call_source: SourceLocation


@dataclass(frozen=True, slots=True)
class NotebookEvidence:
    """One executable notebook and its statically resolvable file calls."""

    stage: str
    implementation: str
    source: SourceLocation
    inputs: tuple[FileReference, ...]
    outputs: tuple[FileReference, ...]


@dataclass(frozen=True, slots=True)
class _LibraryFunction:
    path: str | None
    source: SourceLocation


def run_file_contracts(repository: Path) -> tuple[RunFileContract, ...]:
    """Read DataIngress run-file declarations without evaluating C#."""
    relative = Path("PrecisionLender.DataIngress.Persistence/Client/Schema.xml")
    source_path = repository / relative
    contracts: dict[str, RunFileContract] = {}
    for line_number, line in enumerate(
        source_path.read_text(encoding="utf-8-sig").splitlines(),
        start=1,
    ):
        if "<RunFile " not in line:
            continue
        attributes = dict(_ATTRIBUTE.findall(line))
        folder = attributes.get("Folder")
        if folder not in RUN_FILE_FOLDERS:
            continue
        file_name = attributes.get("FileName") or attributes.get("Name")
        if not file_name:
            continue
        extension = ".xml" if attributes.get("XmlFile") == "true" else ".csv"
        if Path(file_name).suffix:
            extension = ""
        path = f"{folder}/{file_name}{extension}"
        contracts.setdefault(
            path,
            RunFileContract(
                path,
                SourceLocation(f"pl-dataingress/{relative.as_posix()}", line_number),
            ),
        )
    return tuple(contracts[path] for path in sorted(contracts))


def notebook_evidence(
    notebooks_repository: Path,
    libraries_repository: Path,
) -> tuple[NotebookEvidence, ...]:
    """Resolve notebook loader and outputter calls to concrete run files."""
    loaders = _library_functions(
        libraries_repository,
        Path("radar_libraries/fileio/loader.py"),
    )
    outputters = _library_functions(
        libraries_repository,
        Path("radar_libraries/fileio/outputter.py"),
    )
    root = notebooks_repository / "notebooks/Shared"
    candidates = [
        *sorted((root / "Universal").glob("*.py")),
        *sorted((root / "Clients").rglob("*.py")),
    ]
    evidence: list[NotebookEvidence] = []
    for path in candidates:
        stage = _notebook_stage(path.stem)
        if stage is None:
            continue
        relative = path.relative_to(notebooks_repository).as_posix()
        module = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        constants = _string_constants(module)
        inputs: list[FileReference] = []
        outputs: list[FileReference] = []
        for call in (item for item in ast.walk(module) if isinstance(item, ast.Call)):
            symbol = _attribute_call(call)
            if symbol is None:
                continue
            owner, function = symbol
            call_source = SourceLocation(
                f"radar-notebooks/{relative}",
                call.lineno,
            )
            if owner == "loader":
                reference = _call_reference(
                    function,
                    call,
                    constants,
                    loaders,
                    call_source,
                )
                if reference is not None:
                    inputs.append(reference)
            elif owner == "outputter":
                reference = _call_reference(
                    function,
                    call,
                    constants,
                    outputters,
                    call_source,
                )
                if reference is not None:
                    outputs.append(reference)
        if inputs or outputs:
            evidence.append(
                NotebookEvidence(
                    stage=stage,
                    implementation=relative,
                    source=SourceLocation(f"radar-notebooks/{relative}", 1),
                    inputs=_unique_references(inputs),
                    outputs=_unique_references(outputs),
                )
            )
    return tuple(evidence)


def _library_functions(
    repository: Path,
    relative: Path,
) -> dict[str, _LibraryFunction]:
    path = repository / relative
    module = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    result: dict[str, _LibraryFunction] = {}
    for function in (
        item
        for item in module.body
        if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
    ):
        run_path = _function_run_path(function)
        if run_path is None and function.name not in _DYNAMIC_FILE_FUNCTIONS:
            continue
        result[function.name] = _LibraryFunction(
            run_path,
            SourceLocation(f"radar-libraries/{relative.as_posix()}", function.lineno),
        )
    return result


def _function_run_path(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> str | None:
    for node in ast.walk(function):
        if not isinstance(node, ast.Assign) or not any(
            isinstance(target, ast.Name) and target.id in {"filename", "full_path"}
            for target in node.targets
        ):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        function_call = node.value.func
        if not isinstance(function_call, ast.Attribute) or function_call.attr != "join":
            continue
        values = [
            argument.value
            for argument in node.value.args[1:]
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
        ]
        if values and len(values) == len(node.value.args) - 1:
            return "/".join(value.strip("/") for value in values)
    return None


def _call_reference(
    function: str,
    call: ast.Call,
    constants: dict[str, str],
    index: dict[str, _LibraryFunction],
    call_source: SourceLocation,
) -> FileReference | None:
    found = index.get(function)
    if found is not None and found.path is not None:
        return FileReference(found.path, found.source, call_source)
    if (
        function not in _DYNAMIC_FILE_FUNCTIONS
        or found is None
        or len(call.args) <= DYNAMIC_FILE_ARGUMENT
    ):
        return None
    file_name = _string_value(call.args[DYNAMIC_FILE_ARGUMENT], constants)
    if file_name is None:
        return None
    file_name = file_name if file_name.endswith(".csv") else f"{file_name}.csv"
    return FileReference(
        f"RawInputs/{file_name}",
        found.source,
        call_source,
    )


def _notebook_stage(name: str) -> str | None:
    for stage, pattern in _STAGE_TOKEN.items():
        if pattern.search(name):
            return stage
    return None


def _attribute_call(call: ast.Call) -> tuple[str, str] | None:
    function = call.func
    if not isinstance(function, ast.Attribute) or not isinstance(
        function.value, ast.Name
    ):
        return None
    return function.value.id, function.attr


def _string_constants(module: ast.Module) -> dict[str, str]:
    constants: dict[str, str] = {}
    for statement in module.body:
        if not isinstance(statement, ast.Assign):
            continue
        value = _string_value(statement.value, constants)
        if value is None:
            continue
        for target in statement.targets:
            if isinstance(target, ast.Name):
                constants[target.id] = value
    return constants


def _string_value(node: ast.expr, constants: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    return None


def _unique_references(
    references: list[FileReference],
) -> tuple[FileReference, ...]:
    unique = {
        (item.path, item.call_source.path, item.call_source.line): item
        for item in references
    }
    return tuple(unique[key] for key in sorted(unique))
