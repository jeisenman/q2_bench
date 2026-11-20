use serde_json::{Value, json};
#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;
use std::{
    fs,
    io::{Read, Write},
    net::TcpListener,
    process::{Command, Stdio},
    thread,
    time::Instant,
};

fn binary() -> &'static str {
    env!("CARGO_BIN_EXE_researcher-codex")
}
fn fixture(contents: &str) -> (tempfile::TempDir, std::path::PathBuf) {
    let dir = tempfile::tempdir().unwrap();
    let file = dir.path().join("codex");
    fs::write(&file, contents).unwrap();
    #[cfg(unix)]
    fs::set_permissions(&file, fs::Permissions::from_mode(0o700)).unwrap();
    (dir, file)
}
fn complete(script: &str, input: &str, seconds: &str) -> std::process::Output {
    let (dir, file) = fixture(script);
    fs::write(
        dir.path().join("config.toml"),
        "[mcp_servers.\"private-server\"]\ncommand=\"unused\"\n",
    )
    .unwrap();
    let mut child = Command::new(binary())
        .args([
            "complete",
            "--model",
            "gpt-5.6-sol",
            "--timeout-seconds",
            seconds,
        ])
        .env("CODEX_BINARY", file)
        .env("CODEX_HOME", dir.path())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    child
        .stdin
        .take()
        .unwrap()
        .write_all(input.as_bytes())
        .unwrap();
    child.wait_with_output().unwrap()
}
#[test]
fn bridge_passes_actual_prompt_and_ignores_user_configuration() {
    let script = r#"#!/bin/sh
args="$*"
case "$args" in *--ignore-user-config*) ;; *) exit 2;; esac
case "$args" in *features.code_mode=false*features.code_mode_only=false*features.code_mode_host=false*) ;; *) exit 4;; esac
prompt=$(cat)
case "$prompt" in *actual-instructions*actual-question*) ;; *) exit 3;; esac
printf '%s\n' '{"type":"item.completed","item":{"type":"agent_message","text":"actual-answer"}}' '{"type":"turn.completed","usage":{"input_tokens":7,"output_tokens":3}}'
"#;
    let output = complete(
        script,
        r#"{"instructions":"actual-instructions","input":"actual-question"}"#,
        "3",
    );
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    let value: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(value["output"], "actual-answer");
    assert_eq!(value["input_tokens"], 7);
}
#[test]
fn bridge_rejects_invalid_input_provider_failure_and_timeout() {
    let invalid = complete(
        "#!/bin/sh\nexit 99",
        r#"{"instructions":"x","input":"y","extra":1}"#,
        "1",
    );
    assert!(!invalid.status.success());
    let failed = complete(
        "#!/bin/sh\necho super-secret >&2\nexit 1",
        r#"{"instructions":"x","input":"y"}"#,
        "1",
    );
    assert!(!failed.status.success());
    assert!(!String::from_utf8_lossy(&failed.stdout).contains("super-secret"));
    let start = Instant::now();
    let timeout = complete(
        "#!/bin/sh\nsleep 30",
        r#"{"instructions":"x","input":"y"}"#,
        "1",
    );
    assert!(!timeout.status.success());
    assert!(start.elapsed().as_secs() < 4);
    assert!(String::from_utf8_lossy(&timeout.stdout).contains("timeout"));
}
#[test]
fn bridge_bounds_child_output() {
    let output = complete(
        "#!/bin/sh\nyes x",
        r#"{"instructions":"x","input":"y"}"#,
        "3",
    );
    assert!(!output.status.success());
    assert!(String::from_utf8_lossy(&output.stdout).contains("exceeds limit"));
}

