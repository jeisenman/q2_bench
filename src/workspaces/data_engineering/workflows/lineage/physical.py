"""Static extraction of physical DI Pipelines jobs and dependencies."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from workspaces.data_engineering.workflows.lineage.allocation_models import (
    ResourceAllocation,
)
from workspaces.data_engineering.workflows.lineage.ast_values import (
    assignment_names,
    call_keyword,
    call_name,
    evaluate,
    mapping_value,
    string_value,
    stringify,
    target_names,
    truth_value,
)
from workspaces.data_engineering.workflows.lineage.enrichments import (
    SourceLocation,
)
from workspaces.data_engineering.workflows.lineage.physical_allocation import (
    resource_allocation as resources_for,
)
from workspaces.data_engineering.workflows.lineage.physical_dependencies import (
    assign_return_references,
    dependency_expression,
    reference_groups,
)
from workspaces.data_engineering.workflows.lineage.physical_support import (
    PhysicalJobContext,
    bind_arguments,
    is_task_function,
    operator_factory_call,
)
from workspaces.data_engineering.workflows.lineage.source import (
    SourceIndex,
    SourceModule,
)


@dataclass(frozen=True, slots=True)
class PhysicalJob:
    """One OperatorFactory task found without importing Airflow."""

    key: str
    variable: str
    name: str
    implementation: str
    compute: str
    allocation: ResourceAllocation
    activity: tuple[tuple[str, str], ...]
    source: SourceLocation

    @property
    def activity_mapping(self) -> dict[str, str]:
        """Return activity metadata as a mapping."""
        return dict(self.activity)


@dataclass(frozen=True, slots=True)
class PhysicalExtraction:
    """Physical jobs, internal edges, and returned task references."""

    jobs: tuple[PhysicalJob, ...]
    dependencies: tuple[tuple[str, str], ...]
    returns: tuple[tuple[str, ...], ...] = ()


@dataclass(slots=True)
class _State:
    values: dict[str, object]
    references: dict[str, tuple[str, ...]] = field(default_factory=dict)
    jobs: list[PhysicalJob] = field(default_factory=list)
    dependencies: set[tuple[str, str]] = field(default_factory=set)
    returns: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True, slots=True)
class FunctionExtractionRequest:
    """Arguments and recursion context for one static function extraction."""

    arguments: tuple[object, ...]
    keywords: dict[str, object]
    prefix: str
    stack: tuple[tuple[Path, str], ...] = ()


@dataclass(frozen=True, slots=True)
class _WalkContext:
    module: SourceModule
    prefix: str
    stack: tuple[tuple[Path, str], ...]


class FunctionExtractor:
    """Interpret the static subset used to declare DI Pipelines tasks."""

    def __init__(
        self,
        index: SourceIndex,
        *,
        concrete_branches: bool = False,
    ) -> None:
        """Initialize against one source index."""
        self._index = index
        self._concrete_branches = concrete_branches

    def extract_call(
        self,
        module: SourceModule,
        function_name: str,
        call: ast.Call,
        caller_values: dict[str, object],
        *,
        prefix: str,
    ) -> PhysicalExtraction:
        """Extract a function invocation using statically evaluated arguments."""
        resolved = self._index.resolve_function(module, function_name)
        if resolved is None:
            return PhysicalExtraction((), ())
        target_module, function = resolved
        arguments = tuple(evaluate(item, caller_values) for item in call.args)
        keywords = {
            str(item.arg): evaluate(item.value, caller_values)
            for item in call.keywords
            if item.arg is not None
        }
        return self.extract(
            target_module,
            function,
            FunctionExtractionRequest(arguments, keywords, prefix),
        )

    def extract(
        self,
        module: SourceModule,
        function: ast.FunctionDef | ast.AsyncFunctionDef,
        request: FunctionExtractionRequest,
    ) -> PhysicalExtraction:
        """Extract one function and relevant source-resolvable helper calls."""
        identity = (module.path, function.name)
        if identity in request.stack:
            return PhysicalExtraction((), ())
        state = _State(
            values={
                **module.constants,
                **bind_arguments(
                    function,
                    request.arguments,
                    request.keywords,
                    module,
                ),
            }
        )
        self._statements(
            function.body,
            state,
            _WalkContext(
                module,
                request.prefix,
                (*request.stack, identity),
            ),
        )
        return PhysicalExtraction(
            jobs=tuple(state.jobs),
            dependencies=tuple(sorted(state.dependencies)),
            returns=state.returns,
        )

    def _statements(
        self,
        statements: list[ast.stmt],
        state: _State,
        context: _WalkContext,
    ) -> None:
        for statement in statements:
            if isinstance(statement, ast.Assign | ast.AnnAssign):
                self._assignment(
                    statement,
                    state,
                    context,
                )
            elif isinstance(statement, ast.Expr):
                self._expression(statement.value, state)
                if isinstance(statement.value, ast.Call):
                    self._unassigned_call(
                        statement.value,
                        state,
                        context,
                    )
            elif isinstance(statement, ast.Return):
                self._return_statement(
                    statement,
                    state,
                    context,
                )
            elif isinstance(statement, ast.If):
                selected = [*statement.body, *statement.orelse]
                if self._concrete_branches:
                    decision = truth_value(statement.test, state.values)
                    if decision is not None:
                        selected = statement.body if decision else statement.orelse
                self._statements(selected, state, context)
            elif isinstance(statement, ast.With | ast.AsyncWith):
                self._statements(
                    statement.body,
                    state,
                    context,
                )
            elif isinstance(statement, ast.For | ast.AsyncFor):
                for name in target_names(statement.target):
                    state.values[name] = f"{{{name}}}"
                self._statements(
                    [*statement.body, *statement.orelse],
                    state,
                    context,
                )
            elif isinstance(statement, ast.Try):
                nested = [
                    *statement.body,
                    *(item for handler in statement.handlers for item in handler.body),
                    *statement.orelse,
                    *statement.finalbody,
                ]
                self._statements(
                    nested,
                    state,
                    context,
                )

    def _assignment(
        self,
        statement: ast.Assign | ast.AnnAssign,
        state: _State,
        context: _WalkContext,
    ) -> None:
        names = assignment_names(statement)
        value = statement.value
        if value is None:
            return
        operator_call = operator_factory_call(value)
        if operator_call is not None:
            factory_call, operate_call = operator_call
            for variable in names or ("task",):
                job = _physical_job(
                    factory_call,
                    operate_call,
                    PhysicalJobContext(
                        context.module,
                        variable,
                        state.values,
                        context.prefix,
                        self._index.repository,
                    ),
                )
                state.jobs.append(job)
                state.references[variable] = (job.key,)
            return
        if isinstance(value, ast.Call):
            symbol = call_name(value)
            resolved = self._index.resolve_function(context.module, symbol)
            if resolved is not None and is_task_function(resolved[1]):
                child_module, child_function = resolved
                child_prefix = f"{context.prefix}.{names[0] if names else symbol}"
                arguments = tuple(evaluate(item, state.values) for item in value.args)
                keywords = {
                    str(item.arg): evaluate(item.value, state.values)
                    for item in value.keywords
                    if item.arg is not None
                }
                child = self.extract(
                    child_module,
                    child_function,
                    FunctionExtractionRequest(
                        arguments,
                        keywords,
                        child_prefix,
                        context.stack,
                    ),
                )
                state.jobs.extend(child.jobs)
                state.dependencies.update(child.dependencies)
                assign_return_references(names, child.returns, state.references)
                return
        evaluated = evaluate(value, state.values)
        for name in names:
            state.values[name] = evaluated

    def _unassigned_call(
        self,
        call: ast.Call,
        state: _State,
        context: _WalkContext,
    ) -> None:
        symbol = call_name(call)
        resolved = self._index.resolve_function(context.module, symbol)
        if resolved is None or not is_task_function(resolved[1]):
            return
        child_module, child_function = resolved
        child = self.extract(
            child_module,
            child_function,
            FunctionExtractionRequest(
                tuple(evaluate(item, state.values) for item in call.args),
                {
                    str(item.arg): evaluate(item.value, state.values)
                    for item in call.keywords
                    if item.arg is not None
                },
                f"{context.prefix}.{symbol}_{call.lineno}",
                context.stack,
            ),
        )
        state.jobs.extend(child.jobs)
        state.dependencies.update(child.dependencies)

    def _return_statement(
        self,
        statement: ast.Return,
        state: _State,
        context: _WalkContext,
    ) -> None:
        value = statement.value
        if isinstance(value, ast.Call):
            symbol = call_name(value)
            resolved = self._index.resolve_function(context.module, symbol)
            if resolved is not None and is_task_function(resolved[1]):
                child_module, child_function = resolved
                child = self.extract(
                    child_module,
                    child_function,
                    FunctionExtractionRequest(
                        tuple(evaluate(item, state.values) for item in value.args),
                        {
                            str(item.arg): evaluate(item.value, state.values)
                            for item in value.keywords
                            if item.arg is not None
                        },
                        f"{context.prefix}.{symbol}_{value.lineno}",
                        context.stack,
                    ),
                )
                state.jobs.extend(child.jobs)
                state.dependencies.update(child.dependencies)
                state.returns = child.returns
                return
        state.returns = reference_groups(value, state.references)

    def _expression(self, expression: ast.AST, state: _State) -> None:
        if not isinstance(expression, ast.BinOp):
            return
        dependency_expression(
            expression,
            state.references,
            state.dependencies,
        )


def _physical_job(
    factory: ast.Call,
    operate: ast.Call,
    context: PhysicalJobContext,
) -> PhysicalJob:
    activity = mapping_value(
        call_keyword(factory, "override_activity_args"),
        context.values,
    )
    normalized_activity = tuple(
        sorted((key, stringify(value)) for key, value in activity.items())
    )
    compute = string_value(
        call_keyword(operate, "compute"),
        context.values,
    )
    return PhysicalJob(
        key=f"{context.prefix}:{context.variable}:{factory.lineno}",
        variable=context.variable,
        name=string_value(
            call_keyword(factory, "job_name"),
            context.values,
        ),
        implementation=string_value(
            call_keyword(factory, "job_reference"),
            context.values,
        ),
        compute=compute,
        allocation=resources_for(factory, compute, context.values, context.repository),
        activity=normalized_activity,
        source=SourceLocation(
            context.module.path.relative_to(context.repository).as_posix(),
            factory.lineno,
        ),
    )
