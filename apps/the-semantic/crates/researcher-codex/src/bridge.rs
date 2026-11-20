use anyhow::{Context, Result};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    env,
    io::{Read, Seek, SeekFrom, Write},
    path::PathBuf,
    process::{Command, Stdio},
    time::{Duration, Instant},
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    instructions: String,
    input: String,
}

pub fn codex_binary() -> Result<PathBuf> {
    crate::installed_codex::resolve(&crate::session_config::codex_home()?)
}

/// Complete one text-only turn through existing Codex authentication.
pub fn complete(model: &str, seconds: u64) -> Result<Value> {
    anyhow::ensure!(
        !model.trim().is_empty() && model.len() <= 128,
        "model is required"
    );
    anyhow::ensure!(
        (1..=300).contains(&seconds),
        "timeout must be 1..300 seconds"
    );
    let start = Instant::now();
    let mut bytes = Vec::new();
    std::io::stdin().take(262145).read_to_end(&mut bytes)?;
    anyhow::ensure!(bytes.len() <= 262144, "bridge input exceeds limit");
    let input: Input = serde_json::from_slice(&bytes).context("invalid bridge input")?;
    anyhow::ensure!(
        !input.instructions.trim().is_empty() && !input.input.trim().is_empty(),
        "instructions and input are required"
    );
    let codex_home = crate::session_config::codex_home()?;
    let directory = tempfile::tempdir()?;
    let mut prompt = tempfile::tempfile()?;
    write!(
        prompt,
        "{}\n\nThis is a text-only research request. Do not use tools or access files.\n\n{}",
        input.instructions, input.input
    )?;
    prompt.seek(SeekFrom::Start(0))?;
    let mut cmd = Command::new(codex_binary()?);
    cmd.current_dir(directory.path())
        .env("CODEX_HOME", &codex_home)
        .args([
            "exec",
            "--json",
            "--ephemeral",
            "--ignore-user-config",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--color",
            "never",
            "--model",
            model,
        ])
        .args([
            "-c",
            "model_reasoning_effort=\"low\"",
            "-c",
            "model_provider=\"openai\"",
            "-c",
            "features.shell_tool=false",
            "-c",
            "features.code_mode=false",
            "-c",
            "features.code_mode_only=false",
            "-c",
            "features.code_mode_host=false",
        ]);
    cmd.arg("-").stdin(Stdio::from(prompt));
    let output = super::process::execute(
        &mut cmd,
        start + Duration::from_secs(seconds),
        env::var_os("SEMANTIC_OWNED_PROCESS_GROUP").is_none(),
    )?;
    anyhow::ensure!(!output.timed_out, "provider timeout");
    anyhow::ensure!(
        output.success,
        "provider execution failed; check model access and Codex authentication"
    );
    parse_events(&output.stdout, start.elapsed().as_secs_f64())
}

