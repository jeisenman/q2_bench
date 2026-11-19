use serde_json::{Value, json};
use std::{
    fs,
    io::{BufRead, BufReader, Read, Write},
    net::TcpListener,
    process::{Command, Stdio},
    thread,
    time::Duration,
};

fn proposal() -> Value {
    json!({"title":"Draft","question":"Question","hypothesis":"Hypothesis","plan":"Plan","idempotency_key":"proposal key"})
}
fn record() -> Value {
    json!({"proposal_id":"draft-1","title":"Draft","question":"Question","hypothesis":"Hypothesis","plan":"Plan","status":"DRAFT","created_at":"2026-11-18T00:00:00Z","updated_at":"2026-11-18T00:00:00Z"})
}
fn binary() -> &'static str {
    env!("CARGO_BIN_EXE_researcher-codex")
}
fn server(replies: Vec<(u16, Value)>) -> (String, thread::JoinHandle<Vec<(String, Value)>>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = format!("http://{}", listener.local_addr().unwrap());
    let task = thread::spawn(move || {
        let mut requests = vec![];
        for (status, body) in replies {
            let (mut stream, _) = listener.accept().unwrap();
            stream
                .set_read_timeout(Some(Duration::from_secs(5)))
                .unwrap();
            let mut reader = BufReader::new(stream.try_clone().unwrap());
            let mut request = String::new();
            reader.read_line(&mut request).unwrap();
            let mut length = 0;
            loop {
                let mut header = String::new();
                reader.read_line(&mut header).unwrap();
                if header == "\r\n" {
                    break;
                }
                if let Some(value) = header.to_ascii_lowercase().strip_prefix("content-length: ") {
                    length = value.trim().parse::<usize>().unwrap();
                }
            }
            let mut bytes = vec![0; length];
            reader.read_exact(&mut bytes).unwrap();
            requests.push((
                request.trim().to_string(),
                if length == 0 {
                    Value::Null
                } else {
                    serde_json::from_slice(&bytes).unwrap()
                },
            ));
            let encoded = body.to_string();
            write!(stream, "HTTP/1.1 {status} OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{encoded}", encoded.len()).unwrap();
        }
        requests
    });
    (address, task)
}

#[test]
fn proposal_cli_saves_replays_reads_and_reports_conflicts_without_runtime() {
    let expected = record();
    let (address, task) = server(vec![
        (201, expected.clone()),
        (200, expected.clone()),
        (200, json!({"proposals":[expected.clone()]})),
        (200, expected),
        (
            409,
            json!({"error":{"code":"idempotency_conflict","message":"Conflict"}}),
        ),
    ]);
    let dir = tempfile::tempdir().unwrap();
    let file = dir.path().join("proposal.json");
    fs::write(&file, proposal().to_string()).unwrap();
    for args in [
        vec!["proposal", "save", file.to_str().unwrap()],
        vec!["proposal", "save", file.to_str().unwrap()],
        vec!["proposals", "--order", "oldest"],
        vec!["proposal", "get", "draft-1"],
    ] {
        let output = Command::new(binary())
            .args(args)
            .env("SEMANTIC_API_URL", &address)
            .env("SEMANTIC_RUNTIME", "/absent-runtime")
            .env("CODEX_BINARY", "/absent-model")
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stdout)
        );
        let value: Value = serde_json::from_slice(&output.stdout).unwrap();
        assert!(value["status"] == "DRAFT" || value["proposals"][0]["status"] == "DRAFT");
    }
    let output = Command::new(binary())
        .args(["proposal", "save"])
        .arg(file)
        .env("SEMANTIC_API_URL", &address)
        .output()
        .unwrap();
    assert!(!output.status.success());
    assert!(String::from_utf8_lossy(&output.stdout).contains("idempotency_conflict"));
    let requests = task.join().unwrap();
    assert_eq!(
        requests[0],
        (
            "POST /api/research/v1/proposals HTTP/1.1".into(),
            proposal()
        )
    );
    assert_eq!(requests[1], requests[0]);
    assert_eq!(
        requests[2].0,
        "GET /api/research/v1/proposals?order=oldest HTTP/1.1"
    );
    assert_eq!(
        requests[3].0,
        "GET /api/research/v1/proposals/draft-1 HTTP/1.1"
    );
}

#[test]
fn proposal_cli_rejects_invalid_shapes_and_limits_before_http() {
    let dir = tempfile::tempdir().unwrap();
    let file = dir.path().join("proposal.json");
    for (field, invalid) in [
        ("accepted", json!(true)),
        ("title", json!("a".repeat(1001))),
        ("question", json!(" ")),
        ("hypothesis", json!("h".repeat(16001))),
        ("plan", json!("p".repeat(16001))),
        ("idempotency_key", json!("k".repeat(129))),
    ] {
        let mut value = proposal();
        value[field] = invalid;
        fs::write(&file, value.to_string()).unwrap();
        let output = Command::new(binary())
            .args(["proposal", "save"])
            .arg(&file)
            .env("SEMANTIC_API_URL", "http://127.0.0.1:1")
            .output()
            .unwrap();
        assert!(!output.status.success());
        assert!(!String::from_utf8_lossy(&output.stdout).contains("API unavailable"));
    }
}

#[test]
fn proposal_mcp_uses_the_same_save_prepare_list_and_get_routes() {
    let expected = record();
    let (address, task) = server(vec![
        (201, expected.clone()),
        (201, expected.clone()),
        (200, json!({"proposals":[expected.clone()]})),
        (200, expected.clone()),
    ]);
    let mut child = Command::new(binary())
        .arg("mcp")
        .env("SEMANTIC_API_URL", address)
        .env("Q2_MCP_DEBUG", "1")
        .env("SEMANTIC_RUNTIME", "/absent-runtime")
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
    exchange(
        &mut stdin,
        &mut stdout,
        json!({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"proposal-fixture","version":"1"}}}),
    );
    writeln!(
        stdin,
        "{}",
        json!({"jsonrpc":"2.0","method":"notifications/initialized"})
    )
    .unwrap();
    for (index, name, arguments) in [
        (2, "proposal_save", proposal()),
        (3, "proposal_prepare", proposal()),
        (4, "proposal_list", json!({"order":"oldest"})),
        (5, "proposal_get", json!({"proposal_id":"draft-1"})),
    ] {
        let response = exchange(
            &mut stdin,
            &mut stdout,
            json!({"jsonrpc":"2.0","id":index,"method":"tools/call","params":{"name":name,"arguments":arguments}}),
        );
        assert_ne!(response["result"]["isError"], true);
        let value: Value =
            serde_json::from_str(response["result"]["content"][0]["text"].as_str().unwrap())
                .unwrap();
        assert!(value == expected || value["proposals"][0] == expected);
    }
    drop(stdin);
    let _ = child.kill();
    child.wait().unwrap();
    let requests = task.join().unwrap();
    assert_eq!(requests[0].1, proposal());
    assert_eq!(
        requests[1].0,
        "POST /api/research/v1/proposals/prepare HTTP/1.1"
    );
    assert_eq!(requests[1].1, proposal());
    assert_eq!(
        requests[2].0,
        "GET /api/research/v1/proposals?order=oldest HTTP/1.1"
    );
    assert_eq!(
        requests[3].0,
        "GET /api/research/v1/proposals/draft-1 HTTP/1.1"
    );
}
