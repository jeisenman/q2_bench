"""Local uv-project adapter for Python upgrade inventory and mutation."""

from __future__ import annotations

import asyncio
import hashlib
import re
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

from workspaces.data_engineering.agents.python_upgrade import (
    ProjectDependency,
    PythonProjectInventory,
)

_REQUIRES_PYTHON_LINE = re.compile(
    r"^(?P<prefix>\s*requires-python\s*=\s*)"
    r"(?P<quote>[\"'])(?P<value>[^\"']+)(?P=quote)\s*$",
    re.MULTILINE,
)
_MINIMUM_SPECIFIER = re.compile(r"^>=\s*(?P<version>\d+\.\d+(?:\.\d+)?)$")


class PythonProjectAdapterError(RuntimeError):
    """Raised when a local uv project cannot be safely inspected or changed."""

    @classmethod
    def missing_pyproject(cls, path: Path) -> PythonProjectAdapterError:
        """Return an error for a missing project file."""
        return cls(f"pyproject.toml not found under {path}")

    @classmethod
    def invalid_toml(cls) -> PythonProjectAdapterError:
        """Return an error for invalid project TOML."""
        return cls("invalid pyproject.toml: invalid TOML")

    @classmethod
    def missing_project_table(cls) -> PythonProjectAdapterError:
        """Return an error for a missing project table."""
        return cls("invalid pyproject.toml: missing [project] table")

    @classmethod
    def invalid_requires_python(cls) -> PythonProjectAdapterError:
        """Return an error for invalid Requires-Python metadata."""
        return cls("invalid pyproject.toml: project.requires-python must be text")

    @classmethod
    def invalid_dependencies(cls) -> PythonProjectAdapterError:
        """Return an error for invalid dependency metadata."""
        return cls(
            "invalid pyproject.toml: project.dependencies must be a list of strings"
        )

    @classmethod
    def invalid_requirement(cls, value: str) -> PythonProjectAdapterError:
        """Return an error for one malformed direct requirement."""
        return cls(f"invalid pyproject.toml: invalid dependency requirement {value!r}")

    @classmethod
    def duplicate_dependency(cls, package: str) -> PythonProjectAdapterError:
        """Return an error for duplicate direct requirements."""
        return cls(f"invalid pyproject.toml: duplicate dependency {package!r}")

    @classmethod
    def invalid_lock(cls) -> PythonProjectAdapterError:
        """Return an error for malformed lock TOML."""
        return cls("invalid pyproject.toml: invalid uv.lock")

    @classmethod
    def invalid_lock_packages(cls) -> PythonProjectAdapterError:
        """Return an error for malformed lock package entries."""
        return cls("invalid pyproject.toml: uv.lock package entries must be a list")

    @classmethod
    def duplicate_lock_versions(cls, package: str) -> PythonProjectAdapterError:
        """Return an error for ambiguous locked package versions."""
        return cls(
            "invalid pyproject.toml: uv.lock contains multiple versions for "
            f"{package!r}"
        )

    @classmethod
    def invalid_encoding(cls) -> PythonProjectAdapterError:
        """Return an error for non-UTF-8 project content."""
        return cls("invalid pyproject.toml: invalid UTF-8")

    @classmethod
    def stale_project(cls) -> PythonProjectAdapterError:
        """Return an error when project files changed before mutation."""
        return cls("project files changed after planning; generate a new plan")

    @classmethod
    def unsupported_python_range(cls) -> PythonProjectAdapterError:
        """Return an error for a range that cannot be updated deterministically."""
        return cls("requires-python must contain exactly one >= major.minor minimum")


class UvLockRunner(Protocol):
    """Regenerate one uv lock file."""

    async def regenerate(self, project_root: Path) -> None:
        """Run uv lock for one project."""
        ...