fn parse_events(bytes: &[u8], duration: f64) -> Result<Value> {
    let text = std::str::from_utf8(bytes).context("invalid provider event encoding")?;
    let mut completed = false;
    let mut warning_count = 0_u64;
    let mut answer = None;
    let mut usage = json!({});
    for line in text.lines().filter(|line| !line.trim().is_empty()) {
        let event: Value = serde_json::from_str(line).context("invalid provider event JSON")?;
        match event["type"].as_str() {
            Some("turn.completed") => {
                completed = true;
                usage = event["usage"].clone();
            }
            Some("turn.failed" | "error") => {
                anyhow::bail!("provider rejected completion; check model access and authentication")
            }
            Some("item.started" | "item.updated" | "item.completed") => {
                let kind = event["item"]["type"]
                    .as_str()
                    .context("provider item type missing")?;
                match kind {
                    // Codex emits its running plan as metadata, without external I/O.
                    "agent_message" | "reasoning" | "todo_list" => {}
                    "command_execution" | "file_change" | "mcp_tool_call" | "collab_tool_call"
                    | "web_search" => {
                        anyhow::bail!(
                            "provider tool use is not supported (item_type={})",
                            safe_item_type(kind)
                        );
                    }
                    "error" => {
                        let category =
                            warning_category(event["item"]["message"].as_str().unwrap_or(""));
                        anyhow::ensure!(
                            ["unstable_features", "disabled_optional_code_mode"]
                                .contains(&category)
                                && event["type"] == "item.completed",
                            "provider warning requires review (item_type=error, category={category})"
                        );
                        warning_count += 1;
                    }
                    _ => anyhow::bail!(
                        "unsupported provider item (item_type={})",
                        safe_item_type(kind)
                    ),
                }
                if kind == "agent_message" && event["type"] == "item.completed" {
                    answer = event["item"]["text"].as_str().map(str::to_string);
                }
            }
            Some("thread.started" | "turn.started") => {}
            _ => anyhow::bail!("unsupported provider event"),
        }
    }
    anyhow::ensure!(completed, "provider did not complete a final turn");
    let output = answer
        .filter(|answer| !answer.trim().is_empty())
        .context("provider final output missing")?;
    let input_tokens = usage["input_tokens"]
        .as_u64()
        .context("provider input usage missing")?;
    let output_tokens = usage["output_tokens"]
        .as_u64()
        .context("provider output usage missing")?;
    Ok(
        json!({"output": output, "input_tokens": input_tokens, "output_tokens": output_tokens, "duration_seconds": duration, "warning_count": warning_count}),
    )
}

// The JSONL format merges several warning sources; retain only static categories.
fn warning_category(message: &str) -> &'static str {
    // Every invocation above explicitly disables Code Mode and its host. A model's
    // catalog metadata can still request it; this exact notice confirms fail-closed.
    if message
        == "Code Mode is unavailable because code-mode host is disabled. Code mode will fail closed; enable `features.code_mode_host` and install `codex-code-mode-host`."
    {
        return "disabled_optional_code_mode";
    }
    if message.starts_with("Code Mode is unavailable because") {
        return "code_mode_unavailable";
    }
    if message.starts_with("Codex is ignoring") {
        return "unrecognized_configuration";
    }
    if message.starts_with("model rerouted:") {
        "model_rerouted"
    } else if message.starts_with("in-process app-server event stream lagged;") {
        "event_stream_lag"
    } else if message.starts_with("Configured value for `permission_profile` is disallowed") {
        "permission_policy"
    } else if message.starts_with("Error parsing rules;") {
        "rules_policy"
    } else if message.starts_with("Under-development features enabled:") {
        "unstable_features"
    } else if message.contains("deprecated") {
        "deprecation"
    } else if message.contains("global instructions") {
        "global_instructions"
    } else {
        "unclassified"
    }
}

