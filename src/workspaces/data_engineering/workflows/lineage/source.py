"""Repository-aware Python source indexing for DI Pipelines."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from workspaces.data_engineering.workflows.lineage.ast_values import (
    module_constants,
)
from workspaces.data_engineering.workflows.lineage.errors import (
    LineageValidationError,
)


@dataclass(frozen=True, slots=True)
class ImportedSymbol:
    """One source-resolvable imported function or value."""

    module: str
    name: str


@dataclass(frozen=True, slots=True)
class SourceModule:
    """Parsed Python module with constants, functions, and imports."""

    name: str
    path: Path
    tree: ast.Module
    constants: dict[str, object]
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef]
    imports: dict[str, ImportedSymbol]


class SourceIndex:
    """Load DI Pipelines modules without importing provider dependencies."""

    def __init__(self, repository: Path) -> None:
        """Initialize source roots for one DI Pipelines checkout."""
        self.repository = repository.resolve()
        self.dag_root = self.repository / "dags" / "precisionlender" / "dags"
        self._cache: dict[Path, SourceModule] = {}
        self._loading: set[Path] = set()

    def load_path(self, path: Path, *, name: str | None = None) -> SourceModule:
        """Parse one Python source file and cache its static index."""
        resolved = path.resolve()
        if resolved in self._cache:
            return self._cache[resolved]
        if not resolved.is_file():
            raise LineageValidationError.missing_source(str(resolved))
        tree = ast.parse(resolved.read_text(encoding="utf-8"), filename=str(resolved))
        imports = _imports(tree)
        self._loading.add(resolved)
        try:
            initial = self._imported_constants(imports)
        finally:
            self._loading.remove(resolved)
        module = SourceModule(
            name=name or self.module_name(resolved),
            path=resolved,
            tree=tree,
            constants=module_constants(tree, initial),
            functions={
                statement.name: statement
                for statement in tree.body
                if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef)
            },
            imports=imports,
        )
        self._cache[resolved] = module
        return module

    def _imported_constants(
        self,
        imports: dict[str, ImportedSymbol],
    ) -> dict[str, object]:
        values: dict[str, object] = {}
        for alias, imported in imports.items():
            path = self.module_path(imported.module)
            if path is None or not path.is_file() or path.resolve() in self._loading:
                continue
            module = self.load_path(path, name=imported.module)
            if imported.name in module.constants:
                values[alias] = module.constants[imported.name]
        return values

    def load_module(self, name: str) -> SourceModule | None:
        """Resolve a DI Pipelines import name to repository source."""
        path = self.module_path(name)
        return self.load_path(path, name=name) if path and path.is_file() else None

    def module_path(self, name: str) -> Path | None:
        """Return the local file implementing an import name."""
        parts = name.split(".")
        if parts[0] == "task_groups":
            return self.dag_root.joinpath(*parts).with_suffix(".py")
        if parts[0] == "utils":
            return self.repository.joinpath("dag-utils", *parts[1:]).with_suffix(".py")
        return None

    def module_name(self, path: Path) -> str:
        """Return the import name for one known source path."""
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(self.dag_root)
            return ".".join(relative.with_suffix("").parts)
        except ValueError:
            pass
        utility_root = self.repository / "dag-utils"
        try:
            relative = resolved.relative_to(utility_root)
            return ".".join(("utils", *relative.with_suffix("").parts))
        except ValueError:
            return resolved.stem

    def resolve_function(
        self,
        module: SourceModule,
        symbol: str,
    ) -> tuple[SourceModule, ast.FunctionDef | ast.AsyncFunctionDef] | None:
        """Resolve a local or imported function symbol."""
        local = module.functions.get(symbol)
        if local is not None:
            return module, local
        imported = module.imports.get(symbol)
        if imported is None:
            return None
        imported_module = self.load_module(imported.module)
        if imported_module is None:
            return None
        function = imported_module.functions.get(imported.name)
        return (imported_module, function) if function is not None else None


def _imports(tree: ast.Module) -> dict[str, ImportedSymbol]:
    imports: dict[str, ImportedSymbol] = {}
    for statement in tree.body:
        if not isinstance(statement, ast.ImportFrom) or not statement.module:
            continue
        for alias in statement.names:
            imports[alias.asname or alias.name] = ImportedSymbol(
                statement.module,
                alias.name,
            )
    return imports