class SubprocessUvLockRunner:
    """Regenerate uv.lock with the installed uv executable."""

    async def regenerate(self, project_root: Path) -> None:
        """Run uv lock and fail with bounded command diagnostics."""
        process = await asyncio.create_subprocess_exec(
            "uv",
            "lock",
            cwd=project_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            detail = stderr.decode(errors="replace").strip()[-1000:]
            message = f"uv lock failed with exit code {process.returncode}: {detail}"
            raise PythonProjectAdapterError(message)


class LocalPythonProjectSource:
    """Inspect and explicitly update local uv project metadata."""

    def __init__(self, lock_runner: UvLockRunner | None = None) -> None:
        """Initialize with an optional injectable lock regenerator."""
        self._lock_runner = lock_runner or SubprocessUvLockRunner()

    async def inspect(self, project_root: Path) -> PythonProjectInventory:
        """Return direct dependencies, locked versions, and a content fingerprint."""
        return await asyncio.to_thread(_inspect_project, project_root)

    async def apply_requires_python(
        self,
        project_root: Path,
        target_python: str,
        expected_fingerprint: str,
    ) -> tuple[str, ...]:
        """Update Requires-Python and regenerate uv.lock with rollback on failure."""
        root = project_root.resolve()
        pyproject_path = root / "pyproject.toml"
        lock_path = root / "uv.lock"
        pyproject_before, lock_before = await asyncio.to_thread(
            _read_project_files,
            root,
        )
        if _fingerprint(pyproject_before, lock_before) != expected_fingerprint:
            raise PythonProjectAdapterError.stale_project()
        pyproject_after = _updated_pyproject(pyproject_before, target_python)
        await asyncio.to_thread(
            pyproject_path.write_bytes,
            pyproject_after,
        )
        try:
            await self._lock_runner.regenerate(root)
        except BaseException:
            await asyncio.to_thread(
                _restore_project_files,
                pyproject_path,
                lock_path,
                pyproject_before,
                lock_before,
            )
            raise
        lock_after = lock_path.read_bytes() if lock_path.is_file() else None
        changed = ["pyproject.toml"]
        if lock_after != lock_before:
            changed.append("uv.lock")
        return tuple(changed)


def _inspect_project(project_root: Path) -> PythonProjectInventory:
    root = project_root.resolve()
    pyproject_content, lock_content = _read_project_files(root)
    try:
        pyproject = tomllib.loads(pyproject_content.decode())
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise PythonProjectAdapterError.invalid_toml() from error
    project = pyproject.get("project")
    if not isinstance(project, Mapping):
        raise PythonProjectAdapterError.missing_project_table()
    requires_python = project.get("requires-python")
    dependencies = project.get("dependencies", [])
    if not isinstance(requires_python, str) or not requires_python.strip():
        raise PythonProjectAdapterError.invalid_requires_python()
    if not isinstance(dependencies, list) or not all(
        isinstance(item, str) for item in dependencies
    ):
        raise PythonProjectAdapterError.invalid_dependencies()
    requirements = _requirements(dependencies)
    locked_versions = _locked_versions(lock_content)
    inventory_dependencies = tuple(
        ProjectDependency(
            package=package,
            requirement=str(requirement),
            locked_version=locked_versions.get(package),
        )
        for package, requirement in sorted(requirements.items())
    )
    return PythonProjectInventory(
        project_root=root,
        requires_python=requires_python,
        dependencies=inventory_dependencies,
        fingerprint=_fingerprint(pyproject_content, lock_content),
    )


def _read_project_files(project_root: Path) -> tuple[bytes, bytes | None]:
    pyproject_path = project_root / "pyproject.toml"
    if not pyproject_path.is_file():
        raise PythonProjectAdapterError.missing_pyproject(project_root)
    lock_path = project_root / "uv.lock"
    return (
        pyproject_path.read_bytes(),
        lock_path.read_bytes() if lock_path.is_file() else None,
    )


def _requirements(values: list[str]) -> dict[str, Requirement]:
    requirements: dict[str, Requirement] = {}
    for value in values:
        try:
            requirement = Requirement(value)
        except InvalidRequirement as error:
            raise PythonProjectAdapterError.invalid_requirement(value) from error
        package = canonicalize_name(requirement.name)
        if package in requirements:
            raise PythonProjectAdapterError.duplicate_dependency(package)
        requirements[package] = requirement
    return requirements


def _locked_versions(lock_content: bytes | None) -> dict[str, str]:
    if lock_content is None:
        return {}
    try:
        lock = tomllib.loads(lock_content.decode())
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise PythonProjectAdapterError.invalid_lock() from error
    packages = lock.get("package", [])
    if not isinstance(packages, list):
        raise PythonProjectAdapterError.invalid_lock_packages()
    versions: dict[str, str] = {}
    for item in packages:
        if not isinstance(item, Mapping):
            continue
        name = item.get("name")
        version = item.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            continue
        package = canonicalize_name(name)
        previous = versions.get(package)
        if previous is not None and previous != version:
            raise PythonProjectAdapterError.duplicate_lock_versions(package)
        versions[package] = version
    return versions


def _updated_pyproject(content: bytes, target_python: str) -> bytes:
    try:
        text = content.decode()
    except UnicodeDecodeError as error:
        raise PythonProjectAdapterError.invalid_encoding() from error
    matches = tuple(_REQUIRES_PYTHON_LINE.finditer(text))
    if len(matches) != 1:
        raise PythonProjectAdapterError.unsupported_python_range()
    match = matches[0]
    current = match.group("value")
    specifiers = [item.strip() for item in current.split(",")]
    minimum_indexes = [
        index
        for index, specifier in enumerate(specifiers)
        if _MINIMUM_SPECIFIER.fullmatch(specifier)
    ]
    if len(minimum_indexes) != 1:
        raise PythonProjectAdapterError.unsupported_python_range()
    specifiers[minimum_indexes[0]] = f">={target_python}"
    updated_line = (
        f"{match.group('prefix')}{match.group('quote')}"
        f"{','.join(specifiers)}{match.group('quote')}"
    )
    updated = f"{text[: match.start()]}{updated_line}{text[match.end() :]}"
    return updated.encode()


def _fingerprint(pyproject_content: bytes, lock_content: bytes | None) -> str:
    digest = hashlib.sha256()
    digest.update(b"pyproject.toml\0")
    digest.update(pyproject_content)
    digest.update(b"\0uv.lock\0")
    digest.update(lock_content if lock_content is not None else b"<missing>")
    return digest.hexdigest()


def _restore_project_files(
    pyproject_path: Path,
    lock_path: Path,
    pyproject_content: bytes,
    lock_content: bytes | None,
) -> None:
    pyproject_path.write_bytes(pyproject_content)
    if lock_content is None:
        lock_path.unlink(missing_ok=True)
    else:
        lock_path.write_bytes(lock_content)
