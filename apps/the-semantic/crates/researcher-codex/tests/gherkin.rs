use serde_json::{Value, json};
use std::{
    io::{BufRead, BufReader, Write},
    net::TcpListener,
    process::{Command, Stdio},
    thread,
    time::Duration,
};

fn exchange(input: &mut impl Write, output: &mut impl BufRead, value: Value) -> Value {
    writeln!(input, "{value}").unwrap();
    input.flush().unwrap();
    let mut line = String::new();
    output.read_line(&mut line).unwrap();
    serde_json::from_str(&line).unwrap()
}
#[test]
fn gherkin_mcp_uses_shared_reads_and_rejects_vector_before_http() {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = format!("http://{}", listener.local_addr().unwrap());
    let commit = "a".repeat(40);
    let caps = json!({"keyword":{"enabled":true},"vector":{"enabled":false,"reason":"Vector search is disabled."}});
    let list = json!({"repository":"fixture","commit":commit,"count":1,"offset":25,"has_more":false,"features":[{"path":"a & b.feature","title":"a & b"}]});
    let feature = json!({"repository":"fixture","commit":commit,"path":"a & b.feature","title":"a & b","text":"Feature: Capital"});
    let replies = vec![caps.clone(), list.clone(), feature.clone()];
    let server = thread::spawn(move || {
        let mut requests = vec![];
        for body in replies {
            let (mut stream, _) = listener.accept().unwrap();
            stream
                .set_read_timeout(Some(Duration::from_secs(5)))
                .unwrap();
            let mut reader = BufReader::new(stream.try_clone().unwrap());
            let mut request = String::new();
            reader.read_line(&mut request).unwrap();
            requests.push(request);
            loop {
                let mut line = String::new();
                reader.read_line(&mut line).unwrap();
                if line == "\r\n" {
                    break;
                }
            }
            let encoded = body.to_string();
            write!(stream,"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{encoded}",encoded.len()).unwrap();
        }
        requests
    });
    let mut child = Command::new(env!("CARGO_BIN_EXE_researcher-codex"))
        .arg("mcp")
        .env("SEMANTIC_API_URL", address)
        .env("Q2_MCP_DEBUG", "1")
        .env("SEMANTIC_RUNTIME", "/absent-runtime")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    let mut input = child.stdin.take().unwrap();
    let mut output = BufReader::new(child.stdout.take().unwrap());
    exchange(
        &mut input,
        &mut output,
        json!({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"gherkin-fixture","version":"1"}}}),
    );
    writeln!(
        input,
        "{}",
        json!({"jsonrpc":"2.0","method":"notifications/initialized"})
    )
    .unwrap();
    for (id, name, arguments, expected) in [
        (2, "gherkin_capabilities", json!({}), caps),
        (
            3,
            "gherkin_search",
            json!({"query":"capital & cost","offset":25,"commit":commit,"mode":"keyword"}),
            list,
        ),
        (
            4,
            "gherkin_feature",
            json!({"path":"a & b.feature","commit":commit}),
            feature,
        ),
    ] {
        let response = exchange(
            &mut input,
            &mut output,
            json!({"jsonrpc":"2.0","id":id,"method":"tools/call","params":{"name":name,"arguments":arguments}}),
        );
        assert_ne!(response["result"]["isError"], true);
        let actual: Value =
            serde_json::from_str(response["result"]["content"][0]["text"].as_str().unwrap())
                .unwrap();
        assert_eq!(actual, expected);
    }
    // The listener is closed. Disabled vector must not try HTTP.
    let requests = server.join().unwrap();
    let response = exchange(
        &mut input,
        &mut output,
        json!({"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"gherkin_search","arguments":{"query":"capital","mode":"vector"}}}),
    );
    assert_eq!(response["result"]["isError"], true);
    assert!(
        response["result"]["content"][0]["text"]
            .as_str()
            .unwrap()
            .contains("gherkin_vector_disabled")
    );
    drop(input);
    let _ = child.kill();
    child.wait().unwrap();
    assert!(requests[0].contains("GET /api/research/v1/gherkin/capabilities "));
    assert!(requests[1].contains("query=capital+%26+cost&mode=keyword&offset=25&commit="));
    assert!(requests[2].contains("path=a+%26+b.feature&commit="));
}
