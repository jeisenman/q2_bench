#![cfg(unix)]

use serde_json::{Value, json};
use std::{
    fs,
    io::Write,
    os::unix::fs::{PermissionsExt, symlink},
    path::{Path, PathBuf},
    process::{Command, Stdio},
};

fn executable(path: &Path, script: &str) {
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, script).unwrap();
    fs::set_permissions(path, fs::Permissions::from_mode(0o700)).unwrap();
}

fn installed(home: &Path) -> PathBuf {
    let root = home.join("packages/app-server-daemon");
    let release = root.join("releases/0.170.0-aarch64-apple-darwin");
    executable(
        &release.join("bin/codex"),
        r#"#!/bin/sh
case "$*" in *'--model gpt-6.1-sol'*) ;; *) exit 2;; esac
case "$*" in *--ignore-user-config*read-only*) ;; *) exit 3;; esac
case "$*" in *features.shell_tool=false*) ;; *) exit 4;; esac
test -d "$CODEX_HOME" || exit 5
prompt=$(cat)
case "$prompt" in *fixture-instructions*fixture-question*) ;; *) exit 6;; esac
printf '%s\n' '{"type":"item.completed","item":{"type":"agent_message","text":"managed-runtime-answer"}}' '{"type":"turn.completed","usage":{"input_tokens":9,"output_tokens":2}}'
"#,
    );
    fs::write(release.join("codex-package.json"), r#"{"layoutVersion":1,"version":"0.170.0","target":"aarch64-apple-darwin","entrypoint":"bin/codex"}"#).unwrap();
    symlink(&release, root.join("current")).unwrap();
    release.join("bin/codex")
}

fn command(home: &Path) -> Command {
    let mut command = Command::new(env!("CARGO_BIN_EXE_researcher-codex"));
    command
        .args([
            "complete",
            "--model",
            "gpt-6.1-sol",
            "--timeout-seconds",
            "3",
        ])
        .env("CODEX_HOME", home)
        .env_remove("CODEX_BINARY")
        .env_remove("HOME")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    command
}

fn complete(mut command: Command) -> std::process::Output {
    let mut child = command.spawn().unwrap();
    write!(
        child.stdin.take().unwrap(),
        "{}",
        json!({
            "instructions":"fixture-instructions", "input":"fixture-question"
        })
    )
    .unwrap();
    child.wait_with_output().unwrap()
}

#[test]
fn bridge_uses_managed_current_without_home_and_keeps_model_and_isolation() {
    let home = tempfile::tempdir().unwrap();
    installed(home.path());
    let output = complete(command(home.path()));
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    let result: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(result["output"], "managed-runtime-answer");
    assert_eq!(result["input_tokens"], 9);
}

#[test]
fn missing_managed_pointer_never_falls_back_to_debug_binary() {
    let root = tempfile::tempdir().unwrap();
    let codex_home = root.path().join(".codex");
    fs::create_dir(&codex_home).unwrap();
    let marker = root.path().join("debug-called");
    executable(
        &root.path().join("codex/codex-rs/target/debug/codex"),
        &format!("#!/bin/sh\ntouch '{}'\nexit 0\n", marker.display()),
    );
    let mut cmd = command(&codex_home);
    cmd.env("HOME", root.path());
    let output = complete(cmd);
    assert!(!output.status.success());
    assert!(String::from_utf8_lossy(&output.stdout).contains("active installed Codex pointer"));
    assert!(!marker.exists());
}

#[test]
fn explicit_override_wins_and_invalid_override_does_not_fall_back() {
    let home = tempfile::tempdir().unwrap();
    installed(home.path());
    let explicit = home.path().join("explicit-codex");
    executable(
        &explicit,
        "#!/bin/sh\ncat >/dev/null\nprintf '%s\\n' '{\"type\":\"item.completed\",\"item\":{\"type\":\"agent_message\",\"text\":\"explicit-answer\"}}' '{\"type\":\"turn.completed\",\"usage\":{\"input_tokens\":1,\"output_tokens\":1}}'\n",
    );
    let mut cmd = command(home.path());
    cmd.env("CODEX_BINARY", &explicit);
    let output = complete(cmd);
    assert!(output.status.success());
    assert_eq!(
        serde_json::from_slice::<Value>(&output.stdout).unwrap()["output"],
        "explicit-answer"
    );
    let mut cmd = command(home.path());
    cmd.env("CODEX_BINARY", home.path().join("missing"));
    let output = complete(cmd);
    assert!(!output.status.success());
    assert!(String::from_utf8_lossy(&output.stdout).contains("selected Codex binary is missing"));
}
