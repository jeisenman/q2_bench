"""Static extraction of DI Pipelines dataset and Snowflake metadata."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from workspaces.data_engineering.workflows.lineage.ast_values import (
    assignment_names,
    call_keyword,
    call_name,
    evaluate,
    module_constants,
    string_value,
)
from workspaces.data_engineering.workflows.lineage.enrichments import (
    SourceLocation,
)
from workspaces.data_engineering.workflows.lineage.identifiers import (
    dataset_identifier,
)
from workspaces.data_engineering.workflows.lineage.models import DatasetField

_VERSION_FIELDS = re.compile(r"_v(?P<major>\d+)_(?P<minor>\d+)_fields")
_SCHEMA_METHOD = re.compile(r"_schema_v(?P<major>\d+)")
NULLABLE_POSITION = 2


@dataclass(frozen=True, slots=True)
class DatasetMetadata:
    """Business, schema, and Snowflake metadata for one logical dataset."""

    reference: str
    stage: str
    dataset: str
    version: str
    description: str | None
    fields: tuple[DatasetField, ...]
    snowflake_schema: str | None
    snowflake_table: str | None
    source: SourceLocation

    @property
    def node_id(self) -> str:
        """Return the canonical logical dataset identifier."""
        return dataset_identifier(self.stage, self.dataset).value


@dataclass(frozen=True, slots=True)
class _RawClass:
    reference: str
    module: str
    path: Path
    node: ast.ClassDef
    constants: dict[str, object]
    imports: dict[str, str]


class MetadataIndex:
    """Index metadata classes by Python reference and canonical dataset."""

    def __init__(
        self,
        by_reference: dict[str, DatasetMetadata],
    ) -> None:
        """Initialize immutable lookup maps."""
        self._by_reference = by_reference
        self._by_dataset = {
            metadata.node_id: metadata for metadata in by_reference.values()
        }

    @classmethod
    def from_repository(cls, repository: Path) -> MetadataIndex:
        """Parse every DI Pipelines dataset metadata class."""
        root = (
            repository
            / "ds-jobs"
            / "src"
            / "datascience_jobs"
            / "meta_data"
            / "datasets"
        )
        raw = _raw_classes(repository, root)
        resolved: dict[str, DatasetMetadata] = {}
        for reference, candidate in raw.items():
            lineage = _class_lineage(candidate, raw)
            metadata = _resolve_metadata(repository, candidate, lineage)
            if metadata is not None:
                resolved[reference] = metadata
        return cls(resolved)

    def reference(self, value: str) -> DatasetMetadata | None:
        """Return metadata for a fully qualified class reference."""
        return self._by_reference.get(value)

    def dataset(self, node_id: str) -> DatasetMetadata | None:
        """Return metadata for a canonical logical dataset identifier."""
        return self._by_dataset.get(node_id)


def _raw_classes(
    repository: Path,
    root: Path,
) -> dict[str, _RawClass]:
    result: dict[str, _RawClass] = {}
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = path.relative_to(repository / "ds-jobs" / "src")
        module = ".".join(relative.with_suffix("").parts)
        imports = _class_imports(tree)
        constants = module_constants(tree)
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            reference = f"{module}.{node.name}"
            result[reference] = _RawClass(
                reference,
                module,
                path,
                node,
                constants,
                imports,
            )
    return result


def _class_imports(tree: ast.Module) -> dict[str, str]:
    result: dict[str, str] = {}
    for statement in tree.body:
        if not isinstance(statement, ast.ImportFrom) or not statement.module:
            continue
        for alias in statement.names:
            result[alias.asname or alias.name] = f"{statement.module}.{alias.name}"
    return result


def _base_reference(candidate: _RawClass, base: ast.AST) -> str:
    name = ast.unparse(base)
    if name in candidate.imports:
        return candidate.imports[name]
    return f"{candidate.module}.{name}"


def _class_lineage(
    candidate: _RawClass,
    classes: dict[str, _RawClass],
    stack: tuple[str, ...] = (),
) -> tuple[_RawClass, ...]:
    if candidate.reference in stack:
        return ()
    found: list[_RawClass] = []
    for base in candidate.node.bases:
        parent = classes.get(_base_reference(candidate, base))
        if parent is not None:
            found.extend(_class_lineage(parent, classes, (*stack, candidate.reference)))
    found.append(candidate)
    deduplicated = {item.reference: item for item in found}
    return tuple(deduplicated.values())


def _resolve_metadata(
    repository: Path,
    candidate: _RawClass,
    lineage: tuple[_RawClass, ...],
) -> DatasetMetadata | None:
    environment = _class_environment(lineage)

    stage = _string_constant(environment, "PATH_STAGE")
    provider = _string_constant(environment, "PATH_PROVIDER")
    group = _string_constant(environment, "PATH_GROUP")
    dataset_name = _string_constant(environment, "DATASET_NAME")
    if not stage or not provider or not dataset_name:
        return None
    dataset = "/".join(part for part in (provider, group, dataset_name) if part)
    major = _integer_constant(environment, "LATEST_MAJOR_VERSION") or 1
    minor = _integer_constant(environment, "LATEST_MINOR_VERSION") or 0
    fields: tuple[DatasetField, ...] = ()
    for raw_class in lineage:
        fields = _merge_fields(
            fields,
            _fields(raw_class.node, environment, major, minor),
        )
    return DatasetMetadata(
        reference=candidate.reference,
        stage=stage,
        dataset=dataset,
        version=f"v{major}.{minor}",
        description=_string_constant(environment, "DATASET_DESCRIPTION"),
        fields=fields,
        snowflake_schema=_string_constant(environment, "SNOWFLAKE_SCHEMA"),
        snowflake_table=_string_constant(environment, "SNOWFLAKE_TABLE"),
        source=SourceLocation(
            candidate.path.relative_to(repository).as_posix(),
            candidate.node.lineno,
        ),
    )


def _class_environment(lineage: tuple[_RawClass, ...]) -> dict[str, object]:
    environment: dict[str, object] = {}
    for raw_class in lineage:
        environment.update(raw_class.constants)
        for statement in raw_class.node.body:
            if not isinstance(statement, ast.Assign | ast.AnnAssign):
                continue
            if statement.value is None:
                continue
            value = evaluate(statement.value, environment)
            for name in assignment_names(statement):
                environment[name] = value
    return environment


def _fields(
    class_node: ast.ClassDef,
    environment: dict[str, object],
    latest_major: int,
    latest_minor: int,
) -> tuple[DatasetField, ...]:
    fields: dict[str, DatasetField] = {}
    for statement in class_node.body:
        if not isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not _method_applies(statement.name, latest_major, latest_minor):
            continue
        for node in ast.walk(statement):
            if not isinstance(node, ast.Call) or not call_name(node).endswith(
                "DatasetField"
            ):
                continue
            field = _dataset_field(node, environment)
            if field is not None:
                fields[field.name] = field
    return tuple(fields.values())


def _method_applies(name: str, latest_major: int, latest_minor: int) -> bool:
    if version_match := _VERSION_FIELDS.fullmatch(name):
        version = (
            int(version_match.group("major")),
            int(version_match.group("minor")),
        )
        return version <= (latest_major, latest_minor)
    if schema_match := _SCHEMA_METHOD.fullmatch(name):
        return int(schema_match.group("major")) <= latest_major
    return False


def _dataset_field(
    node: ast.Call,
    environment: dict[str, object],
) -> DatasetField | None:
    name_node = node.args[0] if node.args else call_keyword(node, "name")
    type_node = node.args[1] if len(node.args) > 1 else call_keyword(node, "dataType")
    if name_node is None or type_node is None:
        return None
    nullable_node = (
        node.args[NULLABLE_POSITION]
        if len(node.args) > NULLABLE_POSITION
        else call_keyword(node, "nullable")
    )
    description_node = call_keyword(node, "definition")
    pii_node = call_keyword(node, "is_pii")
    return DatasetField(
        name=string_value(name_node, environment),
        data_type=ast.unparse(type_node),
        nullable=bool(evaluate(nullable_node, environment))
        if nullable_node is not None
        else True,
        description=(
            string_value(description_node, environment)
            if description_node is not None
            else None
        ),
        is_pii=bool(evaluate(pii_node, environment)) if pii_node is not None else False,
    )


def _merge_fields(
    inherited: tuple[DatasetField, ...],
    current: tuple[DatasetField, ...],
) -> tuple[DatasetField, ...]:
    fields = {field.name: field for field in inherited}
    fields.update({field.name: field for field in current})
    return tuple(fields.values())


def _string_constant(environment: dict[str, object], name: str) -> str | None:
    value = environment.get(name)
    return str(value) if value is not None else None


def _integer_constant(environment: dict[str, object], name: str) -> int | None:
    value = environment.get(name)
    return value if isinstance(value, int) else None
