package snowflake

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/jeisenman/q2_bench/ports"
)

func writeTestAgentRecording(t *testing.T, root string) {
	t.Helper()
	content := `{
  "agent_name": "DB.SCHEMA.AGENT",
  "version": "VERSION$2",
  "request_body": "{\"messages\":[]}",
  "create_thread_if_not_present": false,
  "response": "{\"role\":\"assistant\"}"
}`
	if err := os.WriteFile(
		filepath.Join(root, "recording.json"),
		[]byte(content),
		0o600,
	); err != nil {
		t.Fatal(err)
	}
}

func TestRecordedAgentReplaysVersionedResponse(t *testing.T) {
	root := t.TempDir()
	writeTestAgentRecording(t, root)
	agent, err := LoadRecordedAgent(root)
	if err != nil {
		t.Fatal(err)
	}
	response, err := agent.Run(context.Background(), ports.CortexAgentRequest{
		AgentName: "DB.SCHEMA.AGENT", Version: "VERSION$2",
		RequestBody: `{"messages":[]}`,
	})
	if err != nil {
		t.Fatal(err)
	}
	if response.Response != `{"role":"assistant"}` || !response.Recorded {
		t.Fatalf("response = %#v", response)
	}
}

func TestRecordedAgentRejectsUnknownVersion(t *testing.T) {
	root := t.TempDir()
	writeTestAgentRecording(t, root)
	agent, err := LoadRecordedAgent(root)
	if err != nil {
		t.Fatal(err)
	}
	_, err = agent.Run(context.Background(), ports.CortexAgentRequest{
		AgentName: "DB.SCHEMA.AGENT", Version: "LIVE",
		RequestBody: `{"messages":[]}`,
	})
	if err == nil || !strings.Contains(err.Error(), "no recorded Cortex Agent response") {
		t.Fatalf("err = %v", err)
	}
}

func TestRecordedAgentRejectsMalformedRecording(t *testing.T) {
	root := t.TempDir()
	if err := os.WriteFile(
		filepath.Join(root, "broken.json"),
		[]byte(`{"response":"not-json"}`),
		0o600,
	); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadRecordedAgent(root); err == nil {
		t.Fatal("expected malformed recording to fail")
	}
}
