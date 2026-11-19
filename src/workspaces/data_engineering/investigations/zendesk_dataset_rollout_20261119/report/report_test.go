package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func encode(t *testing.T, value any) []byte {
	t.Helper()
	b, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	return append(b, '\n')
}
func save(t *testing.T, path string, b []byte) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, b, 0600); err != nil {
		t.Fatal(err)
	}
}

type fixture struct {
	root       string
	target     target
	effective  []byte
	before     definition
	prepared   definition
	edited     definition
	payload    input
	inputBytes []byte
	result     result
}

func synthetic(t *testing.T) fixture {
	t.Helper()
	root := t.TempDir()
	id := "dataset:test/a"
	artifactID := digest([]byte(id))
	record := target{NodeID: id, ArtifactID: artifactID, Directory: "nodes/" + artifactID, Files: map[string]pin{}}
	before := definition{NodeID: id, Description: "Technical window is 30 days.", BusinessContext: "Current business context."}
	edited := before
	edited.BusinessContext += " See [article](https://support.precisionlender.com/hc/en-us/articles/1-Article)."
	payload := input{}
	payload.Target.NodeID = id
	payload.Target.Generation = generation
	payload.Definition = before
	payload.Zendesk.Snapshot = snapshot
	if err := decode([]byte(`[{"chunkId":"chunk-1","articleId":1,"url":"https://support.precisionlender.com/hc/en-us/articles/1-Article"}]`), &payload.Zendesk.Chunks); err != nil {
		t.Fatal(err)
	}
	inputBytes := encode(t, payload)
	objects := map[string]any{"before": before, "prepared": before, "input": payload, "target": map[string]any{"node_id": id, "generation_id": generation}, "retrieval": map[string]any{}, "preparation": map[string]any{"status": "unchanged"}}
	for name, value := range objects {
		b := encode(t, value)
		rel := record.Directory + "/" + name + ".json"
		save(t, filepath.Join(root, rel), b)
		record.Files[name] = pin{Path: rel, SHA256: digest(b)}
	}
	effective := []byte("trusted synthetic effective prompt")
	r := result{NodeID: id, Model: "gpt-6-luna", PromptVersion: "2.0.0", PromptSHA: promptSHA, CallerPolicySHA: policySHA, EffectivePromptSHA: digest(effective), Passes: 1, Status: "changed", Started: "2026-11-19T21:00:00Z", Completed: "2026-11-19T21:00:01Z", InputSHA: record.Files["input"].SHA256, BeforeSHA: record.Files["before"].SHA256, PreparedSHA: record.Files["prepared"].SHA256, ModelChanged: true, NewArticleURLs: []string{"https://support.precisionlender.com/hc/en-us/articles/1-Article"}, Cited: []citation{{ArticleID: "1", ChunkID: "chunk-1", URL: "https://support.precisionlender.com/hc/en-us/articles/1-Article"}}, Usage: map[string]int64{"input_tokens": 10, "output_tokens": 5}}
	r.RequestSHA = digest(append(append(append([]byte{}, effective...), []byte("\n\n## Supplied inputs\n\n")...), inputBytes...))
	return fixture{root, record, effective, before, before, edited, payload, inputBytes, r}
}

func (f *fixture) emit(t *testing.T, status string) {
	t.Helper()
	r := f.result
	attempt := r
	attempt.Status = "failed"
	attempt.Completed = ""
	attempt.RequestSHA = ""
	attempt.RawSHA = ""
	attempt.DraftSHA = ""
	save(t, filepath.Join(f.root, f.target.Directory, "attempt.json"), encode(t, attempt))
	if status == "unresolved" {
		return
	}
	raw := encode(t, f.edited)
	if status == "failed" {
		raw = []byte("not JSON; deliberately held without parsing")
		r.Error = "initial validator held output"
		r.ModelChanged = false
		r.Cited = nil
		r.NewArticleURLs = nil
	}
	r.Status = status
	r.RawSHA = digest(raw)
	save(t, filepath.Join(f.root, f.target.Directory, "model-output.txt"), raw)
	if status != "failed" {
		r.DraftSHA = digest(raw)
		save(t, filepath.Join(f.root, f.target.Directory, "draft.json"), raw)
	}
	f.result = r
	save(t, filepath.Join(f.root, f.target.Directory, "result.json"), encode(t, r))
}