fn http_fixture(responses: Vec<(u16, Value)>) -> (String, thread::JoinHandle<Vec<Value>>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = format!("http://{}", listener.local_addr().unwrap());
    let task = thread::spawn(move || {
        let mut bodies = vec![];
        for (status, value) in responses {
            let (mut stream, _) = listener.accept().unwrap();
            stream
                .set_read_timeout(Some(std::time::Duration::from_secs(5)))
                .unwrap();
            let mut bytes = Vec::new();
            let mut buffer = [0; 1024];
            loop {
                let count = stream.read(&mut buffer).unwrap();
                assert!(count > 0);
                bytes.extend_from_slice(&buffer[..count]);
                if let Some(end) = bytes.windows(4).position(|v| v == b"\r\n\r\n") {
                    let headers = String::from_utf8_lossy(&bytes[..end]);
                    let length = headers
                        .lines()
                        .find_map(|line| {
                            line.to_ascii_lowercase()
                                .strip_prefix("content-length: ")
                                .map(str::to_string)
                        })
                        .map(|v| v.parse::<usize>().unwrap())
                        .unwrap_or(0);
                    if bytes.len() >= end + 4 + length {
                        bodies.push(if length > 0 {
                            serde_json::from_slice(&bytes[end + 4..end + 4 + length]).unwrap()
                        } else {
                            Value::Null
                        });
                        break;
                    }
                }
            }
            let body = value.to_string();
            write!(stream, "HTTP/1.1 {status} OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", body.len()).unwrap();
        }
        bodies
    });
    (address, task)
}
fn spec() -> Value {
    json!({"title":"t","question":"q","hypothesis":"h","plan":"p","agent_id":"a","agent_version":"1","accepted":true,"max_runs":1,"max_seconds":3,"idempotency_key":"key"})
}
fn run_spec(address: &str, runtime: &std::path::Path) -> std::process::Output {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("spec.json");
    fs::write(&path, spec().to_string()).unwrap();
    Command::new(binary())
        .args(["run", "--spec"])
        .arg(path)
        .env("SEMANTIC_API_URL", address)
        .env("SEMANTIC_RUNTIME", runtime)
        .output()
        .unwrap()
}
#[test]
fn idempotent_running_record_never_replays_model() {
    let (address, task) = http_fixture(vec![(200, json!({"status":"RUNNING"}))]);
    let output = run_spec(&address, std::path::Path::new("/does/not/exist"));
    assert!(output.status.success());
    assert_eq!(task.join().unwrap().len(), 1);
}
#[test]
fn runtime_failure_is_persisted() {
    let record = json!({"research_id":"r", "attempt_id":"a1", "status":"RUNNING", "model":"gpt-5.6-sol", "agent_definition_digest":"digest"});
    let agent = json!({"id":"a","version":"1","name":"a","purpose":"p","instructions":"i","model":"gpt-5.6-sol","allowed_tools":[],"page_plugin":"run-summary","definition_digest":"digest","mlflow_run_id":"m"});
    let (address, task) = http_fixture(vec![
        (201, record),
        (200, agent),
        (200, json!({"status":"FAILED"})),
    ]);
    let (dir, _) = fixture("");
    let runtime = dir.path().join("runtime.js");
    fs::write(&runtime, "process.stderr.write('private'); process.exit(1)").unwrap();
    let output = run_spec(&address, &runtime);
    assert!(
        !output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    let bodies = task.join().unwrap();
    assert_eq!(bodies[2]["status"], "FAILED");
    assert!(!bodies[2].to_string().contains("private"));
}

#[test]
fn sdk_mcp_stdio_lists_tools_and_reads_same_api() {
    use std::io::{BufRead, BufReader};
    let expected = json!({"agents":[]});
    let (address, task) = http_fixture(vec![(200, expected.clone())]);
    let mut child = Command::new(binary())
        .arg("mcp")
        .env("SEMANTIC_API_URL", address)
        .env("Q2_MCP_DEBUG", "1")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    let mut stdin = child.stdin.take().unwrap();
    let mut stdout = BufReader::new(child.stdout.take().unwrap());
    fn exchange(input: &mut impl Write, output: &mut impl BufRead, value: Value) -> Value {
        writeln!(input, "{value}").unwrap();
        input.flush().unwrap();
        let mut line = String::new();
        output.read_line(&mut line).unwrap();
        serde_json::from_str(&line).unwrap()
    }
    let initialized = exchange(
        &mut stdin,
        &mut stdout,
        json!({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"fixture","version":"1"}}}),
    );
    assert!(initialized["result"]["capabilities"]["tools"].is_object());
    writeln!(
        stdin,
        "{}",
        json!({"jsonrpc":"2.0","method":"notifications/initialized"})
    )
    .unwrap();
    let listed = exchange(
        &mut stdin,
        &mut stdout,
        json!({"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}),
    );
    assert_eq!(listed["result"]["tools"].as_array().unwrap().len(), 12);
    let result = exchange(
        &mut stdin,
        &mut stdout,
        json!({"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"agent_list","arguments":{}}}),
    );
    let actual: Value =
        serde_json::from_str(result["result"]["content"][0]["text"].as_str().unwrap()).unwrap();
    assert_eq!(actual, expected);
    drop(stdin);
    let _ = child.kill();
    child.wait().unwrap();
    task.join().unwrap();
}

#[test]
fn runtime_timeout_is_killed_and_persisted_within_full_deadline() {
    let record = json!({"research_id":"r", "attempt_id":"a1", "status":"RUNNING", "model":"gpt-5.6-sol", "agent_definition_digest":"digest"});
    let agent = json!({"id":"a","version":"1","name":"a","purpose":"p","instructions":"i","model":"gpt-5.6-sol","allowed_tools":[],"page_plugin":"run-summary","definition_digest":"digest","mlflow_run_id":"m"});
    let (address, task) = http_fixture(vec![
        (201, record),
        (200, agent),
        (200, json!({"status":"KILLED"})),
    ]);
    let dir = tempfile::tempdir().unwrap();
    let runtime = dir.path().join("runtime.js");
    fs::write(&runtime, "setTimeout(() => {}, 30000)").unwrap();
    let start = Instant::now();
    let output = run_spec(&address, &runtime);
    assert!(!output.status.success());
    assert!(start.elapsed().as_millis() < 4000);
    let bodies = task.join().unwrap();
    assert_eq!(bodies[2]["status"], "KILLED");
}

#[test]
fn full_deadline_removes_nested_codex_process() {
    let record = json!({"research_id":"r", "attempt_id":"a1", "status":"RUNNING", "model":"gpt-5.6-sol", "agent_definition_digest":"digest"});
    let agent = json!({"id":"a","version":"1","name":"a","purpose":"p","instructions":"i","model":"gpt-5.6-sol","allowed_tools":[],"page_plugin":"run-summary","definition_digest":"digest","mlflow_run_id":"m"});
    let (address, task) = http_fixture(vec![
        (201, record),
        (200, agent),
        (200, json!({"status":"KILLED"})),
    ]);
    let directory = tempfile::tempdir().unwrap();
    let pidfile = directory.path().join("pid");
    let (codex_dir, codex) = fixture(&format!(
        "#!/bin/sh\necho $$ > '{}'\nsleep 30",
        pidfile.display()
    ));
    let runtime = directory.path().join("runtime.js");
    fs::write(&runtime, format!(r#"
const {{spawn}} = require('node:child_process');
const child = spawn(process.env.SEMANTIC_CLI, ['complete','--model','gpt-5.6-sol','--timeout-seconds','30'], {{env: {{...process.env, CODEX_BINARY:{}, CODEX_HOME:{}}}}});
child.stdin.end(JSON.stringify({{instructions:'fixture',input:'fixture'}}));
setTimeout(()=>{{}},30000);
"#, json!(codex), json!(codex_dir.path()))).unwrap();
    let output = run_spec(&address, &runtime);
    assert!(
        !output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert_eq!(task.join().unwrap()[2]["status"], "KILLED");
    let pid: i32 = fs::read_to_string(pidfile).unwrap().trim().parse().unwrap();
    // Process-group cleanup must remove the actual provider process, not only Node.
    let mut alive = true;
    for _ in 0..50 {
        alive = unsafe { libc::kill(pid, 0) } == 0;
        if !alive {
            break;
        }
        thread::sleep(std::time::Duration::from_millis(10));
    }
    assert!(!alive, "nested Codex process survived deadline");
}

#[test]
fn runtime_receives_absolute_future_deadline_and_persists_success() {
    let record = json!({"research_id":"r", "attempt_id":"a1", "status":"RUNNING", "model":"gpt-5.6-sol", "agent_definition_digest":"digest"});
    let agent = json!({"id":"a","version":"1","name":"a","purpose":"p","instructions":"i","model":"gpt-5.6-sol","allowed_tools":[],"page_plugin":"run-summary","definition_digest":"digest","mlflow_run_id":"m"});
    let (address, task) = http_fixture(vec![
        (201, record),
        (200, agent),
        (200, json!({"status":"FINISHED"})),
    ]);
    let dir = tempfile::tempdir().unwrap();
    let runtime = dir.path().join("runtime.js");
    fs::write(&runtime, r#"
const fs = require('node:fs');
const request = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const deadline = Number(process.env.SEMANTIC_DEADLINE_MS);
const remaining = deadline - Date.now();
if (!Number.isSafeInteger(deadline) || remaining <= 0 || remaining > request.spec.max_seconds * 1000) {
  process.stderr.write('Deadline must be a future Unix epoch millisecond timestamp');
  process.exit(2);
}
process.stdout.write(JSON.stringify({attempt_id:request.attempt_id,status:'FINISHED',output:'verified deadline',metrics:{remaining_ms:remaining},sdk_events:[],error:null}));
"#).unwrap();
    let output = run_spec(&address, &runtime);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    let bodies = task.join().unwrap();
    assert_eq!(bodies[2]["status"], "FINISHED");
    assert_eq!(bodies[2]["output"], "verified deadline");
    assert!(bodies[2]["metrics"]["remaining_ms"].as_f64().unwrap() > 0.0);
}
