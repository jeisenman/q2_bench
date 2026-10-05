"""Static scan of the maximum-feature DI Pipelines L3 main graph."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from workspaces.data_engineering.workflows.lineage.ast_values import (
    assignment_names,
    call_keyword,
    call_name,
    evaluate,
    string_value,
    target_names,
)
from workspaces.data_engineering.workflows.lineage.models import SourceLocation
from workspaces.data_engineering.workflows.lineage.physical import (
    FunctionExtractor,
    PhysicalExtraction,
)
from workspaces.data_engineering.workflows.lineage.physical_dependencies import (
    dependency_expression,
)
from workspaces.data_engineering.workflows.lineage.source import (
    SourceIndex,
    SourceModule,
)

MAIN_GRAPH_FUNCTION = "build_abstract_dag"


@dataclass(frozen=True, slots=True)
class ExtractionProfile:
    """Concrete client values used to resolve allocation branches."""

    client_id: str = "maximum-permissions-client"
    resource_size: str = "xlarge"


@dataclass(frozen=True, slots=True)
class LogicalInvocation:
    """One task group or control job visible in the L3 DAG."""

    key: str
    function: str
    source: SourceLocation
    physical: PhysicalExtraction
    control: bool = False


@dataclass(frozen=True, slots=True)
class IntendedDag:
    """Logical jobs and dependencies for the maximum-feature client."""

    dag_id: str
    invocations: tuple[LogicalInvocation, ...]
    dependencies: tuple[tuple[str, str], ...]


@dataclass(slots=True)
class _ScanState:
    values: dict[str, object]
    references: dict[str, tuple[str, ...]] = field(default_factory=dict)
    invocations: dict[str, LogicalInvocation] = field(default_factory=dict)
    dependencies: set[tuple[str, str]] = field(default_factory=set)


class MainGraphScanner:
    """Scan all feature-gated paths for one maximum-permission client."""

    def __init__(
        self,
        index: SourceIndex,
        *,
        profile: ExtractionProfile | None = None,
        concrete_physical_branches: bool = False,
    ) -> None:
        """Initialize the DAG and physical task extractors."""
        self._index = index
        self._profile = profile or ExtractionProfile()
        self._functions = FunctionExtractor(
            index,
            concrete_branches=concrete_physical_branches,
        )

    def scan(self) -> IntendedDag:
        """Return the intended L3 graph without importing Airflow."""
        path = self._index.dag_root / "l3_main_graph.py"
        module = self._index.load_path(path, name="l3_main_graph")
        function = module.functions[MAIN_GRAPH_FUNCTION]
        state = _ScanState(
            values={
                **module.constants,
                "client": {
                    "clientId": self._profile.client_id,
                    "clientGroup": "4",
                    "resourceTags": {"size": self._profile.resource_size},
                    "sharedResourceGroup": ("pl-datafactory-us-dipipeline-prod-01"),
                },
                "do_not_run_andi_legacy_group": "different-resource-group",
                "mi_groups": {
                    "pl-datafactory-us-dipipeline-prod-01",
                },
                "testing_groups": set(),
                "active_accounts_monthly_financials_clients": {
                    self._profile.client_id,
                },
            }
        )
        self._statements(module, function.body, state)
        return IntendedDag(
            dag_id="l3_main_graph",
            invocations=tuple(
                sorted(state.invocations.values(), key=lambda item: item.key)
            ),
            dependencies=tuple(sorted(state.dependencies)),
        )

    def _statements(
        self,
        module: SourceModule,
        statements: list[ast.stmt],
        state: _ScanState,
    ) -> None:
        for statement in statements:
            if isinstance(statement, ast.Assign | ast.AnnAssign):
                self._assignment(module, statement, state)
            elif isinstance(statement, ast.Expr):
                if isinstance(statement.value, ast.BinOp):
                    dependency_expression(
                        statement.value,
                        state.references,
                        state.dependencies,
                    )
            elif isinstance(statement, ast.If):
                self._statements(
                    module,
                    [*statement.body, *statement.orelse],
                    state,
                )
            elif isinstance(statement, ast.With | ast.AsyncWith):
                self._statements(module, statement.body, state)
            elif isinstance(statement, ast.For | ast.AsyncFor):
                for name in target_names(statement.target):
                    state.values[name] = f"{{{name}}}"
                self._statements(
                    module,
                    [*statement.body, *statement.orelse],
                    state,
                )

    def _assignment(
        self,
        module: SourceModule,
        statement: ast.Assign | ast.AnnAssign,
        state: _ScanState,
    ) -> None:
        value = statement.value
        if value is None:
            return
        names = assignment_names(statement)
        if not isinstance(value, ast.Call):
            evaluated = evaluate(value, state.values)
            for name in names:
                state.values[name] = evaluated
            return
        symbol = call_name(value)
        if self._task_group_call(module, symbol):
            self._register_task_group(module, value, names, state)
            return
        if symbol.endswith("Operator"):
            self._register_control(module, value, names, state)
            return
        evaluated = evaluate(value, state.values)
        for name in names:
            state.values[name] = evaluated

    def _task_group_call(self, module: SourceModule, symbol: str) -> bool:
        imported = module.imports.get(symbol)
        return imported is not None and imported.module.startswith("task_groups.")

    def _register_task_group(
        self,
        module: SourceModule,
        call: ast.Call,
        names: tuple[str, ...],
        state: _ScanState,
    ) -> None:
        symbol = call_name(call)
        logical_names = names or (symbol,)
        extraction = self._functions.extract_call(
            module,
            symbol,
            call,
            state.values,
            prefix=logical_names[0],
        )
        physical_groups = _split_extraction(extraction, len(logical_names))
        for index, logical_name in enumerate(logical_names):
            key = symbol if logical_name == "_" else logical_name
            physical = physical_groups[index]
            invocation = LogicalInvocation(
                key=key,
                function=symbol,
                source=SourceLocation(
                    module.path.relative_to(self._index.repository).as_posix(),
                    call.lineno,
                ),
                physical=physical,
            )
            state.invocations[key] = _merge_invocation(
                state.invocations.get(key),
                invocation,
            )
            state.references[logical_name] = (key,)

    def _register_control(
        self,
        module: SourceModule,
        call: ast.Call,
        names: tuple[str, ...],
        state: _ScanState,
    ) -> None:
        task_id = string_value(call_keyword(call, "task_id"), state.values)
        for name in names:
            key = task_id if task_id != "None" else name
            state.invocations[key] = LogicalInvocation(
                key=key,
                function=call_name(call),
                source=SourceLocation(
                    module.path.relative_to(self._index.repository).as_posix(),
                    call.lineno,
                ),
                physical=PhysicalExtraction((), ()),
                control=True,
            )
            state.references[name] = (key,)


def _split_extraction(
    extraction: PhysicalExtraction,
    target_count: int,
) -> tuple[PhysicalExtraction, ...]:
    if target_count == 1 or len(extraction.returns) != target_count:
        return tuple(extraction for _ in range(target_count))
    return tuple(
        _physical_subset(extraction, returned) for returned in extraction.returns
    )


def _physical_subset(
    extraction: PhysicalExtraction,
    returned: tuple[str, ...],
) -> PhysicalExtraction:
    selected = set(returned)
    dependencies = set(extraction.dependencies)
    changed = True
    while changed:
        ancestors = {
            source
            for source, target in dependencies
            if target in selected and source not in selected
        }
        changed = bool(ancestors)
        selected.update(ancestors)
    return PhysicalExtraction(
        jobs=tuple(job for job in extraction.jobs if job.key in selected),
        dependencies=tuple(
            edge
            for edge in extraction.dependencies
            if edge[0] in selected and edge[1] in selected
        ),
        returns=(returned,),
    )


def _merge_invocation(
    existing: LogicalInvocation | None,
    current: LogicalInvocation,
) -> LogicalInvocation:
    if existing is None:
        return current
    jobs = {job.key: job for job in existing.physical.jobs}
    jobs.update({job.key: job for job in current.physical.jobs})
    dependencies = set(existing.physical.dependencies)
    dependencies.update(current.physical.dependencies)
    return LogicalInvocation(
        key=current.key,
        function=current.function,
        source=current.source,
        physical=PhysicalExtraction(
            tuple(sorted(jobs.values(), key=lambda item: item.key)),
            tuple(sorted(dependencies)),
        ),
        control=existing.control and current.control,
    )
