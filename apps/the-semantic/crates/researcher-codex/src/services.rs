use anyhow::{Context, Result};
use reqwest::{Url, blocking::Client};
use serde_json::Value;
use std::{
    env,
    io::Read,
    net::TcpStream,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    thread,
    time::{Duration, Instant},
};

pub struct Services {
    pub api: String,
    pub health: Value,
    pub owned_api: Option<Child>,
}
impl Drop for Services {
    fn drop(&mut self) {
        if let Some(child) = &mut self.owned_api {
            stop(child);
        }
    }
}
pub fn stop(child: &mut Child) {
    if matches!(child.try_wait(), Ok(None)) {
        #[cfg(unix)]
        unsafe {
            if libc::getpgid(child.id() as i32) == child.id() as i32 {
                libc::kill(-(child.id() as i32), libc::SIGKILL);
            }
        }
        let _ = child.kill();
    }
    let _ = child.wait();
}
fn origin(value: &str) -> Result<Url> {
    let url = Url::parse(value).context("invalid local service URL")?;
    anyhow::ensure!(
        url.scheme() == "http"
            && url.host_str() == Some("127.0.0.1")
            && url.username().is_empty()
            && url.password().is_none()
            && url.path() == "/"
            && url.query().is_none()
            && url.fragment().is_none(),
        "service URL must be an HTTP 127.0.0.1 origin"
    );
    Ok(url)
}
fn get(url: &str) -> Result<Value> {
    let client = Client::builder()
        .no_proxy()
        .redirect(reqwest::redirect::Policy::none())
        .timeout(Duration::from_secs(1))
        .build()?;
    let response = client.get(url).send()?;
    anyhow::ensure!(response.status().is_success(), "service health failed");
    let mut bytes = vec![];
    response.take(65537).read_to_end(&mut bytes)?;
    anyhow::ensure!(bytes.len() <= 65536, "health response exceeds limit");
    Ok(serde_json::from_slice(&bytes)?)
}
fn listening(url: &Url) -> bool {
    TcpStream::connect_timeout(
        &format!("127.0.0.1:{}", url.port_or_known_default().unwrap_or(80))
            .parse()
            .expect("loopback socket"),
        Duration::from_millis(200),
    )
    .is_ok()
}
fn tracking_ready(tracking: &str) -> bool {
    get(&format!(
        "{tracking}/api/2.0/mlflow/experiments/search?max_results=1"
    ))
    .is_ok_and(|value| value["experiments"].is_array())
}
fn start_mlflow(tracking: &str) -> Result<()> {
    if tracking_ready(tracking) {
        return Ok(());
    }
    let url = origin(tracking)?;
    anyhow::ensure!(
        !listening(&url),
        "MLflow endpoint has an unknown or unhealthy listener; it was left unchanged"
    );
    anyhow::ensure!(
        tracking == "http://127.0.0.1:5055",
        "configured MLflow service is unavailable"
    );
    let home = env::var_os("HOME").context("HOME is required for existing MLflow LaunchAgent")?;
    let plist = PathBuf::from(home).join("Library/LaunchAgents/com.jeisenman.codex-mlflow.plist");
    anyhow::ensure!(
        plist.is_file(),
        "MLflow is unavailable and its existing LaunchAgent is not installed"
    );
    let uid = unsafe { libc::getuid() };
    let mut command = Command::new("launchctl");
    command
        .args([
            "kickstart",
            &format!("gui/{uid}/com.jeisenman.codex-mlflow"),
        ])
        .stdin(Stdio::null());
    let output =
        crate::process::execute(&mut command, Instant::now() + Duration::from_secs(5), true)?;
    if !output.success {
        let mut command = Command::new("launchctl");
        command
            .args(["bootstrap", &format!("gui/{uid}")])
            .arg(plist)
            .stdin(Stdio::null());
        let output =
            crate::process::execute(&mut command, Instant::now() + Duration::from_secs(5), true)?;
        anyhow::ensure!(output.success, "cannot start existing MLflow LaunchAgent");
    }
    let deadline = Instant::now() + Duration::from_secs(15);
    while Instant::now() < deadline {
        if tracking_ready(tracking) {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(200));
    }
    anyhow::bail!("existing MLflow LaunchAgent did not become ready")
}
fn validate(health: &Value, root: &Path, tracking: &str) -> Result<()> {
    anyhow::ensure!(
        health["status"] == "ok"
            && health["tracking_uri"] == tracking
            && health["project_root"].as_str() == root.to_str()
            && health["experiment_id"]
                .as_str()
                .is_some_and(|s| !s.is_empty())
            && health["capabilities"]
                .as_array()
                .is_some_and(|a| a.iter().any(|c| c == "sessions")),
        "API listener is not this project's session-capable service; it was left unchanged"
    );
    if let Ok(experiment) = env::var("MLFLOW_EXPERIMENT_NAME") {
        anyhow::ensure!(
            health["experiment_name"] == experiment,
            "API experiment name does not match configured name"
        );
    }
    Ok(())
}
/// Reuse matching services or start only this project's local API child.
pub fn ensure(root: &Path) -> Result<Services> {
    let api = env::var("SEMANTIC_API_URL")
        .unwrap_or_else(|_| "http://127.0.0.1:5056".into())
        .trim_end_matches('/')
        .to_string();
    let url = origin(&api)?;
    let tracking = env::var("MLFLOW_TRACKING_URI")
        .unwrap_or_else(|_| "http://127.0.0.1:5055".into())
        .trim_end_matches('/')
        .to_string();
    origin(&tracking)?;
    start_mlflow(&tracking)?;
    if let Ok(health) = get(&format!("{api}/health")) {
        validate(&health, root, &tracking)?;
        return Ok(Services {
            api,
            health,
            owned_api: None,
        });
    }
    anyhow::ensure!(
        !listening(&url),
        "API endpoint has an unknown or unhealthy listener; it was left unchanged"
    );
    let mut command = Command::new("uv");
    command
        .arg("run")
        .arg("--project")
        .arg(root.join("server"))
        .arg("semantic-api")
        .current_dir(root)
        .env(
            "SEMANTIC_API_PORT",
            url.port_or_known_default().unwrap_or(5056).to_string(),
        )
        .env("MLFLOW_TRACKING_URI", &tracking)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        command.process_group(0);
    }
    let child = command
        .spawn()
        .context("cannot start project API; install its uv dependencies")?;
    let mut services = Services {
        api,
        health: Value::Null,
        owned_api: Some(child),
    };
    let deadline = Instant::now() + Duration::from_secs(20);
    while Instant::now() < deadline {
        if let Some(child) = &mut services.owned_api {
            anyhow::ensure!(
                child.try_wait()?.is_none(),
                "project API exited before readiness"
            );
        }
        if let Ok(health) = get(&format!("{}/health", services.api)) {
            validate(&health, root, &tracking)?;
            services.health = health;
            return Ok(services);
        }
        thread::sleep(Duration::from_millis(200));
    }
    anyhow::bail!("project API did not become ready within 20 seconds")
}