// Only enum-like ASCII identifiers can enter retained provider diagnostics.
fn safe_item_type(kind: &str) -> &str {
    if !kind.is_empty()
        && kind.len() <= 64
        && kind
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"_-".contains(&byte))
    {
        kind
    } else {
        "invalid"
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn accepts_plan_metadata_without_retaining_its_payload() {
        let events = b"{\"type\":\"item.updated\",\"item\":{\"type\":\"todo_list\",\"items\":[\"private-plan\"]}}\n{\"type\":\"item.completed\",\"item\":{\"type\":\"agent_message\",\"text\":\"answer\"}}\n{\"type\":\"turn.completed\",\"usage\":{\"input_tokens\":2,\"output_tokens\":1}}";
        let result = parse_events(events, 1.0).unwrap();
        assert_eq!(result["output"], "answer");
        assert!(!result.to_string().contains("private-plan"));
    }
    #[test]
    fn item_diagnostics_distinguish_tools_errors_and_unknown_protocol() {
        for kind in [
            "command_execution",
            "file_change",
            "mcp_tool_call",
            "collab_tool_call",
            "web_search",
        ] {
            let event = json!({"type":"item.started","item":{"type":kind,"payload":"private"}});
            let error = parse_events(event.to_string().as_bytes(), 0.0)
                .unwrap_err()
                .to_string();
            assert!(error.contains("tool use"));
            assert!(error.contains(kind));
            assert!(!error.contains("private"));
        }
        let error = parse_events(
            br#"{"type":"item.completed","item":{"type":"error","message":"private"}}"#,
            0.0,
        )
        .unwrap_err()
        .to_string();
        assert!(error.contains("category=unclassified"));
        assert!(!error.contains("private"));
        for kind in [
            "future_item".to_owned(),
            "secret\nvalue".to_owned(),
            "x".repeat(65),
        ] {
            let event = json!({"type":"item.started","item":{"type":kind,"payload":"private"}});
            let error = parse_events(event.to_string().as_bytes(), 0.0)
                .unwrap_err()
                .to_string();
            assert!(error.contains("unsupported provider item"));
            assert!(!error.contains("private"));
            assert!(!error.contains("secret"));
            assert!(error.len() < 110);
        }
    }
    #[test]
    fn accepts_only_source_pinned_feature_warning_with_completed_evidence() {
        let warning = json!({"type":"item.completed","item":{"type":"error","message":"Under-development features enabled: private-feature. Details /private/path"}});
        assert!(parse_events(warning.to_string().as_bytes(), 0.0).is_err());
        let final_events = "{\"type\":\"item.completed\",\"item\":{\"type\":\"agent_message\",\"text\":\"answer\"}}\n{\"type\":\"turn.completed\",\"usage\":{\"input_tokens\":2,\"output_tokens\":1}}";
        let result = parse_events(format!("{warning}\n{final_events}").as_bytes(), 1.0).unwrap();
        assert_eq!(result["warning_count"], 1);
        let disabled = json!({"type":"item.completed","item":{"type":"error","message":"Code Mode is unavailable because code-mode host is disabled. Code mode will fail closed; enable `features.code_mode_host` and install `codex-code-mode-host`."}});
        let result = parse_events(format!("{disabled}\n{final_events}").as_bytes(), 1.0).unwrap();
        assert_eq!(result["warning_count"], 1);
        assert!(!result.to_string().contains("private"));
        for (message, category) in [
            ("model rerouted: private -> other", "model_rerouted"),
            (
                "in-process app-server event stream lagged; dropped 1 events",
                "event_stream_lag",
            ),
            (
                "Configured value for `permission_profile` is disallowed by requirements",
                "permission_policy",
            ),
            (
                "Error parsing rules; custom rules not applied.",
                "rules_policy",
            ),
            ("some setting is deprecated", "deprecation"),
            ("invalid global instructions", "global_instructions"),
            ("private unknown message", "unclassified"),
            (
                "Code Mode is unavailable because failed to spawn private host",
                "code_mode_unavailable",
            ),
            (
                "Codex is ignoring 1 unrecognized configuration setting. private",
                "unrecognized_configuration",
            ),
        ] {
            let warning =
                json!({"type":"item.completed","item":{"type":"error","message":message}});
            let error = parse_events(format!("{warning}\n{final_events}").as_bytes(), 1.0)
                .unwrap_err()
                .to_string();
            assert!(error.contains(category));
            assert!(!error.contains("private"));
        }
        let incomplete = json!({"type":"item.started","item":{"type":"error","message":"Under-development features enabled: private"}});
        assert!(parse_events(format!("{incomplete}\n{final_events}").as_bytes(), 1.0).is_err());
    }
    #[test]
    fn requires_final_and_usage() {
        assert!(parse_events(b"", 0.0).is_err());
        assert!(parse_events(br#"{"type":"turn.completed"}"#, 0.0).is_err());
        let value = parse_events(b"{\"type\":\"item.completed\",\"item\":{\"type\":\"agent_message\",\"text\":\"answer\"}}\n{\"type\":\"turn.completed\",\"usage\":{\"input_tokens\":2,\"output_tokens\":1}}", 1.0).unwrap();
        assert_eq!(value["output"], "answer");
    }
    #[test]
    fn rejects_tools_and_provider_errors_without_details() {
        let error = parse_events(br#"{"type":"error","message":"secret"}"#, 0.0).unwrap_err();
        assert!(!error.to_string().contains("secret"));
        assert!(
            parse_events(
                br#"{"type":"item.started","item":{"type":"command_execution"}}"#,
                0.0
            )
            .is_err()
        );
    }
}
