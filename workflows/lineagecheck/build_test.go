package lineagecheck

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestBuildRejectsStaleEvidenceAndIgnoresUncommittedSource(t *testing.T) {
	m, roots := fixture(t)
	a := built(t, m, roots)
	if err := os.WriteFile(filepath.Join(roots["di-pipelines"], "job.py"), []byte("uncommitted changes"), 0o600); err != nil {
		t.Fatal(err)
	}
	b := built(t, m, roots)
	if a.ID != b.ID {
		t.Fatal("working tree affected pinned build")
	}
	m.Datasets[0].Evidence[0].SHA256 = digest([]byte("incorrect"))
	if _, err := Build(context.Background(), m, roots); err == nil {
		t.Fatal("stale evidence accepted")
	}
	if _, err := Build(context.Background(), a.Manifest, map[string]string{}); err == nil {
		t.Fatal("missing checkout accepted")
	}
}

func TestLiteralSchemaExtractionRejectsComputedAndCommentedFields(t *testing.T) {
	source := []byte(`class Metadata(DatasetMetaData):
    @property
    def _schema_v1(self):
        _schema = StructType([
            # StructField('NotAField', StringType(), True),
            StructField('CoreAccountId', StringType(), True),
            StructField('Value', DoubleType(), False),
        ])
        return _schema
`)
	fields, err := ExtractSchema(source, "Metadata", 1)
	if err != nil || len(fields) != 2 || fields[1].Nullable {
		t.Fatalf("schema = %+v, %v", fields, err)
	}
	if _, err := ExtractSchema(source, "Metadata", 2); err == nil {
		t.Fatal("missing schema accepted")
	}
	if _, err := ExtractSchema([]byte("class Metadata:\n    def _schema_v1(self):\n        return make_schema()\n"), "Metadata", 1); err == nil {
		t.Fatal("computed schema accepted")
	}
	if _, err := ExtractSchema([]byte("class Metadata:\n    def _schema_v1(self):\n        _schema = StructType([StructField('X', StringType(), True)])\n        _schema.add('Extra')\n        return _schema\n"), "Metadata", 1); err == nil {
		t.Fatal("mutated schema accepted")
	}
}

func TestStoreChecksDigestsLocksAndHistory(t *testing.T) {
	m, roots := fixture(t)
	a := built(t, m, roots)
	store := Store{Root: t.TempDir()}
	ctx := context.Background()
	if err := store.Save(ctx, a); err != nil {
		t.Fatal(err)
	}
	if err := store.Save(ctx, a); err != nil {
		t.Fatal(err)
	}
	b := cloneSnapshot(t, a, func(m *Manifest) { m.Datasets[0].Minor++ })
	if err := store.Save(ctx, b); err != nil {
		t.Fatal(err)
	}
	got, err := store.Load(ctx, "")
	if err != nil || got.ID != b.ID {
		t.Fatalf("latest = %+v, %v", got, err)
	}
	history, err := store.History(ctx, 10)
	if err != nil || len(history) != 2 {
		t.Fatalf("history = %+v, %v", history, err)
	}
	if _, err := store.Load(ctx, "../../anything"); err == nil {
		t.Fatal("invalid ID accepted")
	}
	if err := os.Mkdir(filepath.Join(store.Root, ".writer-lock"), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := store.Save(ctx, a); err == nil {
		t.Fatal("concurrent writer lock ignored")
	}
	a.Manifest.Scope = "tampered"
	content, _ := json.Marshal(a)
	if err := os.WriteFile(filepath.Join(store.Root, "snapshots", a.ID+".json"), content, 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := store.Load(ctx, a.ID); err == nil {
		t.Fatal("corrupt snapshot accepted")
	}
}

func TestPRCheckRejectsStalePinsAndUncoveredFiles(t *testing.T) {
	m, roots := fixture(t)
	base := built(t, m, roots)
	root := roots["di-pipelines"]
	if err := os.WriteFile(filepath.Join(root, "unreviewed.py"), []byte("# changed source\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	gitTest(t, root, "add", "unreviewed.py")
	gitTest(t, root, "commit", "--quiet", "-m", "new source")
	m.Repositories[0].Commit = gitTest(t, root, "rev-parse", "HEAD")
	head := built(t, m, roots)
	scope := PRScope{Repository: "di-pipelines", Root: root, BaseRef: base.Manifest.Repositories[0].Commit, HeadRef: head.Manifest.Repositories[0].Commit}
	r, err := CheckPR(context.Background(), base, head, Policy{Mode: "additive"}, scope)
	if err != nil || r.Status != "unknown" || !hasFinding(r, "uncovered_pr_file") {
		t.Fatalf("uncovered = %+v, %v", r, err)
	}
	if _, err := CheckPR(context.Background(), base, base, Policy{Mode: "additive"}, scope); err == nil {
		t.Fatal("stale head accepted")
	}
}
