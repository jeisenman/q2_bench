package lineage

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestJSONSourceLoadsAndValidatesArtifact(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "graph.json")
	content := `{
		"manifest": {"commit": "abc123"},
		"nodes": [
			{"id": "dataset:one", "kind": "dataset", "name": "one"},
			{"id": "job:one", "kind": "job", "name": "one"}
		],
		"edges": [
			{"id": "edge:one", "source": "dataset:one", "target": "job:one", "kind": "input"}
		]
	}`
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
	source, err := NewJSONSource(path)
	if err != nil {
		t.Fatal(err)
	}
	graph, err := source.Latest(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(graph.Nodes) != 2 || len(graph.Edges) != 1 {
		t.Fatalf("graph = %#v", graph)
	}
	history, err := source.History(context.Background(), 1)
	if err != nil {
		t.Fatal(err)
	}
	if len(history) != 1 || history[0].Manifest["commit"] != "abc123" {
		t.Fatalf("history = %#v", history)
	}
}

func TestParseGraphRejectsInvalidReferencesAndShapes(t *testing.T) {
	tests := []struct {
		name string
		body string
		want string
	}{
		{
			name: "missing manifest",
			body: `{"nodes":[],"edges":[]}`,
			want: "manifest must be an object",
		},
		{
			name: "missing edge target",
			body: `{
				"manifest": {},
				"nodes": [{"id":"dataset:one","kind":"dataset"}],
				"edges": [{"id":"edge:one","source":"dataset:one","target":"missing","kind":"input"}]
			}`,
			want: "references missing target",
		},
		{
			name: "unsupported node kind",
			body: `{
				"manifest": {},
				"nodes": [{"id":"other:one","kind":"other"}],
				"edges": []
			}`,
			want: "kind must be dataset or job",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			_, err := ParseGraph([]byte(test.body))
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("error = %v, want %q", err, test.want)
			}
		})
	}
}

func TestJSONSourceRejectsInvalidHistoryLimitAndMissingFile(t *testing.T) {
	source, err := NewJSONSource(filepath.Join(t.TempDir(), "missing.json"))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := source.History(context.Background(), 0); err == nil {
		t.Fatal("expected history limit error")
	}
	if _, err := source.Latest(context.Background()); err == nil ||
		!strings.Contains(err.Error(), "artifact") {
		t.Fatalf("missing file error = %v", err)
	}
}
