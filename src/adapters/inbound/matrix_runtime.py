"""Isolated runtime construction for benchmark candidates and judges."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from workspaces.data_engineering.benchmarks import ModelProfile

CODEX_AUTH_FILES = (
    Path("config.toml"),
    Path("cloud-config-bundle-cache.json"),
    Path("models_cache.json"),
    Path("system-ca-bundle.pem"),
    Path(".runtime/netskope-ca-bundle.pem"),
)
SAFE_PROFILE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class MatrixRunError(RuntimeError):
    """Raised when a candidate or judge process fails."""

    @classmethod
    def process_failed(cls, name: str, returncode: int) -> MatrixRunError:
        """Create an error for a failed candidate or judge process."""
        return cls(f"{name} failed with exit code {returncode}")

    @classmethod
    def invalid_judgment(cls, profile: str) -> MatrixRunError:
        """Create an error for malformed judge output."""
        return cls(f"judge returned invalid JSON for {profile}")

    @classmethod
    def judge_failed(cls, profile: str, returncode: int) -> MatrixRunError:
        """Create an error for a failed judge process."""
        return cls(f"judge for {profile} failed with exit code {returncode}")

    @classmethod
    def path_outside_workspace(cls, path: Path) -> MatrixRunError:
        """Create an error for a path unavailable to a worker container."""
        return cls(f"container path must be inside workspace or output: {path}")

    @classmethod
    def missing_candidate_inputs(cls) -> MatrixRunError:
        """Create an error for an empty candidate evidence set."""
        return cls("matrix candidate inputs must not be empty")


@dataclass(frozen=True, slots=True)
class _CommandOptions:
    workspace: Path
    sandbox: str
    final_path: Path
    json_output: bool
    schema_path: Path | None = None
    runtime: str = "process"
    container_image: str = ""
    output_root: Path | None = None
    auth_source: Path | None = None


def _codex_command(profile: ModelProfile, options: _CommandOptions) -> list[str]:
    if options.runtime == "container" and options.sandbox != "read-only":
        message = "container matrix sandbox must be read-only"
        raise MatrixRunError(message)
    codex_sandbox = (
        "danger-full-access" if options.runtime == "container" else options.sandbox
    )
    command = [
        "--model",
        profile.model,
        "--profile",
        "bedrock",
        "-c",
        f'model_reasoning_effort="{profile.reasoning_effort}"',
        "-c",
        'model_providers.amazon-bedrock.aws.profile="benchmark"',
        "--sandbox",
        codex_sandbox,
        "--ask-for-approval",
        "never",
        "--cd",
        _runtime_path(options.workspace, options),
        "exec",
        "--skip-git-repo-check",
        "--ephemeral",
        "--output-last-message",
        _runtime_path(options.final_path, options),
    ]
    if options.json_output:
        command.append("--json")
    if options.schema_path is not None:
        command.extend(("--output-schema", _runtime_path(options.schema_path, options)))
    if options.runtime != "container":
        return ["codex", *command]
    if options.output_root is None or options.auth_source is None:
        message = "container runtime requires output_root and auth_source"
        raise MatrixRunError(message)
    return [
        "docker",
        "run",
        "--rm",
        "--read-only",
        "--user",
        "1000:1000",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "256",
        "--memory",
        "4g",
        "--cpus",
        "2",
        "--env",
        "SSL_CERT_FILE=/run/agent-auth/ca-bundle.pem",
        "--env",
        "AWS_PROFILE=benchmark",
        "--env",
        "AWS_SHARED_CREDENTIALS_FILE=/run/agent-auth/credentials",
        "--env",
        "AWS_REGION=us-east-2",
        "--env",
        "CODEX_SOURCE_HOME=/run/agent-auth",
        "--tmpfs",
        "/home/agentbench/.bedrock_codex:uid=1000,gid=1000,mode=0700",
        "--tmpfs",
        "/tmp:uid=1000,gid=1000,mode=0700",
        "--tmpfs",
        "/workspace/src:uid=1000,gid=1000,mode=0500",
        "--volume",
        f"{options.workspace.resolve()}:/evaluation:ro",
        "--volume",
        f"{options.output_root.resolve()}:/output",
        "--volume",
        f"{(options.auth_source / 'config.toml').resolve()}:"
        "/run/agent-auth/config.toml:ro",
        "--volume",
        f"{(options.auth_source / '.runtime/aws-credentials').resolve()}:"
        "/run/agent-auth/credentials:ro",
        "--volume",
        f"{(options.auth_source / '.runtime/netskope-ca-bundle.pem').resolve()}:"
        "/run/agent-auth/ca-bundle.pem:ro",
        "--workdir",
        "/evaluation",
        options.container_image,
        "codex",
        *command,
    ]


def _runtime_path(path: Path, options: _CommandOptions) -> str:
    if options.runtime != "container":
        return str(path)
    try:
        relative = path.resolve().relative_to(options.workspace.resolve())
        return str(Path("/evaluation") / relative)
    except ValueError:
        if options.output_root is not None:
            try:
                relative = path.resolve().relative_to(options.output_root.resolve())
                return str(Path("/output") / relative)
            except ValueError:
                pass
    raise MatrixRunError.path_outside_workspace(path)


@contextmanager
def _candidate_workspace(
    workspace: Path,
    inputs: tuple[Path, ...],
) -> Iterator[Path]:
    if not inputs:
        raise MatrixRunError.missing_candidate_inputs()
    workspace_root = workspace.resolve()
    sources = tuple(_validated_input(workspace_root, item) for item in inputs)
    with TemporaryDirectory(prefix="agentbench-evidence-") as temporary:
        root = Path(temporary)
        for relative, source in zip(inputs, sources, strict=True):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        yield root


def _validated_input(workspace_root: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        message = f"matrix input path must be workspace-relative: {relative}"
        raise MatrixRunError(message)
    source = workspace_root / relative
    if _has_symlink_component(workspace_root, relative):
        message = f"matrix input may not contain symlinks: {relative}"
        raise MatrixRunError(message)
    source = source.resolve()
    try:
        source.relative_to(workspace_root)
    except ValueError as error:
        message = f"matrix input resolves outside workspace: {relative}"
        raise MatrixRunError(message) from error
    if not source.is_file() or source.is_symlink():
        message = f"matrix input does not exist: {source}"
        raise MatrixRunError(message)
    return source


@contextmanager
def _codex_auth_source() -> Iterator[Path]:
    source_root = Path(
        os.environ.get("CODEX_HOME", str(Path.home() / ".bedrock_codex"))
    )
    if source_root.is_symlink():
        message = f"Codex authentication root may not be a symlink: {source_root}"
        raise MatrixRunError(message)
    with TemporaryDirectory(prefix="agentbench-auth-") as temporary:
        target_root = Path(temporary)
        copied = 0
        for relative in CODEX_AUTH_FILES:
            source = source_root / relative
            if not source.is_file():
                continue
            if _has_symlink_component(source_root, relative):
                message = (
                    f"allowlisted Codex authentication path is a symlink: {relative}"
                )
                raise MatrixRunError(message)
            target = target_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied += 1
        if copied == 0:
            message = (
                f"no allowlisted Codex authentication files found in {source_root}"
            )
            raise MatrixRunError(message)
        _write_aws_credentials(target_root)
        yield target_root


def _has_symlink_component(root: Path, relative: Path) -> bool:
    """Return whether any existing path component below root is a symlink."""
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            return True
    return False


def _write_aws_credentials(target_root: Path) -> None:
    config = tomllib.loads((target_root / "config.toml").read_text(encoding="utf-8"))
    provider = config.get("model_providers", {}).get("amazon-bedrock", {})
    aws = provider.get("aws", {}) if isinstance(provider, dict) else {}
    source_profile = aws.get("profile") if isinstance(aws, dict) else None
    if not isinstance(source_profile, str) or not source_profile:
        message = "Codex Bedrock configuration is missing an AWS profile"
        raise MatrixRunError(message)
    process = subprocess.run(
        (
            "aws",
            "configure",
            "export-credentials",
            "--profile",
            source_profile,
            "--format",
            "process",
        ),
        check=False,
        capture_output=True,
        text=True,
    )
    if process.returncode != 0:
        message = f"failed to refresh AWS credentials for profile {source_profile}"
        raise MatrixRunError(message)
    values = json.loads(process.stdout)
    required = ("AccessKeyId", "SecretAccessKey", "SessionToken")
    if any(not values.get(key) for key in required):
        message = "refreshed AWS credentials are missing required fields"
        raise MatrixRunError(message)
    target = target_root / ".runtime/aws-credentials"
    target.write_text(
        "\n".join(
            (
                "[benchmark]",
                f"aws_access_key_id={values['AccessKeyId']}",
                f"aws_secret_access_key={values['SecretAccessKey']}",
                f"aws_session_token={values['SessionToken']}",
                "",
            )
        ),
        encoding="utf-8",
    )
    target.chmod(0o600)
