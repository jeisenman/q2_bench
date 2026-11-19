use rmcp::schemars;
use serde::{Deserialize, Serialize};
use serde_json::Value;

/// An unaccepted proposal saved without model execution or an agent selection.
#[derive(Clone, Debug, Deserialize, Serialize, rmcp::schemars::JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Proposal {
    pub title: String,
    pub question: String,
    pub hypothesis: String,
    pub plan: String,
    pub idempotency_key: String,
}
impl Proposal {
    pub fn validate(&self) -> anyhow::Result<()> {
        for (value, maximum) in [
            (&self.title, 1000),
            (&self.question, 16000),
            (&self.hypothesis, 16000),
            (&self.plan, 16000),
            (&self.idempotency_key, 128),
        ] {
            anyhow::ensure!(
                !value.trim().is_empty() && value.chars().count() <= maximum,
                "proposal text must be nonempty and within its character limit"
            );
        }
        Ok(())
    }
}

/// Immutable research agent definition.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Agent {
    pub id: String,
    pub version: String,
    pub name: String,
    pub purpose: String,
    pub instructions: String,
    pub model: String,
    pub allowed_tools: Vec<String>,
    pub page_plugin: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub definition_digest: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub mlflow_run_id: Option<String>,
}

/// Accepted, bounded research specification.
#[derive(Clone, Debug, Deserialize, Serialize, rmcp::schemars::JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Spec {
    pub title: String,
    pub question: String,
    pub hypothesis: String,
    pub plan: String,
    pub agent_id: String,
    pub agent_version: String,
    pub accepted: bool,
    pub max_runs: u32,
    pub max_seconds: u64,
    pub idempotency_key: String,
}
impl Spec {
    pub fn validate(&self) -> anyhow::Result<()> {
        anyhow::ensure!(self.accepted, "research must be accepted");
        anyhow::ensure!(self.max_runs == 1, "max_runs must equal 1");
        anyhow::ensure!(
            (1..=300).contains(&self.max_seconds),
            "max_seconds must be 1..300"
        );
        for value in [
            &self.title,
            &self.question,
            &self.hypothesis,
            &self.plan,
            &self.agent_id,
            &self.agent_version,
            &self.idempotency_key,
        ] {
            anyhow::ensure!(
                !value.trim().is_empty() && value.len() <= 65536,
                "specification text must contain 1..65536 bytes"
            );
        }
        Ok(())
    }
}

/// Terminal runtime evidence written to the research API.
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Completion {
    pub attempt_id: String,
    pub status: String,
    pub output: String,
    pub metrics: std::collections::BTreeMap<String, f64>,
    pub sdk_events: Vec<Value>,
    pub error: Option<String>,
}
impl Completion {
    pub fn failure(attempt: &str, killed: bool, message: &str) -> Self {
        Self {
            attempt_id: attempt.into(),
            status: if killed { "KILLED" } else { "FAILED" }.into(),
            output: String::new(),
            metrics: Default::default(),
            sdk_events: vec![],
            error: Some(message.into()),
        }
    }
    pub fn validate(&self, attempt: &str) -> anyhow::Result<()> {
        anyhow::ensure!(self.attempt_id == attempt, "runtime attempt mismatch");
        anyhow::ensure!(
            ["FINISHED", "FAILED", "KILLED"].contains(&self.status.as_str()),
            "invalid runtime status"
        );
        anyhow::ensure!(
            self.metrics.values().all(|v| v.is_finite()),
            "metrics must be finite"
        );
        anyhow::ensure!(
            self.output.len() <= 1048576 && self.sdk_events.len() <= 1000,
            "runtime evidence exceeds limit"
        );
        anyhow::ensure!(
            self.status != "FINISHED" || (!self.output.trim().is_empty() && self.error.is_none()),
            "successful runtime needs output and no error"
        );
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn specifications_require_acceptance_and_one_bounded_attempt() {
        let mut spec = Spec {
            title: "t".into(),
            question: "q".into(),
            hypothesis: "h".into(),
            plan: "p".into(),
            agent_id: "a".into(),
            agent_version: "1".into(),
            accepted: true,
            max_runs: 1,
            max_seconds: 1,
            idempotency_key: "k".into(),
        };
        assert!(spec.validate().is_ok());
        spec.max_seconds = 300;
        assert!(spec.validate().is_ok());
        spec.max_seconds = 301;
        assert!(spec.validate().is_err());
        spec.max_seconds = 0;
        assert!(spec.validate().is_err());
        spec.max_seconds = 1;
        spec.max_runs = 2;
        assert!(spec.validate().is_err());
        spec.max_runs = 1;
        spec.accepted = false;
        assert!(spec.validate().is_err());
    }
    #[test]
    fn completions_need_owned_attempt_and_success_evidence() {
        let mut completion = Completion::failure("a", false, "provider failed");
        assert!(completion.validate("a").is_ok());
        assert!(completion.validate("other").is_err());
        completion.status = "FINISHED".into();
        assert!(completion.validate("a").is_err());
        completion.output = "answer".into();
        completion.error = None;
        assert!(completion.validate("a").is_ok());
        completion.metrics.insert("invalid".into(), f64::NAN);
        assert!(completion.validate("a").is_err());
    }
}
