package main

import (
	"context"
	"encoding/json"
	"github.com/jeisenman/q2_bench/workflows/formallineage/model"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestFormalLineageParseWritesUnknown(t *testing.T) {
	root := t.TempDir()
	git := func(args ...string) string {
		t.Helper()
		b, err := exec.Command("git", append([]string{"-C", root}, args...)...).CombinedOutput()
		if err != nil {
			t.Fatalf("git %v: %s", args, b)
		}
		return strings.TrimSpace(string(b))
	}
	git("init", "--quiet")
	git("config", "user.name", "Test")
	git("config", "user.email", "test@example.invalid")
	if err := os.WriteFile(filepath.Join(root, "notebook.py"), []byte("import pandas as pd\ndef f(df):\n    return df.query('x > 0')\n"), 0600); err != nil {
		t.Fatal(err)
	}
	git("add", "notebook.py")
	git("commit", "--quiet", "-m", "fixture")
	pin := git("rev-parse", "HEAD")
	output := filepath.Join(t.TempDir(), "catalog.json")
	err := run(context.Background(), []string{"formal-lineage", "parse", "--project", "radar", "--repository", "radar-notebooks", "--root", root, "--commit", pin, "--path", "notebook.py", "--output", output})
	if err == nil || !strings.Contains(err.Error(), "prediction_ready=false") {
		t.Fatalf("unresolved result passed: %v", err)
	}
	b, err := os.ReadFile(output)
	if err != nil {
		t.Fatal(err)
	}
	var catalog model.ParsedFile
	if err := json.Unmarshal(b, &catalog); err != nil {
		t.Fatal(err)
	}
	if catalog.Source.Commit != pin || catalog.PredictionReady || catalog.Declarations[0].Method.Status != "unknown" {
		t.Fatalf("catalog %+v", catalog)
	}
}

func TestFormalLineageRejectsInvalidCommands(t *testing.T) {
	for _, args := range [][]string{{"formal-lineage"}, {"formal-lineage", "unknown"}, {"formal-lineage", "projects", "extra"}, {"formal-lineage", "parse", "--project", "radar", "--repository", "pl-dataingress"}, {"formal-lineage", "dependencies", "--project", "radar"}} {
		if err := run(context.Background(), args); err == nil {
			t.Fatalf("accepted %v", args)
		}
	}
}
