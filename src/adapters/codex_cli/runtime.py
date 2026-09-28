"""Execute tool-free agent definitions through the Codex CLI."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from domain import AgentDefinition, AgentRequest, AgentResult
from observability import traced_runtime_run


class CodexCliRuntimeError(RuntimeError):
    """Raised when Codex cannot execute an agent definition."""

    @classmethod
    def invalid_home(cls) -> CodexCliRuntimeError:
        """Return an error for a missing Codex home."""
        return cls("CODEX_HOME must reference an initialized Codex directory")

    @classmethod
    def missing_config(cls, path: Path) -> CodexCliRuntimeError:
        """Return an error for missing Codex configuration."""
        return cls(f"Codex configuration is missing: {path}")

    @classmethod
    def process_failed(cls, returncode: int, detail: str) -> CodexCliRuntimeError:
        """Return an error for a failed Codex process."""
        return cls(f"Codex exited with code {returncode}: {detail}")

    @classmethod
    def missing_output(cls) -> CodexCliRuntimeError:
        """Return an error when Codex writes no output file."""
        return cls("Codex did not write its final output")

    @classmethod
    def empty_output(cls, name: str) -> CodexCliRuntimeError:
        """Return an error when Codex produces empty output."""
        return cls(f"agent {name!r} returned no text")

    @classmethod
    def delegation_unsupported(cls, name: str) -> CodexCliRuntimeError:
        """Return an error for a delegating definition."""
        return cls(f"agent {name!r} permits delegation; leaf agents are required")

    @classmethod
    def missing_model(cls, name: str) -> CodexCliRuntimeError:
        """Return an error for a definition without a model."""
        return cls(f"agent {name!r} does not declare a model")

    @classmethod
    def tools_unsupported(cls, name: str) -> CodexCliRuntimeError:
        """Return an error for a definition with tools."""
        return cls(f"agent {name!r} declares unsupported tools")


class CodexCliRuntime:
    """Run leaf agents using the provider configured in ``CODEX_HOME``."""

    def __init__(self, *, executable: str = "codex") -> None:
        """Initialize the runtime with a Codex executable."""
        self._executable = executable

    @traced_runtime_run
    async def run(
        self,
        definition: AgentDefinition,
        request: AgentRequest,
    ) -> AgentResult:
        """Execute one model-backed agent request."""
        _validate_definition(definition)
        model = definition.model
        assert model is not None
        codex_home = Path(os.environ.get("CODEX_HOME", "")).expanduser()
        if not codex_home.is_dir():
            raise CodexCliRuntimeError.invalid_home()
        config_path = codex_home / "config.toml"
        if not config_path.is_file():
            raise CodexCliRuntimeError.missing_config(config_path)

        with TemporaryDirectory(prefix="prod-support-codex-") as temporary:
            output_path = Path(temporary) / "output.txt"
            process = await asyncio.create_subprocess_exec(
                self._executable,
                "--model",
                model,
                "--sandbox",
                "read-only",
                "--ask-for-approval",
                "never",
                "exec",
                "--skip-git-repo-check",
                "--ephemeral",
                "--output-last-message",
                str(output_path),
                "-",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate(_prompt(definition, request).encode())
            returncode = process.returncode
            assert returncode is not None
            if returncode != 0:
                detail = stderr.decode(errors="replace").strip()
                raise CodexCliRuntimeError.process_failed(
                    returncode,
                    detail,
                )
            if not output_path.is_file():
                raise CodexCliRuntimeError.missing_output()
            output = output_path.read_text(encoding="utf-8").strip()
        if not output:
            raise CodexCliRuntimeError.empty_output(definition.name)
        return AgentResult(
            output=output,
            correlation_id=request.correlation_id,
            attributes=(
                ("model", definition.model),
                ("runtime", "codex-cli"),
            ),
        )


def _validate_definition(definition: AgentDefinition) -> None:
    if definition.can_delegate:
        raise CodexCliRuntimeError.delegation_unsupported(definition.name)
    if definition.model is None:
        raise CodexCliRuntimeError.missing_model(definition.name)
    if definition.tools:
        raise CodexCliRuntimeError.tools_unsupported(definition.name)


def _prompt(definition: AgentDefinition, request: AgentRequest) -> str:
    sections = [
        definition.instructions,
        (
            "Delegation is disabled. Complete this task directly without invoking "
            "tools, spawning agents, or changing files."
        ),
    ]
    if definition.output_template is not None:
        sections.extend(
            (
                "Follow this output template and replace every placeholder.",
                definition.output_template,
            )
        )
    sections.extend(("Input evidence:", request.prompt))
    return "\n\n".join(sections)
