from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from adapters.python_upgrade import (
    LocalPythonProjectSource,
    PythonProjectAdapterError,
    SubprocessUvLockRunner,
)
from adapters.python_upgrade import local as local_module


class UpdatingLockRunner:
    async def regenerate(self, project_root: Path) -> None:
        (project_root / "uv.lock").write_text(
            '[[package]]\nname = "example"\nversion = "2.0.0"\n',
            encoding="utf-8",
        )


class FailingLockRunner:
    async def regenerate(self, project_root: Path) -> None:
        (project_root / "uv.lock").write_text("partial", encoding="utf-8")
        message = "lock failed"
        raise RuntimeError(message)


class NoopLockRunner:
    async def regenerate(self, project_root: Path) -> None:
        del project_root


def _project(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        (
            "[project]\n"
            'name = "demo"\n'
            'requires-python = ">=3.11,<4"\n'
            'dependencies = ["Example>=1"]\n'
        ),
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "example"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )


def test_local_python_project_source_inspects_and_applies(tmp_path: Path) -> None:
    _project(tmp_path)
    source = LocalPythonProjectSource(UpdatingLockRunner())

    inventory = asyncio.run(source.inspect(tmp_path))
    changed = asyncio.run(
        source.apply_requires_python(
            tmp_path,
            "3.12",
            inventory.fingerprint,
        )
    )

    assert inventory.dependencies[0].locked_version == "1.0.0"
    assert changed == ("pyproject.toml", "uv.lock")
    assert 'requires-python = ">=3.12,<4"' in (tmp_path / "pyproject.toml").read_text(
        encoding="utf-8"
    )


def test_local_python_project_source_rolls_back_lock_failure(
    tmp_path: Path,
) -> None:
    _project(tmp_path)
    source = LocalPythonProjectSource(FailingLockRunner())
    inventory = asyncio.run(source.inspect(tmp_path))
    pyproject_before = (tmp_path / "pyproject.toml").read_bytes()
    lock_before = (tmp_path / "uv.lock").read_bytes()

    with pytest.raises(RuntimeError, match="lock failed"):
        asyncio.run(
            source.apply_requires_python(
                tmp_path,
                "3.12",
                inventory.fingerprint,
            )
        )

    assert (tmp_path / "pyproject.toml").read_bytes() == pyproject_before
    assert (tmp_path / "uv.lock").read_bytes() == lock_before


def test_local_python_project_source_rejects_stale_fingerprint(
    tmp_path: Path,
) -> None:
    _project(tmp_path)
    source = LocalPythonProjectSource(UpdatingLockRunner())

    with pytest.raises(PythonProjectAdapterError, match="changed after planning"):
        asyncio.run(source.apply_requires_python(tmp_path, "3.12", "stale"))


def test_local_python_project_source_supports_projects_without_locks(
    tmp_path: Path,
) -> None:
    _project(tmp_path)
    (tmp_path / "uv.lock").unlink()
    source = LocalPythonProjectSource(NoopLockRunner())

    inventory = asyncio.run(source.inspect(tmp_path))
    changed = asyncio.run(
        source.apply_requires_python(tmp_path, "3.12", inventory.fingerprint)
    )

    assert inventory.dependencies[0].locked_version is None
    assert changed == ("pyproject.toml",)


def test_local_python_project_source_removes_new_lock_on_rollback(
    tmp_path: Path,
) -> None:
    _project(tmp_path)
    (tmp_path / "uv.lock").unlink()
    source = LocalPythonProjectSource(FailingLockRunner())
    inventory = asyncio.run(source.inspect(tmp_path))

    with pytest.raises(RuntimeError, match="lock failed"):
        asyncio.run(
            source.apply_requires_python(tmp_path, "3.12", inventory.fingerprint)
        )

    assert not (tmp_path / "uv.lock").exists()


@pytest.mark.parametrize(
    ("pyproject", "message"),
    [
        ("[project", "invalid TOML"),
        ("[tool.demo]\nvalue = 1\n", "missing \\[project\\]"),
        ("[project]\nrequires-python = 3\n", "requires-python must be text"),
        (
            '[project]\nrequires-python = ">=3.11"\ndependencies = "bad"\n',
            "dependencies must be a list",
        ),
        (
            '[project]\nrequires-python = ">=3.11"\ndependencies = ["not @"]\n',
            "invalid dependency requirement",
        ),
        (
            (
                '[project]\nrequires-python = ">=3.11"\n'
                'dependencies = ["Example", "example"]\n'
            ),
            "duplicate dependency",
        ),
    ],
)
def test_local_python_project_source_rejects_invalid_projects(
    tmp_path: Path,
    pyproject: str,
    message: str,
) -> None:
    (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")

    with pytest.raises(PythonProjectAdapterError, match=message):
        asyncio.run(LocalPythonProjectSource().inspect(tmp_path))


@pytest.mark.parametrize(
    ("lock", "message"),
    [
        ("not =", "invalid uv.lock"),
        ('[package]\nname = "example"\n', "package entries must be a list"),
        (
            (
                '[[package]]\nname = "example"\nversion = "1.0.0"\n'
                '[[package]]\nname = "example"\nversion = "2.0.0"\n'
            ),
            "multiple versions",
        ),
    ],
)
def test_local_python_project_source_rejects_invalid_locks(
    tmp_path: Path,
    lock: str,
    message: str,
) -> None:
    _project(tmp_path)
    (tmp_path / "uv.lock").write_text(lock, encoding="utf-8")

    with pytest.raises(PythonProjectAdapterError, match=message):
        asyncio.run(LocalPythonProjectSource().inspect(tmp_path))


def test_local_python_project_source_requires_project_file(tmp_path: Path) -> None:
    with pytest.raises(PythonProjectAdapterError, match="not found"):
        asyncio.run(LocalPythonProjectSource().inspect(tmp_path))


@pytest.mark.parametrize("requires_python", ["~=3.11", ">=3.10,>=3.11"])
def test_local_python_project_source_rejects_unsupported_ranges(
    tmp_path: Path,
    requires_python: str,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        (f'[project]\nrequires-python = "{requires_python}"\ndependencies = []\n'),
        encoding="utf-8",
    )
    source = LocalPythonProjectSource(NoopLockRunner())
    inventory = asyncio.run(source.inspect(tmp_path))

    with pytest.raises(PythonProjectAdapterError, match="exactly one"):
        asyncio.run(
            source.apply_requires_python(tmp_path, "3.12", inventory.fingerprint)
        )


def test_updated_pyproject_rejects_non_utf8() -> None:
    with pytest.raises(PythonProjectAdapterError, match="invalid UTF-8"):
        local_module._updated_pyproject(b"\xff", "3.12")


def test_subprocess_uv_lock_runner_reports_command_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeProcess:
        returncode = 1

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"", b"resolution failed"

    async def create_process(*args: object, **kwargs: object) -> FakeProcess:
        assert args[:2] == ("uv", "lock")
        assert kwargs["cwd"] == tmp_path
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)

    with pytest.raises(PythonProjectAdapterError, match="resolution failed"):
        asyncio.run(SubprocessUvLockRunner().regenerate(tmp_path))


def test_subprocess_uv_lock_runner_accepts_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeProcess:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"", b""

    async def create_process(*args: object, **kwargs: object) -> FakeProcess:
        del args, kwargs
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)

    asyncio.run(SubprocessUvLockRunner().regenerate(tmp_path))
