use anyhow::{Context, Result};
use std::{
    env, fs,
    path::{Path, PathBuf},
    process::Command,
};

pub fn project_root() -> Result<PathBuf> {
    env::var_os("SEMANTIC_PROJECT_ROOT")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../.."))
        .canonicalize()
        .context("project root is unavailable")
}
pub fn codex_home() -> Result<PathBuf> {
    let home = env::var_os("CODEX_HOME")
        .map(PathBuf::from)
        .or_else(|| env::var_os("HOME").map(|p| PathBuf::from(p).join(".codex")))
        .context("CODEX_HOME or HOME is required")?;
    let home = home.canonicalize().context("CODEX_HOME must exist")?;
    anyhow::ensure!(home.is_dir(), "CODEX_HOME must be a directory");
    Ok(home)
}
fn string(value: &str) -> String {
    toml::Value::String(value.into()).to_string()
}
fn setting(command: &mut Command, key: &str, value: &str) {
    command.arg("-c").arg(format!("{key}={value}"));
}

/// Build native Codex arguments without changing authentication or global configuration.
pub fn configure(
    command: &mut Command,
    model: &str,
    cwd: &Path,
    home: &Path,
    api: &str,
    session_id: &str,
) -> Result<()> {
    anyhow::ensure!(
        !model.trim().is_empty() && model.len() <= 128,
        "model must contain 1..128 bytes"
    );
    command
        .arg("--model")
        .arg(model)
        .arg("--cd")
        .arg(cwd)
        .env("CODEX_HOME", home);
    let executable = env::current_exe()?.canonicalize()?;
    // This fork splits dotted override paths literally, including quote characters.
    // Put all server names inside one TOML value so names and dots stay intact.
    // The fork merges tables recursively; valid base transports remain disabled.
    let mut entries = Vec::new();
    let config = home.join("config.toml");
    if config.exists() {
        anyhow::ensure!(
            fs::metadata(&config)?.len() <= 1048576,
            "Codex configuration exceeds limit"
        );
        let config: toml::Value = toml::from_str(&fs::read_to_string(config)?)
            .context("Codex configuration is invalid")?;
        if let Some(servers) = config.get("mcp_servers").and_then(toml::Value::as_table) {
            anyhow::ensure!(servers.len() <= 100, "Codex MCP server count exceeds limit");
            for (key, server) in servers {
                if key == "semantic_research" {
                    continue;
                }
                // Disabled entries still deserialize. Supply an inert valid transport
                // only when the entry has no native command or HTTP URL at all.
                let transport = if server.get("command").is_none() && server.get("url").is_none() {
                    format!(
                        ",command={},args=[\"mcp\"]",
                        string(&executable.to_string_lossy())
                    )
                } else {
                    String::new()
                };
                entries.push(format!("{}={{enabled=false{transport}}}", string(key)));
            }
        }
    }
    entries.push(format!("semantic_research={{command={},args=[\"mcp\"],enabled=true,env={{SEMANTIC_API_URL={},Q2_MCP_DEBUG=\"1\"}}}}", string(&executable.to_string_lossy()), string(api)));
    setting(
        command,
        "mcp_servers",
        &format!("{{{}}}", entries.join(",")),
    );
    setting(
        command,
        "developer_instructions",
        &string(concat!(
            "You are the research coordinator for The Semantic. Work with the user in native Codex. ",
            "Use semantic_research to inspect retained agents, proposals, and research. ",
            "When the user asks to save a proposal, use proposal_save to retain its title, question, hypothesis, and plan as DRAFT. ",
            "Saving a proposal does not require experiment acceptance and never authorizes execution. ",
            "For hypothesis formation, refinement, or review, first call semantic_research.agent_get ",
            "with the exact selection {\"id\":\"hypothesis\",\"version\":\"1\"}. ",
            "Apply the retrieved definition as a drafting role within this same interactive coordinator, ",
            "under the existing authorization and tool limits; do not dispatch a separate worker. ",
            "Reuse answers already supplied in this chat. Ask one focused question only for a missing fact needed to draft or review the hypothesis. ",
            "During hypothesis drafting, do not query data, call research_run, or execute experiments. ",
            "If the exact agent is not registered, explain that hypothesis version 1 registration is required; ",
            "do not invent another agent, version, or substitute definition. If retrieval fails, report the failure before drafting. ",
            "Do not execute research until the user accepts a bounded question, hypothesis, and plan. ",
            "Never substitute a model after an access error. This interactive session is recorded separately from accepted experiments."
        )),
    );
    setting(
        command,
        "otel.exporter",
        &format!(
            "{{otlp-http={{endpoint={},protocol=\"json\",headers={{}}}}}}",
            string(&format!("{api}/api/research/v1/sessions/{session_id}/otel"))
        ),
    );
    for (key, value) in [
        ("otel.log_user_prompt", "true"),
        ("otel.log_agent_responses", "true"),
        ("otel.log_sse_deltas", "false"),
        ("otel.log_guardian_assessments", "false"),
        ("otel.tool_result.max_bytes", "0"),
        ("otel.trace_exporter", "\"none\""),
        ("otel.metrics_exporter", "\"none\""),
    ] {
        setting(command, key, value);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn native_settings_select_model_and_isolate_recording_without_bypassing_policy() {
        let directory = tempfile::tempdir().unwrap();
        fs::write(
            directory.path().join("config.toml"),
            "[mcp_servers.private]\ncommand='secret-value'\n[mcp_servers.\"with.dot\"]\ncommand='private-dot-command'\n[mcp_servers.airflow]\ntransport='unsupported-host-transport'\n",
        )
        .unwrap();
        let mut command = Command::new("fixture");
        configure(
            &mut command,
            "gpt-6.1-sol",
            directory.path(),
            directory.path(),
            "http://127.0.0.1:5056",
            "session1",
        )
        .unwrap();
        let args: Vec<_> = command.get_args().map(|v| v.to_string_lossy()).collect();
        assert_eq!(args[0], "--model");
        assert_eq!(args[1], "gpt-6.1-sol");
        let joined = args.join(" ");
        let overlay = args
            .iter()
            .find(|arg| arg.starts_with("mcp_servers="))
            .unwrap();
        let overlay: toml::Value = toml::from_str(overlay).unwrap();
        let servers = overlay["mcp_servers"].as_table().unwrap();
        assert_eq!(servers["private"]["enabled"].as_bool(), Some(false));
        assert_eq!(servers["with.dot"]["enabled"].as_bool(), Some(false));
        assert!(!servers.contains_key("\"private\""));
        assert_eq!(
            servers["semantic_research"]["enabled"].as_bool(),
            Some(true)
        );
        assert_eq!(servers["airflow"]["enabled"].as_bool(), Some(false));
        assert!(servers["airflow"]["command"].is_str());
        assert!(servers["private"].get("command").is_none());
        assert!(joined.contains("/sessions/session1/otel"));
        assert!(joined.contains("otel.tool_result.max_bytes=0"));
        let instructions = args
            .iter()
            .find(|arg| arg.starts_with("developer_instructions="))
            .unwrap();
        let instructions: toml::Value = toml::from_str(instructions).unwrap();
        let instructions = instructions["developer_instructions"].as_str().unwrap();
        assert!(instructions.contains("semantic_research.agent_get"));
        assert!(instructions.contains(r#"{"id":"hypothesis","version":"1"}"#));
        assert!(instructions.contains("drafting role within this same interactive coordinator"));
        assert!(instructions.contains("do not dispatch a separate worker"));
        assert!(instructions.contains("Reuse answers already supplied"));
        assert!(instructions.contains("Ask one focused question only for a missing fact"));
        assert!(
            instructions.contains("do not query data, call research_run, or execute experiments")
        );
        assert!(instructions.contains("hypothesis version 1 registration is required"));
        assert!(
            instructions.contains("do not invent another agent, version, or substitute definition")
        );
        assert!(instructions.contains("Do not execute research until the user accepts a bounded question, hypothesis, and plan"));
        assert!(!joined.contains("secret-value"));
        for forbidden in [
            "exec --json",
            "ignore-user-config",
            "ignore-rules",
            "dangerously",
            "features.code_mode",
        ] {
            assert!(!joined.contains(forbidden));
        }
    }
}
