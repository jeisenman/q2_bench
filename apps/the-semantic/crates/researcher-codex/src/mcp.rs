use anyhow::Result;
use rmcp::{
    ServerHandler, ServiceExt,
    handler::server::wrapper::Parameters,
    model::{CallToolResult, ContentBlock, ServerCapabilities, ServerConfig},
    schemars, tool, tool_handler, tool_router,
};
use serde::Deserialize;
use serde_json::Value;

#[derive(Clone)]
struct ResearchServer;
#[derive(Deserialize, schemars::JsonSchema)]
#[serde(deny_unknown_fields)]
struct ListArgs {
    #[serde(default = "newest")]
    order: String,
}
fn newest() -> String {
    "newest".into()
}
#[derive(Deserialize, schemars::JsonSchema)]
#[serde(deny_unknown_fields)]
struct GetArgs {
    research_id: String,
}
#[derive(Deserialize, schemars::JsonSchema)]
#[serde(deny_unknown_fields)]
struct AgentArgs {
    id: String,
    version: String,
}
#[derive(Deserialize, schemars::JsonSchema)]
#[serde(deny_unknown_fields)]
struct ProposalGetArgs {
    proposal_id: String,
}

async fn operation(
    f: impl FnOnce(crate::client::Client) -> Result<Value> + Send + 'static,
) -> CallToolResult {
    let start = std::time::Instant::now();
    let result = tokio::task::spawn_blocking(move || f(crate::client::Client::new()?)).await;
    if std::env::var("Q2_MCP_DEBUG").as_deref() == Ok("1") {
        eprintln!(
            "research operation duration_ms={}",
            start.elapsed().as_millis()
        );
    }
    match result {
        Ok(Ok(value)) => CallToolResult::success(vec![ContentBlock::text(value.to_string())]),
        Ok(Err(error)) => CallToolResult::error(vec![ContentBlock::text(error.to_string())]),
        Err(_) => CallToolResult::error(vec![ContentBlock::text("research operation failed")]),
    }
}
#[tool_router]
impl ResearchServer {
    fn new() -> Self {
        Self
    }
    #[tool(
        description = "Save an unaccepted DRAFT proposal; does not execute research or call a model"
    )]
    async fn proposal_save(
        &self,
        Parameters(proposal): Parameters<crate::types::Proposal>,
    ) -> CallToolResult {
        operation(move |client| client.save_proposal(proposal)).await
    }
    #[tool(
        description = "Prepare and persist an unaccepted DRAFT attachment; never accepts or executes research"
    )]
    async fn proposal_prepare(
        &self,
        Parameters(proposal): Parameters<crate::types::Proposal>,
    ) -> CallToolResult {
        operation(move |client| client.prepare_proposal(proposal)).await
    }
    #[tool(description = "List retained DRAFT proposals in date order")]
    async fn proposal_list(&self, Parameters(args): Parameters<ListArgs>) -> CallToolResult {
        operation(move |client| {
            anyhow::ensure!(
                ["newest", "oldest"].contains(&args.order.as_str()),
                "order must be newest or oldest"
            );
            client.get(&format!("api/research/v1/proposals?order={}", args.order))
        })
        .await
    }
    #[tool(description = "Get one retained DRAFT proposal by its exact ID")]
    async fn proposal_get(&self, Parameters(args): Parameters<ProposalGetArgs>) -> CallToolResult {
        operation(move |client| {
            client.get(&format!(
                "api/research/v1/proposals/{}",
                crate::client::segment(&args.proposal_id)?
            ))
        })
        .await
    }
    #[tool(description = "List retained research records in date order")]
    async fn research_list(&self, Parameters(args): Parameters<ListArgs>) -> CallToolResult {
        operation(move |client| {
            anyhow::ensure!(
                ["newest", "oldest"].contains(&args.order.as_str()),
                "order must be newest or oldest"
            );
            client.get(&format!("api/research/v1/research?order={}", args.order))
        })
        .await
    }
    #[tool(description = "Get one retained research record by its exact ID")]
    async fn research_get(&self, Parameters(args): Parameters<GetArgs>) -> CallToolResult {
        operation(move |client| {
            client.get(&format!(
                "api/research/v1/research/{}",
                crate::client::segment(&args.research_id)?
            ))
        })
        .await
    }
    #[tool(description = "List immutable registered research agents")]
    async fn agent_list(&self) -> CallToolResult {
        operation(|client| client.get("api/research/v1/agents")).await
    }
    #[tool(description = "Get one exact immutable agent version")]
    async fn agent_get(&self, Parameters(args): Parameters<AgentArgs>) -> CallToolResult {
        operation(move |client| {
            client.get(&format!(
                "api/research/v1/agents/{}?version={}",
                crate::client::segment(&args.id)?,
                crate::client::segment(&args.version)?
            ))
        })
        .await
    }
    #[tool(
        description = "Execute one explicitly accepted bounded research specification; persists output and evidence"
    )]
    async fn research_run(
        &self,
        Parameters(spec): Parameters<crate::types::Spec>,
    ) -> CallToolResult {
        operation(move |client| client.run(spec)).await
    }
}
#[tool_handler]
impl ServerHandler for ResearchServer {
    fn get_info(&self) -> ServerConfig {
        ServerConfig::new(ServerCapabilities::builder().enable_tools().build()).with_instructions(
            "Bounded local research API adapter. proposal_prepare and proposal_save persist a DRAFT without execution. research_run performs one accepted model call.",
        )
    }
}
/// Start the official Rust MCP SDK stdio server.
pub async fn serve() -> Result<()> {
    let service = ResearchServer::new()
        .serve(rmcp::transport::stdio())
        .await?;
    service.waiting().await?;
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn exposes_only_nine_finite_tools() {
        let tools = ResearchServer::tool_router().list_all();
        let mut names: Vec<_> = tools.iter().map(|tool| tool.name.as_ref()).collect();
        names.sort();
        assert_eq!(
            names,
            [
                "agent_get",
                "agent_list",
                "proposal_get",
                "proposal_list",
                "proposal_prepare",
                "proposal_save",
                "research_get",
                "research_list",
                "research_run"
            ]
        );
        for tool in tools {
            assert_eq!(tool.input_schema.get("type").unwrap(), "object");
        }
    }
}
