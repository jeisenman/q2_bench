use serde_json::{Value, json};
use std::os::unix::fs::PermissionsExt;
use std::{
    fs,
    io::{Read, Write},
    net::TcpListener,
    path::{Path, PathBuf},
    process::Command,
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
    },
    thread,
    time::Duration,
};
struct Server {
    url: String,
    requests: Arc<Mutex<Vec<(String, Value)>>>,
    stop: Arc<AtomicBool>,
    thread: Option<thread::JoinHandle<()>>,
}
impl Server {
    fn new(route: impl Fn(&str, &Value) -> Value + Send + 'static) -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let url = format!("http://{}", listener.local_addr().unwrap());
        let requests = Arc::new(Mutex::new(vec![]));
        let captured = requests.clone();
        let stop = Arc::new(AtomicBool::new(false));
        let halted = stop.clone();
        let thread = thread::spawn(move || {
            while !halted.load(Ordering::Relaxed) {
                let Ok((mut stream, _)) = listener.accept() else {
                    thread::sleep(Duration::from_millis(5));
                    continue;
                };
                stream.set_nonblocking(false).unwrap();
                stream
                    .set_read_timeout(Some(Duration::from_secs(2)))
                    .unwrap();
                let mut bytes = vec![];
                let mut buffer = [0; 1024];
                while let Ok(count) = stream.read(&mut buffer) {
                    if count == 0 {
                        break;
                    }
                    bytes.extend_from_slice(&buffer[..count]);
                    if let Some(end) = bytes.windows(4).position(|v| v == b"\r\n\r\n") {
                        let header = String::from_utf8_lossy(&bytes[..end]);
                        let length = header
                            .lines()
                            .find_map(|line| {
                                line.to_ascii_lowercase()
                                    .strip_prefix("content-length: ")
                                    .map(str::to_string)
                            })
                            .map(|v| v.parse::<usize>().unwrap())
                            .unwrap_or(0);
                        if bytes.len() < end + 4 + length {
                            continue;
                        }
                        let path = header
                            .lines()
                            .next()
                            .unwrap()
                            .split_whitespace()
                            .nth(1)
                            .unwrap()
                            .to_string();
                        let value = if length == 0 {
                            Value::Null
                        } else {
                            serde_json::from_slice(&bytes[end + 4..end + 4 + length]).unwrap()
                        };
                        captured.lock().unwrap().push((path.clone(), value.clone()));
                        let body = route(&path, &value).to_string();
                        write!(stream,"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",body.len()).unwrap();
                        break;
                    }
                }
            }
        });
        Self {
            url,
            requests,
            stop,
            thread: Some(thread),
        }
    }
}
impl Drop for Server {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Relaxed);
        let _ = self.thread.take().unwrap().join();
    }
}
fn executable(path: &Path, text: &str) {
    fs::write(path, text).unwrap();
    fs::set_permissions(path, fs::Permissions::from_mode(0o700)).unwrap();
}
struct Fixture {
    root: tempfile::TempDir,
    home: PathBuf,
    binary: PathBuf,
    electron: PathBuf,
    tracking: Server,
    api: Server,
}
impl Fixture {
    fn new() -> Self {
        let root = tempfile::tempdir().unwrap();
        let home = root.path().join("home");
        fs::create_dir(&home).unwrap();
        fs::write(
            home.join("config.toml"),
            "[mcp_servers.private]\ncommand='sensitive-secret-config-value'\n",
        )
        .unwrap();
        for path in ["apps/desktop/dist-electron", "apps/desktop/dist"] {
            fs::create_dir_all(root.path().join(path)).unwrap();
        }
        fs::write(root.path().join("apps/desktop/dist-electron/main.cjs"), "").unwrap();
        fs::write(root.path().join("apps/desktop/dist/index.html"), "").unwrap();
        let binary = root.path().join("codex");
        executable(
            &binary,
            r#"#!/usr/bin/env node
const args=process.argv.slice(2);const assert=require('node:assert/strict');
assert.equal(args[0],'--model');assert.equal(args[1],process.env.EXPECT_MODEL || 'gpt-6.1-sol');
assert.equal(args[2],'--cd');assert.equal(args[3],process.cwd());
assert.equal(args.includes('exec'),false);assert.equal(args.includes('--ignore-user-config'),false);
const configs=args.filter((_,i)=>args[i-1]==='-c');
assert.ok(configs.some(v=>v.startsWith('mcp_servers=')&&v.includes('"private"={enabled=false}')));
assert.ok(configs.some(v=>v.startsWith('mcp_servers=')&&v.includes('semantic_research={')));
assert.ok(configs.includes('otel.log_user_prompt=true'));assert.ok(configs.includes('otel.log_agent_responses=true'));
assert.ok(configs.includes('otel.tool_result.max_bytes=0'));
const endpoint=configs.find(v=>v.startsWith('otel.exporter=')).match(/endpoint="([^"]+)"/)[1];
const attribute=(key,value)=>({key,value:{stringValue:value}});
const log=(name,key,text)=>({attributes:[attribute('event.name',name),attribute(key,text),attribute('agent.type','main'),attribute('event.timestamp','2026-11-18T12:00:00.000Z')]});
fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({resourceLogs:[{scopeLogs:[{logRecords:[log('codex.user_prompt','prompt','fixture question'),log('codex.agent_response','response','fixture answer')]}]}]})}).then(r=>{assert.ok(r.ok);console.log('NATIVE_FIXTURE');process.exit(Number(process.env.FIXTURE_EXIT||0));}).catch(()=>process.exit(9));
"#,
        );
        let electron = root.path().join("electron");
        executable(
            &electron,
            "#!/bin/sh\ncase \"$*\" in *--research-session*s1*) exit 0;; *) exit 2;; esac\n",
        );
        let tracking = Server::new(|_, _| json!({"experiments":[]}));
        let project = root.path().canonicalize().unwrap();
        let tracking_url = tracking.url.clone();
        let api = Server::new(move |path, _| {
            if path == "/health" {
                json!({"status":"ok","project_root":project,"capabilities":["research","sessions"],"experiment_id":"2","experiment_name":"fixture","tracking_uri":tracking_url})
            } else if path == "/api/research/v1/sessions" {
                json!({"session_id":"s1"})
            } else {
                json!({"status":"ok"})
            }
        });
        Self {
            root,
            home,
            binary,
            electron,
            tracking,
            api,
        }
    }
    fn command(&self) -> Command {
        let mut command = Command::new(env!("CARGO_BIN_EXE_researcher-codex"));
        command
            .arg("chat")
            .current_dir(self.root.path())
            .env("SEMANTIC_PROJECT_ROOT", self.root.path())
            .env("CODEX_HOME", &self.home)
            .env("CODEX_BINARY", &self.binary)
            .env("SEMANTIC_ELECTRON_BINARY", &self.electron)
            .env("SEMANTIC_API_URL", &self.api.url)
            .env("MLFLOW_TRACKING_URI", &self.tracking.url)
            .env_remove("MLFLOW_EXPERIMENT_NAME");
        command
    }
}
#[test]
fn native_chat_persists_session_then_messages_then_close_without_automatic_prompt() {
    let fixture = Fixture::new();
    let output = fixture.command().output().unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(String::from_utf8_lossy(&output.stdout).contains("NATIVE_FIXTURE"));
    assert!(!String::from_utf8_lossy(&output.stdout).contains("sensitive-secret"));
    let requests = fixture.api.requests.lock().unwrap();
    let paths: Vec<_> = requests.iter().map(|(path, _)| path.as_str()).collect();
    let create = paths
        .iter()
        .position(|p| *p == "/api/research/v1/sessions")
        .unwrap();
    let otel = paths.iter().position(|p| p.ends_with("/otel")).unwrap();
    let close = paths.iter().position(|p| p.ends_with("/close")).unwrap();
    assert!(create < otel && otel < close);
    assert_eq!(requests[create].1["model"], "gpt-6.1-sol");
    assert_eq!(requests[close].1["status"], "CLOSED");
    let records = &requests[otel].1["resourceLogs"][0]["scopeLogs"][0]["logRecords"];
    assert_eq!(records.as_array().unwrap().len(), 2);
}
#[test]
fn native_model_failure_is_visible_and_persisted_without_fallback() {
    let fixture = Fixture::new();
    let output = fixture
        .command()
        .args(["--model", "explicit-model"])
        .env("EXPECT_MODEL", "explicit-model")
        .env("FIXTURE_EXIT", "7")
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(7));
    let requests = fixture.api.requests.lock().unwrap();
    let close = requests
        .iter()
        .find(|(p, _)| p.ends_with("/close"))
        .unwrap();
    assert_eq!(close.1["status"], "FAILED");
    assert_eq!(close.1["exit_code"], 7);
    assert_eq!(
        requests
            .iter()
            .filter(|(p, _)| p.ends_with("/otel"))
            .count(),
        1
    );
}
#[test]
fn startup_failure_closes_persisted_session_and_leaves_reused_api() {
    let fixture = Fixture::new();
    let output = fixture
        .command()
        .env("SEMANTIC_ELECTRON_BINARY", "/nonexistent/electron")
        .output()
        .unwrap();
    assert!(!output.status.success());
    let requests = fixture.api.requests.lock().unwrap();
    let close = requests
        .iter()
        .find(|(p, _)| p.ends_with("/close"))
        .unwrap();
    assert_eq!(close.1["status"], "FAILED");
    assert!(!requests.iter().any(|(p, _)| p.ends_with("/otel")));
}
#[test]
fn wrong_api_listener_is_not_replaced_and_no_session_is_started() {
    let fixture = Fixture::new();
    let wrong = Server::new(|_, _| json!({"status":"ok","project_root":"/wrong"}));
    let output = fixture
        .command()
        .env("SEMANTIC_API_URL", &wrong.url)
        .output()
        .unwrap();
    assert!(!output.status.success());
    assert!(String::from_utf8_lossy(&output.stderr).contains("left unchanged"));
    assert_eq!(wrong.requests.lock().unwrap().len(), 1);
    assert!(fixture.api.requests.lock().unwrap().is_empty());
}

