use crate::{client::Client, services, session_config as config};
use anyhow::{Context, Result};
use chrono::Utc;
use serde_json::{Value, json};
use std::{
    env,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    thread,
    time::{Duration, Instant},
};

fn lifecycle(client: &Client, session: &str, phase: &str) -> Result<()> {
    client.post(&format!("api/research/v1/sessions/{session}/events"), &json!({"events":[{"event_id":format!("launcher-{session}-{phase}"),"at":Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Millis,true),"kind":"lifecycle","text":null,"tool_name":null,"status":phase}]}))?;
    Ok(())
}
fn close(
    client: &Client,
    session: &str,
    status: &str,
    exit: Option<i32>,
    error: Option<&str>,
) -> Result<Value> {
    client.post(
        &format!("api/research/v1/sessions/{session}/close"),
        &json!({"status":status,"exit_code":exit,"error":error}),
    )
}
struct Desktop(Option<Child>);
impl Drop for Desktop {
    fn drop(&mut self) {
        if let Some(child) = &mut self.0 {
            services::stop(child);
        }
    }
}
fn desktop(root: &Path, session: &str, api: &str) -> Result<Desktop> {
    let binary = env::var_os("SEMANTIC_ELECTRON_BINARY")
        .map(PathBuf::from)
        .unwrap_or_else(|| root.join("node_modules/.bin/electron"));
    anyhow::ensure!(
        root.join("apps/desktop/dist-electron/main.cjs").is_file()
            && root.join("apps/desktop/dist/index.html").is_file(),
        "Electron build is missing; run npm run build:desktop"
    );
    let mut command = Command::new(binary);
    command
        .arg(root.join("apps/desktop"))
        .arg("--research-session")
        .arg(session)
        .env("SEMANTIC_API_URL", api)
        .env_remove("ELECTRON_RUN_AS_NODE")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        command.process_group(0);
    }
    let mut child = command
        .spawn()
        .context("cannot start built Electron application")?;
    thread::sleep(Duration::from_millis(200));
    if let Some(status) = child.try_wait()? {
        anyhow::ensure!(status.success(), "Electron exited during startup");
    }
    Ok(Desktop(Some(child)))
}
fn interactive(command: &mut Command, on_started: impl FnOnce()) -> Result<(i32, bool)> {
    let terminate = Arc::new(AtomicBool::new(false));
    let interrupt = Arc::new(AtomicBool::new(false));
    let term_handler =
        signal_hook::flag::register(signal_hook::consts::SIGTERM, terminate.clone())?;
    // Native Codex owns Ctrl+C behavior. Keep its waiting parent alive.
    let int_handler = signal_hook::flag::register(signal_hook::consts::SIGINT, interrupt)?;
    let result = (|| {
        let mut child = command
            .stdin(Stdio::inherit())
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit())
            .spawn()
            .context("cannot start native Codex")?;
        on_started();
        loop {
            if let Some(status) = child.try_wait()? {
                #[cfg(unix)]
                {
                    use std::os::unix::process::ExitStatusExt;
                    return Ok((
                        status.code().unwrap_or(128 + status.signal().unwrap_or(1)),
                        false,
                    ));
                }
                #[cfg(not(unix))]
                return Ok((status.code().unwrap_or(1), false));
            }
            if terminate.load(Ordering::Relaxed) {
                #[cfg(unix)]
                unsafe {
                    libc::kill(child.id() as i32, libc::SIGTERM);
                }
                let deadline = Instant::now() + Duration::from_secs(2);
                while Instant::now() < deadline {
                    if child.try_wait()?.is_some() {
                        return Ok((143, true));
                    }
                    thread::sleep(Duration::from_millis(20));
                }
                services::stop(&mut child);
                return Ok((143, true));
            }
            thread::sleep(Duration::from_millis(30));
        }
    })();
    signal_hook::low_level::unregister(term_handler);
    signal_hook::low_level::unregister(int_handler);
    result
}

/// Persist a new session, open Electron, then enter native Codex without a prompt.
pub fn run(model: String, cwd: Option<PathBuf>, check: bool) -> Result<i32> {
    anyhow::ensure!(
        !model.trim().is_empty() && model.len() <= 128,
        "model must contain 1..128 bytes"
    );
    let root = config::project_root()?;
    let cwd = cwd
        .unwrap_or(env::current_dir()?)
        .canonicalize()
        .context("working directory must exist")?;
    anyhow::ensure!(cwd.is_dir(), "working directory must be a directory");
    let home = config::codex_home()?;
    let binary = crate::installed_codex::resolve(&home)?;
    let mut services = services::ensure(&root)?;
    if check {
        println!(
            "{}",
            json!({"status":"ok","api":services.health,"model":model,"cwd":cwd,"codex_binary":binary})
        );
        services.owned_api.take();
        return Ok(0);
    }
    let client = Client::new()?;
    let session = client.post(
        "api/research/v1/sessions",
        &json!({"model":model,"cwd":cwd,"codex_home":home,"codex_binary":binary}),
    )?;
    let id = crate::client::segment(
        session["session_id"]
            .as_str()
            .context("session response missing ID")?,
    )?;
    let startup = (|| {
        let desktop = desktop(&root, id, &services.api)?;
        let mut command = Command::new(&binary);
        command.current_dir(&cwd);
        config::configure(&mut command, &model, &cwd, &home, &services.api, id)?;
        lifecycle(&client, id, "started")?;
        Ok::<_, anyhow::Error>((desktop, command))
    })();
    let (mut desktop, mut command) = match startup {
        Ok(value) => value,
        Err(_) => {
            close(
                &client,
                id,
                "FAILED",
                None,
                Some(
                    "Interactive session startup failed; check the local Codex and Electron build.",
                ),
            )?;
            anyhow::bail!("interactive session startup failed; session was retained as FAILED");
        }
    };
    let execution = interactive(&mut command, || {
        // Once Codex starts these services remain available for the retained UI.
        services.owned_api.take();
        desktop.0.take();
    });
    match execution {
        Ok((code, interrupted)) => {
            let status = if interrupted || code == 130 || code == 143 {
                "INTERRUPTED"
            } else if code == 0 {
                "CLOSED"
            } else {
                "FAILED"
            };
            lifecycle(&client, id, "exited")?;
            close(
                &client,
                id,
                status,
                Some(code),
                if status == "FAILED" {
                    Some("Native Codex exited unsuccessfully; inspect its terminal error.")
                } else {
                    None
                },
            )?;
            Ok(code)
        }
        Err(_) => {
            close(
                &client,
                id,
                "FAILED",
                None,
                Some("Native Codex could not start or be monitored."),
            )?;
            anyhow::bail!("native Codex could not start; session was retained as FAILED")
        }
    }
}
