package oms

import (
	"encoding/base64"
	"strings"
	"testing"

	agent "github.com/jeisenman/q2_bench/agents/oms"
)

func TestSignatureRejectsInvalidKey(t *testing.T) {
	t.Parallel()
	if _, err := Signature("workspace", "not base64", "date", []byte("{}")); err == nil {
		t.Fatal("expected invalid shared key to fail")
	}
	key := base64.StdEncoding.EncodeToString([]byte("secret"))
	signature, err := Signature("workspace", key, "date", []byte("{}"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(signature, "SharedKey workspace:") {
		t.Fatalf("signature = %q", signature)
	}
}

func TestRenderRows(t *testing.T) {
	t.Parallel()
	rendered, err := RenderRows(agent.QueryResult{
		Columns: []string{"message", "level"},
		Rows:    [][]any{{"ready", "info"}},
	})
	if err != nil {
		t.Fatal(err)
	}
	if rendered != `{"level":"info","message":"ready"}` {
		t.Fatalf("rendered = %q", rendered)
	}
}
