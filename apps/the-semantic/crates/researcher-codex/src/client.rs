use crate::types::{Agent, Completion, Proposal, Spec};
use anyhow::{Context, Result};
use reqwest::{Url, blocking::Client as Http};
use serde_json::{Value, json};
use std::{
    env,
    io::Read,
    process::{Command, Stdio},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

#[derive(Clone)]
pub struct Client {
    base: Url,
}
impl Client {
    pub fn new() -> Result<Self> {
        let base = env::var("SEMANTIC_API_URL").unwrap_or_else(|_| "http://127.0.0.1:5056".into());
        Self::from_url(&base)
    }
    fn from_url(base: &str) -> Result<Self> {
        let base = Url::parse(base).context("invalid API URL")?;
        anyhow::ensure!(
            base.scheme() == "http"
                && base.host_str() == Some("127.0.0.1")
                && base.username().is_empty()
                && base.password().is_none()
                && base.query().is_none()
                && base.fragment().is_none()
                && base.path() == "/",
            "API URL must be an HTTP 127.0.0.1 origin"
        );
        Ok(Self { base })
    }
    pub fn request(
        &self,
        path: &str,
        body: Option<&Value>,
        deadline: Instant,
    ) -> Result<(Value, bool)> {
        let remaining = deadline
            .checked_duration_since(Instant::now())
            .context("API deadline expired")?;
        let http = Http::builder()
            .no_proxy()
            .redirect(reqwest::redirect::Policy::none())
            .timeout(remaining.min(Duration::from_secs(10)))
            .build()?;
        let url = self.base.join(path)?;
        let request = if let Some(body) = body {
            http.post(url).json(body)
        } else {
            http.get(url)
        };
        let response = request.send().context("research API unavailable")?;
        let status = response.status();
        let replay = status.as_u16() != 201
            || response
                .headers()
                .get("Idempotent-Replayed")
                .is_some_and(|v| v == "true");
        let mut bytes = Vec::new();
        response.take(2097153).read_to_end(&mut bytes)?;
        anyhow::ensure!(bytes.len() <= 2097152, "API response exceeds limit");
        let value: Value = serde_json::from_slice(&bytes).context("invalid API JSON")?;
        anyhow::ensure!(
            status.is_success(),
            "research API returned HTTP {}: {}",
            status.as_u16(),
            value["error"]["code"].as_str().unwrap_or("request_failed")
        );
        Ok((value, replay))
    }
    pub fn get(&self, path: &str) -> Result<Value> {
        Ok(self
            .request(path, None, Instant::now() + Duration::from_secs(10))?
            .0)
    }
    pub fn post(&self, path: &str, body: &Value) -> Result<Value> {
        Ok(self
            .request(path, Some(body), Instant::now() + Duration::from_secs(10))?
            .0)
    }
    pub fn run(&self, spec: Spec) -> Result<Value> {
        spec.validate()?;
        let deadline = Instant::now() + Duration::from_secs(spec.max_seconds);
        // Reserve a small part of the full run budget for terminal persistence.
        let execution_deadline =
            deadline - Duration::from_millis((spec.max_seconds * 100).min(1500));
        let (record, replay) = self.request(
            "api/research/v1/research",
            Some(&serde_json::to_value(&spec)?),
            execution_deadline,
        )?;
        if replay || record["status"] != "RUNNING" {
            return Ok(record);
        }
        let id = field(&record, "research_id")?;
        let attempt = field(&record, "attempt_id")?;
        let completion = match self.runtime(&spec, &record, execution_deadline) {
            Ok(value) => value,
            Err(error) => Completion::failure(
                attempt,
                Instant::now() >= execution_deadline,
                &error.to_string(),
            ),
        };
        Ok(self
            .request(
                &format!("api/research/v1/research/{}/complete", segment(id)?),
                Some(&serde_json::to_value(completion)?),
                deadline,
            )?
            .0)
    }
    /// Save a draft only; this operation cannot start the model runtime.
    pub fn save_proposal(&self, proposal: Proposal) -> Result<Value> {
        proposal.validate()?;
        self.post(
            "api/research/v1/proposals",
            &serde_json::to_value(proposal)?,
        )
    }
    /// Persist an unaccepted DRAFT attachment through the shared prepare operation.
    pub fn prepare_proposal(&self, proposal: Proposal) -> Result<Value> {
        proposal.validate()?;
        self.post(
            "api/research/v1/proposals/prepare",
            &serde_json::to_value(proposal)?,
        )
    }
    fn runtime(&self, spec: &Spec, record: &Value, deadline: Instant) -> Result<Completion> {
        let path = format!(
            "api/research/v1/agents/{}?version={}",
            segment(&spec.agent_id)?,
            segment(&spec.agent_version)?
        );
        let agent_value = self.request(&path, None, deadline)?.0;
        let agent: Agent =
            serde_json::from_value(agent_value.clone()).context("invalid pinned agent")?;
        anyhow::ensure!(
            agent.id == spec.agent_id
                && agent.version == spec.agent_version
                && agent.model == field(record, "model")?
                && agent.definition_digest.as_deref()
                    == Some(field(record, "agent_definition_digest")?)
                && agent.allowed_tools.is_empty()
                && agent.page_plugin == "run-summary",
            "pinned agent mismatch or unsupported configuration"
        );
        let mut request = tempfile::NamedTempFile::new()?;
        serde_json::to_writer(
            &mut request,
            &json!({"research_id": record["research_id"], "attempt_id": record["attempt_id"], "agent": agent_value, "spec": spec}),
        )?;
        let runtime = env::var_os("SEMANTIC_RUNTIME")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|| {
                std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                    .join("../../packages/runtime/dist/main.js")
            });
        anyhow::ensure!(
            runtime.is_file(),
            "runtime missing; build packages/runtime first"
        );
        let mut command = Command::new("node");
        command
            .arg(runtime)
            .arg("--request")
            .arg(request.path())
            .env("SEMANTIC_CLI", env::current_exe()?)
            .env("SEMANTIC_OWNED_PROCESS_GROUP", "1")
            .env(
                "SEMANTIC_DEADLINE_MS",
                SystemTime::now()
                    .checked_add(
                        deadline
                            .checked_duration_since(Instant::now())
                            .context("run deadline expired")?,
                    )
                    .context("runtime deadline overflow")?
                    .duration_since(UNIX_EPOCH)
                    .context("system clock precedes Unix epoch")?
                    .as_millis()
                    .to_string(),
            )
            .stdin(Stdio::null());
        let output = crate::process::execute(&mut command, deadline, true)?;
        anyhow::ensure!(!output.timed_out, "runtime timeout");
        let completion: Completion = serde_json::from_slice(&output.stdout)
            .context("runtime returned invalid completion")?;
        completion.validate(field(record, "attempt_id")?)?;
        anyhow::ensure!(
            output.success || completion.status != "FINISHED",
            "runtime process failed"
        );
        Ok(completion)
    }
}
pub fn segment(value: &str) -> Result<&str> {
    anyhow::ensure!(
        !value.is_empty()
            && value.len() <= 200
            && value
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"-_.".contains(&b))
            && value != "."
            && value != "..",
        "invalid identifier"
    );
    Ok(value)
}
fn field<'a>(value: &'a Value, name: &str) -> Result<&'a str> {
    value[name]
        .as_str()
        .with_context(|| format!("API record missing {name}"))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn validates_origins_and_identifiers() {
        assert!(Client::from_url("http://127.0.0.1:5056").is_ok());
        for origin in [
            "https://example.com",
            "http://localhost:5056",
            "http://127.0.0.1:5056/foo",
            "http://user@127.0.0.1",
        ] {
            assert!(Client::from_url(origin).is_err());
        }
        assert!(segment("../evil").is_err());
        assert!(segment("valid-1").is_ok());
    }
}
