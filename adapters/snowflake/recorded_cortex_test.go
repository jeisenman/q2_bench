package snowflake

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/jeisenman/q2_bench/ports"
)

func writeTestRecording(t *testing.T, root string) {
	t.Helper()
	content := `{
  "model": "model",
  "prompt": "prompt",
  "temperature": 0,
  "text": "recorded answer",
  "token_count": 4
}`
	if err := os.WriteFile(
		filepath.Join(root, "recording.json"),
		[]byte(content),
		0o600,
	); err != nil {
		t.Fatal(err)
	}
}

func TestRecordedCortexReplaysDeterministically(t *testing.T) {
	root := t.TempDir()
	writeTestRecording(t, root)
	cortex, err := LoadRecordedCortex(root)
	if err != nil {
		t.Fatal(err)
	}
	response, err := cortex.Complete(
		context.Background(),
		ports.CortexRequest{Model: "model", Prompt: "prompt"},
	)
	if err != nil {
		t.Fatal(err)
	}
	if response.Text != "recorded answer" || !response.Recorded {
		t.Fatalf("response = %#v", response)
	}
	count, err := cortex.CountTokens(context.Background(), "model", "prompt")
	if err != nil || count != 4 {
		t.Fatalf("count = %d, err = %v", count, err)
	}
}

func TestRecordedCortexRejectsUnknownRequest(t *testing.T) {
	root := t.TempDir()
	writeTestRecording(t, root)
	cortex, err := LoadRecordedCortex(root)
	if err != nil {
		t.Fatal(err)
	}
	_, err = cortex.Complete(
		context.Background(),
		ports.CortexRequest{Model: "model", Prompt: "unseen"},
	)
	if err == nil || !strings.Contains(err.Error(), "no recorded Cortex response") {
		t.Fatalf("err = %v", err)
	}
}

func TestRecordedCortexRejectsMalformedRecording(t *testing.T) {
	root := t.TempDir()
	if err := os.WriteFile(
		filepath.Join(root, "broken.json"),
		[]byte("{broken"),
		0o600,
	); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadRecordedCortex(root); err == nil {
		t.Fatal("expected malformed recording to fail")
	}
}
