package main

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/jeisenman/q2_bench/workflows/formallineage/projects"
)

func TestEnvironmentCommandRejectsSharedCompute(t *testing.T) {
	bindings := []projects.EnvironmentBinding{
		{ProfileID: "data-ingress-dotnet10", Platform: "native-dotnet", IsolationID: "process:shared", Root: "/validation/ingress", Versions: map[string]string{"dotnet_sdk": "10.0.103"}},
		{ProfileID: "calculation-engine-dotnet10", Platform: "native-dotnet", IsolationID: "process:shared", Root: "/validation/engine", Versions: map[string]string{"dotnet_sdk": "10.0.103"}},
	}
	root := t.TempDir()
	file := filepath.Join(root, "bindings.json")
	output := filepath.Join(root, "report.json")
	write := func() {
		t.Helper()
		b, err := json.Marshal(bindings)
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(file, b, 0600); err != nil {
			t.Fatal(err)
		}
	}
	write()
	args := []string{"formal-lineage", "check-environments", "--bindings", file, "--output", output}
	if err := run(context.Background(), args); err == nil || !strings.Contains(err.Error(), "reuse compute") {
		t.Fatalf("shared execution accepted: %v", err)
	}
	if _, err := os.Stat(output); !os.IsNotExist(err) {
		t.Fatal("failure wrote success report")
	}
	bindings[1].IsolationID = "process:engine"
	write()
	if err := run(context.Background(), args); err != nil {
		t.Fatal(err)
	}
	b, err := os.ReadFile(output)
	if err != nil {
		t.Fatal(err)
	}
	var report struct {
		Compatible bool `json:"bindings_compatible"`
		Validated  bool `json:"runtime_validated"`
	}
	if err := json.Unmarshal(b, &report); err != nil || !report.Compatible || report.Validated {
		t.Fatal("compatibility became execution proof")
	}
	if err := os.WriteFile(file, append(b, []byte(` {}`)...), 0600); err != nil {
		t.Fatal(err)
	}
	if err := run(context.Background(), args); err == nil {
		t.Fatal("accepted trailing or unknown JSON")
	}
}
