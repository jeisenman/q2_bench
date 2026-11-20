mod bridge;
mod chat;
mod client;
mod gherkin;
mod installed_codex;
mod mcp;
mod process;
mod services;
mod session_config;
mod types;
use anyhow::{Context, Result};
use clap::{Parser, Subcommand};
use serde_json::{Value, json};
use std::{fs, path::PathBuf};

#[derive(Parser)]
#[command(
    name = "researcher-codex",
    version,
    about = "Bounded local research CLI and MCP server"
)]
struct Args {
    #[command(subcommand)]
    command: Action,
}
#[derive(Subcommand)]
enum Action {
    Doctor,
    Chat {
        #[arg(long, default_value = "gpt-6.1-sol")]
        model: String,
        #[arg(long)]
        cwd: Option<PathBuf>,
        #[arg(long)]
        check: bool,
    },
    Agent {
        #[command(subcommand)]
        command: AgentAction,
    },
    Agents,
    Proposal {
        #[command(subcommand)]
        command: ProposalAction,
    },
    Proposals {
        #[arg(long, default_value="newest", value_parser=["newest", "oldest"])]
        order: String,
    },
    List {
        #[arg(long, default_value="newest", value_parser=["newest", "oldest"])]
        order: String,
    },
    Get {
        research_id: String,
    },
    Run {
        #[arg(long)]
        spec: PathBuf,
    },
    Complete {
        #[arg(long)]
        model: String,
        #[arg(long)]
        timeout_seconds: u64,
    },
    Mcp,
}
#[derive(Subcommand)]
enum AgentAction {
    Put { file: PathBuf },
}
#[derive(Subcommand)]
enum ProposalAction {
    Save { file: PathBuf },
    Get { proposal_id: String },
}
fn read_json(file: PathBuf) -> Result<Value> {
    anyhow::ensure!(
        fs::metadata(&file)?.len() <= 262144,
        "JSON file exceeds limit"
    );
    serde_json::from_slice(&fs::read(file)?).context("invalid input JSON")
}
fn run(action: Action) -> Result<Value> {
    if let Action::Complete {
        model,
        timeout_seconds,
    } = action
    {
        return bridge::complete(&model, timeout_seconds);
    }
    let client = client::Client::new()?;
    match action {
        Action::Doctor => {
            let health = client.get("health")?;
            let binary = bridge::codex_binary()?;
            anyhow::ensure!(binary.is_file(), "Codex executable missing");
            Ok(json!({"status":"ok", "api":health, "codex_binary":binary}))
        }
        Action::Agent {
            command: AgentAction::Put { file },
        } => {
            let value = read_json(file)?;
            let _: types::Agent = serde_json::from_value(value.clone()).context("invalid agent")?;
            client.post("api/research/v1/agents", &value)
        }
        Action::Agents => client.get("api/research/v1/agents"),
        Action::Proposal { command } => match command {
            ProposalAction::Save { file } => client.save_proposal(
                serde_json::from_value(read_json(file)?).context("invalid proposal")?,
            ),
            ProposalAction::Get { proposal_id } => client.get(&format!(
                "api/research/v1/proposals/{}",
                client::segment(&proposal_id)?
            )),
        },
        Action::Proposals { order } => {
            client.get(&format!("api/research/v1/proposals?order={order}"))
        }
        Action::List { order } => client.get(&format!("api/research/v1/research?order={order}")),
        Action::Get { research_id } => client.get(&format!(
            "api/research/v1/research/{}",
            client::segment(&research_id)?
        )),
        Action::Run { spec } => client.run(
            serde_json::from_value(read_json(spec)?).context("invalid research specification")?,
        ),
        _ => anyhow::bail!("unsupported command"),
    }
}
fn main() {
    let args = Args::parse();
    if let Action::Chat { model, cwd, check } = args.command {
        match chat::run(model, cwd, check) {
            Ok(code) => std::process::exit(code),
            Err(error) => {
                eprintln!("researcher-codex chat: {error}");
                std::process::exit(1);
            }
        }
    }
    if matches!(args.command, Action::Mcp) {
        let result = tokio::runtime::Runtime::new()
            .expect("Tokio runtime")
            .block_on(mcp::serve());
        if result.is_err() {
            eprintln!("MCP server failed");
            std::process::exit(1);
        }
        return;
    }
    let is_run = matches!(args.command, Action::Run { .. });
    match run(args.command) {
        Ok(value) => {
            println!("{value}");
            if is_run && matches!(value["status"].as_str(), Some("FAILED" | "KILLED")) {
                std::process::exit(1);
            }
        }
        Err(error) => {
            println!(
                "{}",
                json!({"error":{"code":"operation_failed", "message":error.to_string()}})
            );
            std::process::exit(1);
        }
    }
}