#[test]
fn wrong_tracking_listener_is_untouched_and_cannot_start_a_session() {
    let fixture = Fixture::new();
    let wrong = Server::new(|_, _| json!({"status":"unrelated"}));
    let output = fixture
        .command()
        .env("MLFLOW_TRACKING_URI", &wrong.url)
        .output()
        .unwrap();
    assert!(!output.status.success());
    assert!(String::from_utf8_lossy(&output.stderr).contains("left unchanged"));
    assert!(fixture.api.requests.lock().unwrap().is_empty());
}

#[test]
fn owned_api_startup_failure_cleans_its_child_group() {
    let fixture = Fixture::new();
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = format!("http://{}", listener.local_addr().unwrap());
    drop(listener);
    let bin = fixture.root.path().join("bin");
    fs::create_dir(&bin).unwrap();
    let server = fixture.root.path().join("wrong-api.cjs");
    let pidfile = fixture.root.path().join("api-child.pid");
    fs::write(&server,format!(r#"require('node:fs').writeFileSync({},String(process.pid));require('node:http').createServer((q,r)=>{{r.setHeader('Content-Type','application/json');r.end(JSON.stringify({{status:'ok',project_root:'/wrong'}}));}}).listen(Number(process.env.SEMANTIC_API_PORT),'127.0.0.1');"#,json!(pidfile))).unwrap();
    executable(
        &bin.join("uv"),
        &format!("#!/bin/sh\nnode '{}' &\nwait\n", server.display()),
    );
    let path = format!("{}:{}", bin.display(), std::env::var("PATH").unwrap());
    let output = fixture
        .command()
        .env("SEMANTIC_API_URL", &address)
        .env("PATH", path)
        .output()
        .unwrap();
    assert!(!output.status.success());
    assert!(String::from_utf8_lossy(&output.stderr).contains("left unchanged"));
    let pid: i32 = fs::read_to_string(pidfile).unwrap().parse().unwrap();
    let mut alive = true;
    for _ in 0..50 {
        alive = unsafe { libc::kill(pid, 0) } == 0;
        if !alive {
            break;
        }
        thread::sleep(Duration::from_millis(10));
    }
    assert!(!alive, "owned API descendant survived startup failure");
    assert!(fixture.api.requests.lock().unwrap().is_empty());
}

#[test]
fn termination_closes_session_as_interrupted_and_waits_for_native_child() {
    let fixture = Fixture::new();
    let pidfile = fixture.root.path().join("native.pid");
    executable(
        &fixture.binary,
        &format!(
            "#!/usr/bin/env node\nrequire('node:fs').writeFileSync({},String(process.pid));setInterval(()=>{{}},1000);",
            json!(pidfile)
        ),
    );
    let child = fixture
        .command()
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .unwrap();
    for _ in 0..200 {
        if pidfile.is_file() {
            break;
        }
        thread::sleep(Duration::from_millis(10));
    }
    assert!(pidfile.is_file());
    let native: i32 = fs::read_to_string(pidfile).unwrap().parse().unwrap();
    unsafe {
        libc::kill(child.id() as i32, libc::SIGTERM);
    }
    let output = child.wait_with_output().unwrap();
    assert_eq!(output.status.code(), Some(143));
    let requests = fixture.api.requests.lock().unwrap();
    let close = requests
        .iter()
        .find(|(p, _)| p.ends_with("/close"))
        .unwrap();
    assert_eq!(close.1["status"], "INTERRUPTED");
    assert_ne!(
        unsafe { libc::kill(native, 0) },
        0,
        "native child survived launcher interruption"
    );
}
