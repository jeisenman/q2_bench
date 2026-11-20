//! Finite committed-source reads through the existing research API.
use crate::client::Client;
use anyhow::Result;
use rmcp::schemars;
use serde::Deserialize;
use serde_json::Value;

#[derive(Clone, Copy, Default, Deserialize, schemars::JsonSchema)]
#[serde(rename_all = "lowercase")]
pub enum SearchMode {
    #[default]
    Keyword,
    Vector,
}
#[derive(Deserialize, schemars::JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct SearchArgs {
    pub query: String,
    #[serde(default)]
    pub mode: SearchMode,
    #[serde(default)]
    pub offset: u32,
    pub commit: Option<String>,
}
#[derive(Deserialize, schemars::JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct FeatureArgs {
    pub path: String,
    pub commit: String,
}
fn commit(value: &str) -> Result<()> {
    anyhow::ensure!(
        value.len() == 40
            && value
                .bytes()
                .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase()),
        "a full lowercase source commit is required"
    );
    Ok(())
}
fn search_path(args: &SearchArgs) -> Result<String> {
    anyhow::ensure!(
        !matches!(args.mode, SearchMode::Vector),
        "gherkin_vector_disabled: Vector search is disabled."
    );
    let query = args.query.trim();
    anyhow::ensure!(
        !query.is_empty() && query.chars().count() <= 200 && !query.chars().any(char::is_control),
        "a literal query of 1..200 characters is required"
    );
    anyhow::ensure!(args.offset <= 10000, "offset must be from 0 to 10000");
    let mut url = reqwest::Url::parse("http://127.0.0.1/api/research/v1/gherkin/features")?;
    url.query_pairs_mut()
        .append_pair("query", query)
        .append_pair("mode", "keyword")
        .append_pair("offset", &args.offset.to_string());
    if let Some(value) = &args.commit {
        commit(value)?;
        url.query_pairs_mut().append_pair("commit", value);
    }
    Ok(format!("{}?{}", url.path(), url.query().unwrap_or("")))
}
impl Client {
    /// Report supported retrieval modes without reading a checkout or calling models.
    pub fn gherkin_capabilities(&self) -> Result<Value> {
        self.get("api/research/v1/gherkin/capabilities")
    }
    /// Find literal keyword matches, retaining the source commit and bounded page.
    pub fn gherkin_search(&self, args: SearchArgs) -> Result<Value> {
        self.get(&search_path(&args)?)
    }
    /// Read one tracked feature at its exact immutable source commit.
    pub fn gherkin_feature(&self, args: FeatureArgs) -> Result<Value> {
        commit(&args.commit)?;
        anyhow::ensure!(
            !args.path.is_empty()
                && args.path.chars().count() <= 2048
                && args.path.ends_with(".feature")
                && !args.path.contains('\\')
                && !args.path.chars().any(char::is_control)
                && args
                    .path
                    .split('/')
                    .all(|part| !["", ".", ".."].contains(&part)),
            "a tracked relative feature path is required"
        );
        let mut url = reqwest::Url::parse("http://127.0.0.1/api/research/v1/gherkin/feature")?;
        url.query_pairs_mut()
            .append_pair("path", &args.path)
            .append_pair("commit", &args.commit);
        self.get(&format!("{}?{}", url.path(), url.query().unwrap_or("")))
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn vector_is_disabled_before_query_validation_or_http() {
        let error = search_path(&SearchArgs {
            query: String::new(),
            mode: SearchMode::Vector,
            offset: u32::MAX,
            commit: None,
        })
        .unwrap_err();
        assert!(error.to_string().contains("gherkin_vector_disabled"));
    }
    #[test]
    fn keyword_encodes_literal_text_and_preserves_pin_and_bounds() {
        let mut args = SearchArgs {
            query: "a&b + c".into(),
            mode: SearchMode::Keyword,
            offset: 25,
            commit: Some("a".repeat(40)),
        };
        let url = search_path(&args).unwrap();
        assert!(url.contains("query=a%26b+%2B+c"));
        assert!(url.contains("offset=25"));
        assert!(url.ends_with(&"a".repeat(40)));
        args.offset = 10001;
        assert!(search_path(&args).is_err());
        args.offset = 0;
        args.commit = Some("A".repeat(40));
        assert!(search_path(&args).is_err());
    }
}
