package dipipelines

import (
	"context"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func boundaryModule(t *testing.T, source string) *parsedModule {
	t.Helper()
	tree, err := parse([]byte(source))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(tree.Close)
	return &parsedModule{source: Source{Commit: strings.Repeat("a", 40), Path: "job.py", SHA256: hash([]byte(source))}, content: []byte(source), tree: tree}
}

func TestBoundaryFiltersGenerateCompleteTruthTablesAndEmptySchema(t *testing.T) {
	m := boundaryModule(t, `from pyspark.sql import functions as F
def transform(data):
    return data.where((F.col('amount') > 0) & (F.col('status') == 'Open'))
`)
	clauses := extractBoundaryClauses(m)
	var cases []ComparisonCase
	for _, c := range clauses {
		if c.Kind == "filter" {
			generated, _ := clauseCases(context.Background(), m, c)
			cases = append(cases, generated...)
		}
	}
	if len(cases) != 2 || len(cases[0].Bindings.Tables["data"]) != 43 {
		t.Fatalf("expected 6 numeric x 7 string values plus duplicate, cases=%+v", cases)
	}
	seen := map[float64]bool{}
	for _, row := range cases[0].Bindings.Tables["data"] {
		if value, ok := row["amount"].(float64); ok {
			seen[value] = true
		}
	}
	if !seen[-1] || !seen[0] || !seen[1] {
		t.Fatal("missing user's -1/0/1 boundary values")
	}
	result, err := EvaluateOutputs(context.Background(), cases[1].Method, cases[1].Bindings)
	if err != nil || len(result.Tables["output_1"]) != 0 || len(result.Schemas["output_1"]) != 2 {
		t.Fatalf("empty case lost schema: %+v %v", result, err)
	}
}

func TestBoundaryJoinCasesIncludeCompositeNullsFanoutAndEachEmptySide(t *testing.T) {
	m := boundaryModule(t, "def transform(left, right):\n    return left.join(right, on=['id', 'type'], how='left')\n")
	clauses := extractBoundaryClauses(m)
	cases, reason := clauseCases(context.Background(), m, clauses[0])
	if len(cases) != 4 {
		t.Fatalf("cases=%d reason=%s", len(cases), reason)
	}
	rows, err := Evaluate(context.Background(), cases[0].Method, cases[0].Bindings)
	if err != nil || len(rows) != 8 {
		t.Fatalf("fanout/null-key prediction=%v %v", rows, err)
	}
	for i := 1; i < len(cases); i++ {
		if _, err := EvaluateOutputs(context.Background(), cases[i].Method, cases[i].Bindings); err != nil {
			t.Fatal(err)
		}
	}
}

func TestBoundaryUnknownAndOversizedTruthTablesRemainBlocked(t *testing.T) {
	for _, predicate := range []string{"F.col('x') > cutoff", "custom(F.col('x'))", " & " + strings.Repeat("x", 2)} {
		source := "from pyspark.sql import functions as F\ndef transform(data):\n    return data.filter(" + predicate + ")\n"
		if strings.HasPrefix(predicate, " & ") {
			terms := []string{}
			for _, name := range []string{"a", "b", "c", "d", "e", "f", "g", "h"} {
				terms = append(terms, "(F.col('"+name+"') > 0)")
			}
			source = "from pyspark.sql import functions as F\ndef transform(data):\n    return data.filter(" + strings.Join(terms, " & ") + ")\n"
		}
		m := boundaryModule(t, source)
		for _, c := range extractBoundaryClauses(m) {
			if c.Kind == "filter" {
				cases, reason := clauseCases(context.Background(), m, c)
				if len(cases) != 0 || reason == "" {
					t.Fatalf("unsupported predicate became executed coverage: %s", predicate)
				}
			}
		}
	}
}

func TestDropNamesPreserveRowsNullsAndIgnoreAbsentColumn(t *testing.T) {
	m := compiled(t, "def transform(data):\n    return data.drop('gone', 'absent')\n", "transform", "data")
	result, err := EvaluateOutputs(context.Background(), m, Bindings{Tables: map[string][]Row{"data": {{"gone": "v", "keep": nil}, {"gone": "v", "keep": nil}}}})
	if err != nil || len(result.Tables["output_1"]) != 2 || len(result.Schemas["output_1"]) != 1 || result.Schemas["output_1"][0] != "keep" {
		t.Fatalf("drop semantics=%+v %v", result, err)
	}
	if _, err := Evaluate(context.Background(), m, Bindings{Tables: map[string][]Row{"data": {}}, Schemas: map[string][]string{"data": {"gone", "keep"}}}); err != nil {
		t.Fatal(err)
	}
}

func TestMembershipNullnessAndBetweenRespectSQLNulls(t *testing.T) {
	m := compiled(t, `from pyspark.sql import functions as F
def transform(data):
    return data.withColumn('member', F.col('x').isin([1, None])).withColumn('missing', F.col('x').isNull()).withColumn('present', F.col('x').isNotNull()).withColumn('bounded', F.col('x').between(-1, 1))
`, "transform", "data")
	rows, err := Evaluate(context.Background(), m, Bindings{Tables: map[string][]Row{"data": {{"x": float64(-1)}, {"x": float64(1)}, {"x": float64(2)}, {"x": nil}}}})
	if err != nil || rows[0]["bounded"] != true || rows[1]["member"] != true || rows[2]["member"] != nil || rows[3]["missing"] != true || rows[3]["present"] != false || rows[3]["bounded"] != nil {
		t.Fatalf("predicate null semantics: %v %v", rows, err)
	}
	source := boundaryModule(t, "from pyspark.sql import functions as F\ndef transform(data):\n    return data.filter(F.col('x').isNull() | F.col('x').between(-1, 1))\n")
	for _, c := range extractBoundaryClauses(source) {
		if c.Kind == "filter" && strings.HasPrefix(c.Expression, "data.filter") {
			cases, reason := clauseCases(context.Background(), source, c)
			if len(cases) != 2 {
				t.Fatalf("null and numeric types should refine: %s", reason)
			}
		}
	}
}

func TestNestedSparkColumnPathsCannotBecomeFlatColumnPredictions(t *testing.T) {
	for _, expression := range []string{"F.col('categories.isDeleted')", "data['categories.isDeleted']", "F.col('`categories.isDeleted`')"} {
		source := []byte("from pyspark.sql import functions as F\ndef transform(data):\n    return data.filter(~" + expression + ")\n")
		m, err := Compile(source, Source{Commit: strings.Repeat("a", 40), Path: "job.py", SHA256: hash(source)}, "transform", []string{"data"})
		if err != nil || m.Status != "unknown" || len(m.Steps) != 0 {
			t.Fatalf("nested-column regression: %+v %v", m, err)
		}
	}
	m := compiled(t, "def transform(data):\n    return data.select('missing')\n", "transform", "data")
	if _, err := Evaluate(context.Background(), m, Bindings{Tables: map[string][]Row{"data": {}}, Schemas: map[string][]string{"data": {"present"}}}); err == nil {
		t.Fatal("empty input hid a missing projected column")
	}
}

func TestClauseExtractionRetainsUTF8BytesAndRejectsLocalSparkShadowing(t *testing.T) {
	for _, prefix := range []string{"# naïve 🧪\n", ""} {
		m := boundaryModule(t, prefix+"from pyspark.sql import functions as F\ndef transform(data, F):\n    return data.filter(F.col('x') > 0)\n")
		for _, c := range extractBoundaryClauses(m) {
			if string(m.content[c.StartByte:c.EndByte]) != c.Expression {
				t.Fatal("UTF8 source span changed")
			}
			if c.Kind == "filter" {
				cases, reason := clauseCases(context.Background(), m, c)
				if len(cases) > 0 || !strings.Contains(reason, "shadows") {
					t.Fatalf("local F shadow accepted: %s", reason)
				}
			}
		}
	}
}

func TestBoundarySuitePinsGraphKeepsAllJobsAndLimitsScenarios(t *testing.T) {
	root := t.TempDir()
	path := "ds-jobs/src/datascience_jobs/jobs/example.py"
	if err := os.MkdirAll(filepath.Dir(filepath.Join(root, path)), 0700); err != nil {
		t.Fatal(err)
	}
	source := "from pyspark.sql import functions as F\nLIMIT=0\nclass Example:\n    def run(self, data):\n        return data.filter(F.col('amount') > LIMIT)\n"
	if err := os.WriteFile(filepath.Join(root, path), []byte(source), 0600); err != nil {
		t.Fatal(err)
	}
	git := func(args ...string) string {
		t.Helper()
		b, err := exec.Command("git", append([]string{"-C", root}, args...)...).CombinedOutput()
		if err != nil {
			t.Fatalf("git %v: %s %v", args, b, err)
		}
		return strings.TrimSpace(string(b))
	}
	git("init", "-q")
	git("config", "user.name", "Fixture")
	git("config", "user.email", "fixture@example.invalid")
	git("add", path)
	git("commit", "-qm", "fixture")
	commit := git("rev-parse", "HEAD")
	inventory, err := InventoryGit(context.Background(), root, commit)
	if err != nil {
		t.Fatal(err)
	}
	graph := func(pin string) []byte {
		b, err := json.Marshal(map[string]any{"manifest": map[string]any{"sourceRepositories": []any{map[string]string{"repository": "di-pipelines", "commitSha": pin}}}, "nodes": []any{map[string]any{"id": "job:example", "kind": "job", "transformations": []any{map[string]string{"implementation": "datascience_jobs.jobs.example.Example"}, map[string]string{"implementation": "external.Unknown"}}}}, "edges": []any{}})
		if err != nil {
			t.Fatal(err)
		}
		return b
	}
	if _, err := PlanBoundariesGit(context.Background(), root, inventory, graph(strings.Repeat("f", 40))); err == nil {
		t.Fatal("mixed graph and source pins accepted")
	}
	suite, err := PlanBoundariesGit(context.Background(), root, inventory, graph(commit))
	if err != nil || len(suite.Jobs) != 2 || len(suite.LogicalJobs) != 1 || len(suite.Cases) != 2 || suite.Status != "blocked" {
		t.Fatalf("suite=%+v %v", suite, err)
	}
	for _, job := range suite.Jobs {
		if len(job.Scenarios) < 2 || len(job.Scenarios) > 10 || job.Status != "blocked" {
			t.Fatalf("scenario limit or unknown coverage violated: %+v", job)
		}
	}
	caseCopy := suite.Cases[0]
	clauseCopy := *caseCopy.Clause
	caseCopy.Clause = &clauseCopy
	if _, err := PrepareComparison(context.Background(), root, []ComparisonCase{caseCopy}); err != nil {
		t.Fatal(err)
	}
	caseCopy.Clause.Adapter += "# tamper\n"
	if _, err := PrepareComparison(context.Background(), root, []ComparisonCase{caseCopy}); err == nil {
		t.Fatal("tampered clause adapter accepted")
	}
	if err := WriteBoundarySuite(filepath.Join(root, "artifacts"), suite); err != nil {
		t.Fatal(err)
	}
	loaded, err := LoadBoundarySuite(filepath.Join(root, "artifacts"))
	if err != nil || len(loaded.Cases) != len(suite.Cases) {
		t.Fatalf("batch receipt round trip: %v", err)
	}
	batch := filepath.Join(root, "artifacts", loaded.CaseBatches[0].Path)
	if err := os.WriteFile(batch, []byte("[]\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadBoundarySuite(filepath.Join(root, "artifacts")); err == nil {
		t.Fatal("changed case batch accepted")
	}
}
