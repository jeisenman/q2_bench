package lineagecheck

import (
	"context"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func gitTest(t *testing.T, root string, args ...string) string {
	t.Helper()
	args = append([]string{"-C", root, "-c", "user.name=Lineage Test", "-c", "user.email=lineage@example.invalid"}, args...)
	b, err := exec.Command("git", args...).CombinedOutput()
	if err != nil {
		t.Fatalf("git fixture: %v: %s", err, b)
	}
	return strings.TrimSpace(string(b))
}

func fixture(t *testing.T) (Manifest, map[string]string) {
	t.Helper()
	root := t.TempDir()
	gitTest(t, root, "init", "--quiet")
	source := []byte("# reviewed job and schema fixture\n")
	if err := os.WriteFile(filepath.Join(root, "job.py"), source, 0o600); err != nil {
		t.Fatal(err)
	}
	gitTest(t, root, "add", "job.py")
	gitTest(t, root, "commit", "--quiet", "-m", "fixture")
	e := Evidence{Repository: "di-pipelines", Path: "job.py", SHA256: digest(source)}
	fields := []Field{{"CoreAccountId", "StringType", true}, {"DatePartition", "IntegerType", true}, {"IndustryCode", "StringType", true}}
	replay := Replay{Mode: "partition", HourUTC: 5, WriteMode: "replace", Force: true, ClientScope: "single_client"}
	m := Manifest{Format: Format, Scope: "reviewed deposit projection", Profile: "all_clients", Repositories: []Repository{{"di-pipelines", gitTest(t, root, "rev-parse", "HEAD")}}, Datasets: []Dataset{
		{ID: "primary/supplemental", Major: 1, Minor: 1, Fields: fields, Keys: []string{"CoreAccountId", "DatePartition"}, Partition: "DatePartition", Evidence: []Evidence{e}},
		{ID: "derived/deposits", Major: 3, Minor: 6, Fields: []Field{{"CoreAccountId", "StringType", true}, {"DatePartition", "IntegerType", true}, {"NaicsCode", "StringType", true}}, Keys: []string{"CoreAccountId", "DatePartition"}, Partition: "DatePartition", Evidence: []Evidence{e}},
	}, Jobs: []Job{{ID: "derive", DAG: "l3_main_graph", Inputs: []Input{{Dataset: "primary/supplemental", Major: 1, Fields: []string{"CoreAccountId", "DatePartition", "IndustryCode"}, Keys: []string{"CoreAccountId", "DatePartition"}}}, Outputs: []string{"derived/deposits"}, Dependencies: []Dependency{
		{FieldRef{"derived/deposits", "CoreAccountId"}, []FieldRef{{"primary/supplemental", "CoreAccountId"}}},
		{FieldRef{"derived/deposits", "DatePartition"}, []FieldRef{{"primary/supplemental", "DatePartition"}}},
		{FieldRef{"derived/deposits", "NaicsCode"}, []FieldRef{{"primary/supplemental", "IndustryCode"}}},
	}, ColumnsComplete: true, Replay: replay, Evidence: []Evidence{e}}}, Unresolved: []string{}}
	return m, map[string]string{"di-pipelines": root}
}

func built(t *testing.T, m Manifest, roots map[string]string) Snapshot {
	t.Helper()
	s, err := Build(context.Background(), m, roots)
	if err != nil {
		t.Fatal(err)
	}
	return s
}

func cloneSnapshot(t *testing.T, s Snapshot, mutate func(*Manifest)) Snapshot {
	t.Helper()
	b, _ := json.Marshal(s)
	var out Snapshot
	if err := Decode(b, &out); err != nil {
		t.Fatal(err)
	}
	mutate(&out.Manifest)
	canonicalize(&out.Manifest)
	out.ID = snapshotID(out)
	if err := ValidateSnapshot(out); err != nil {
		t.Fatal(err)
	}
	return out
}

func hasFinding(r Report, code string) bool {
	for _, f := range r.Findings {
		if f.Code == code {
			return true
		}
	}
	return false
}

func plan(s Snapshot) BackfillPlan {
	j := s.Manifest.Jobs[0]
	return BackfillPlan{ClientID: "us-bank-fixture", SnapshotID: s.ID, Dataset: "primary/supplemental", Columns: []string{"IndustryCode"}, From: "2026-01-15", Until: "2026-02-10", Runs: []ReplayRun{{ClientID: "us-bank-fixture", Job: j.ID, Enabled: true, From: "2026-01-15", Until: "2026-02-10", Replay: j.Replay, Evidence: j.Evidence}}}
}