func TestPendingUnresolvedAndSuccess(t *testing.T) {
	f := synthetic(t)
	row, _, err := reconcileTarget(f.root, f.target, f.effective)
	if err != nil || row.Status != "pending" || !row.Held {
		t.Fatalf("pending: %+v %v", row, err)
	}
	f.emit(t, "unresolved")
	row, _, err = reconcileTarget(f.root, f.target, f.effective)
	if err != nil || row.Status != "unresolved_attempt" || !row.Held {
		t.Fatalf("unresolved: %+v %v", row, err)
	}
	f.emit(t, "changed")
	row, usage, err := reconcileTarget(f.root, f.target, f.effective)
	if err != nil || row.Status != "changed" || row.Held || !row.ModelChanged || len(row.Cited) != 1 || usage["input_tokens"] != 10 {
		t.Fatalf("success: %+v %v", row, err)
	}
}

func TestFailedOutputIsNotAcceptedOrParsed(t *testing.T) {
	f := synthetic(t)
	f.emit(t, "failed")
	row, _, err := reconcileTarget(f.root, f.target, f.effective)
	if err != nil || row.Status != "failed" || !row.Held || row.Files["draft"] != "" || !row.RawHashVerified {
		t.Fatalf("failed output reconsidered: %+v %v", row, err)
	}
}

func TestOutputHashIdentityPassAndChangeFailures(t *testing.T) {
	for _, name := range []string{"input hash", "raw hash", "draft hash", "identity", "passes", "status", "citation"} {
		t.Run(name, func(t *testing.T) {
			f := synthetic(t)
			f.emit(t, "changed")
			switch name {
			case "input hash":
				save(t, filepath.Join(f.root, f.target.Files["input"].Path), []byte("changed"))
			case "raw hash":
				save(t, filepath.Join(f.root, f.target.Directory, "model-output.txt"), []byte("changed"))
			case "draft hash":
				save(t, filepath.Join(f.root, f.target.Directory, "draft.json"), []byte("changed"))
			case "identity":
				f.result.NodeID = "dataset:test/other"
			case "passes":
				f.result.Passes = 2
			case "status":
				f.result.Status = "unchanged"
			case "citation":
				f.result.Cited[0].ChunkID = "invented"
			}
			if name != "input hash" && name != "raw hash" && name != "draft hash" {
				save(t, filepath.Join(f.root, f.target.Directory, "result.json"), encode(t, f.result))
			}
			if _, _, err := reconcileTarget(f.root, f.target, f.effective); err == nil {
				t.Fatal("artifact inconsistency accepted")
			}
		})
	}
}

func TestThreeStringKeysAndPreservedCitations(t *testing.T) {
	for _, raw := range []string{`{"description":"a","business_context":"b","node_id":"dataset:test/a","extra":"c"}`, `{"description":null,"business_context":"b","node_id":"dataset:test/a"}`, `{"description":"a","business_context":1,"node_id":"dataset:test/a"}`} {
		if _, err := parseDefinition([]byte(raw), "dataset:test/a"); err == nil {
			t.Fatal("invalid definition contract accepted")
		}
	}
	f := synthetic(t)
	original := f.prepared
	original.Description += " [source](https://example.com/source)"
	if err := verifyCitations(f.payload, original, f.edited, f.result); err == nil {
		t.Fatal("lost original citation accepted")
	}
}

func TestMarkdownIndexesBoundedAndExclusive(t *testing.T) {
	root := t.TempDir()
	out := filepath.Join(root, "review")
	s := summary{Selected: 161, Counts: map[string]int{}, Nodes: []nodeRow{}}
	for i := 0; i < 161; i++ {
		s.Nodes = append(s.Nodes, nodeRow{NodeID: fmt.Sprintf("dataset:test/%03d", i), Status: "pending", Held: true, Files: map[string]string{}})
	}
	if err := writeReport(root, out, s); err != nil {
		t.Fatal(err)
	}
	total := 0
	for i := 1; i <= 3; i++ {
		b, err := os.ReadFile(filepath.Join(out, fmt.Sprintf("datasets-%02d.md", i)))
		if err != nil {
			t.Fatal(err)
		}
		rows := strings.Count(string(b), "| dataset:test/")
		if rows > 80 || strings.Count(string(b), "\n") >= 400 {
			t.Fatal("index page exceeds bounds")
		}
		total += rows
	}
	if total != 161 {
		t.Fatal("some identities missing")
	}
	if err := writeReport(root, out, s); err == nil {
		t.Fatal("existing report overwritten")
	}
}
