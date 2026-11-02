package formalmethod

import (
	"context"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

func compiled(t *testing.T, source, name string, tables ...string) Method {
	t.Helper()
	b := []byte(source)
	m, err := Compile(b, Source{strings.Repeat("a", 40), "job.py", hash(b)}, name, tables)
	if err != nil || m.Status != "compiled" {
		t.Fatalf("compile: %+v, %v", m.Diagnostics, err)
	}
	return m
}

func TestCompiledFiltersUseSQLNullsAndBagMultiplicity(t *testing.T) {
	m := compiled(t, `from pyspark.sql import functions as F
def transform(data, cutoff):
    data = data.filter((F.col('amount') > cutoff) | (F.col('eligible') == True))
    data = data.dropna(how='all', subset=['id'])
    return data
`, "transform", "data")
	input := []Row{{"id": "a", "amount": nil, "eligible": true}, {"id": "b", "amount": nil, "eligible": false}, {"id": "c", "amount": float64(10), "eligible": nil}, {"id": "c", "amount": float64(10), "eligible": nil}, {"id": nil, "amount": float64(10), "eligible": true}}
	rows, err := Evaluate(context.Background(), m, Bindings{Tables: map[string][]Row{"data": input}, Scalars: map[string]any{"cutoff": float64(5)}})
	if err != nil || len(rows) != 3 || rows[0]["id"] != "a" || rows[1]["id"] != "c" || !reflect.DeepEqual(rows[1], rows[2]) {
		t.Fatalf("rows=%v err=%v", rows, err)
	}
	if !reflect.DeepEqual(input[0], Row{"id": "a", "amount": nil, "eligible": true}) {
		t.Fatal("input mutated")
	}
}

func TestCompiledAggregatesAndJoinsRetainNullGroupsAndMultiplicity(t *testing.T) {
	m := compiled(t, `from pyspark.sql import functions as F
def transform(data, base):
    groups = ['id']
    totals = data.groupBy(groups).agg((F.sum(data.balance * data.weight) / F.sum(data.weight)).alias('average'))
    out = base.join(totals, groups, how='left')
    return out
`, "transform", "data", "base")
	rows, err := Evaluate(context.Background(), m, Bindings{Tables: map[string][]Row{
		"data": {{"id": "a", "balance": float64(100), "weight": float64(1)}, {"id": "a", "balance": float64(200), "weight": float64(3)}, {"id": nil, "balance": float64(50), "weight": float64(1)}},
		"base": {{"id": "a"}, {"id": "a"}, {"id": "missing"}, {"id": nil}},
	}})
	if err != nil || len(rows) != 4 || rows[0]["average"] != float64(175) || rows[1]["average"] != float64(175) || rows[2]["average"] != nil || rows[3]["average"] != nil {
		t.Fatalf("rows=%v err=%v", rows, err)
	}
}

func TestEmptyGroupedRightRelationRetainsSchema(t *testing.T) {
	m := compiled(t, `from pyspark.sql import functions as F
def transform(data, base):
    result = data.groupBy('id').agg(F.sum(data.amount).alias('total'))
    result = base.join(result, on='id', how='left')
    return result
`, "transform", "data", "base")
	rows, err := Evaluate(context.Background(), m, Bindings{Tables: map[string][]Row{"data": {}, "base": {{"id": "a"}}}, Schemas: map[string][]string{"data": {"id", "amount"}}})
	if err != nil || len(rows) != 1 || len(rows[0]) != 2 || rows[0]["total"] != nil {
		t.Fatalf("rows=%v err=%v", rows, err)
	}
}

func TestUnsupportedAndTamperedMethodsCannotExecute(t *testing.T) {
	source := []byte("def transform(data):\n    data = data.filter(True)\n    data = custom(data)\n    return data\n")
	m, err := Compile(source, Source{strings.Repeat("a", 40), "job.py", hash(source)}, "transform", []string{"data"})
	if err != nil || m.Status != "unknown" || len(m.Steps) != 0 || len(m.Diagnostics) == 0 {
		t.Fatalf("%+v %v", m, err)
	}
	if _, err = Evaluate(context.Background(), m, Bindings{}); err == nil {
		t.Fatal("unknown executed")
	}
	m = compiled(t, "def transform(data):\n    return data\n", "transform", "data")
	m.Steps[0].Expression.Name = "missing"
	if _, err = Evaluate(context.Background(), m, Bindings{Tables: map[string][]Row{"data": {{"id": "a"}}}}); err == nil {
		t.Fatal("tampering accepted")
	}
}

func TestEvaluationBoundsMissingColumnsAndCancellation(t *testing.T) {
	m := compiled(t, "def transform(data):\n    data = data.filter(data.missing > 0)\n    return data\n", "transform", "data")
	b := Bindings{Tables: map[string][]Row{"data": {{"id": "a"}}}}
	if _, err := Evaluate(context.Background(), m, b); err == nil {
		t.Fatal("missing column accepted")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := Evaluate(ctx, m, b); err == nil {
		t.Fatal("cancellation ignored")
	}
	b.Tables["data"] = make([]Row, maxRows+1)
	if _, err := Evaluate(context.Background(), m, b); err == nil {
		t.Fatal("row limit ignored")
	}
	for _, expr := range []*Expression{nil, {Op: "filter", Kind: Table}, {Op: "div", Kind: Scalar}} {
		n := 0
		if validateTree(expr, 0, &n) == nil {
			t.Fatal("malformed operator accepted")
		}
	}
}

func TestStandardParserAcceptsModernSyntaxAndFailsInvalidSource(t *testing.T) {
	tree, err := parse([]byte("def transform(data):\n    match data:\n        case {'x': x}:\n            return f'{x}'\n"))
	if err != nil {
		t.Fatal(err)
	}
	tree.Close()
	if _, err := parse([]byte("def broken(:\n")); err == nil {
		t.Fatal("invalid Python accepted")
	}
	// Exercise repeated parser close to cover cancellation/lifetime safety.
	for range 200 {
		tree, err := parse([]byte("x = 1\n"))
		if err != nil {
			t.Fatal(err)
		}
		tree.Close()
	}
}

func TestPinnedGitCompilationIgnoresWorkingTree(t *testing.T) {
	root := t.TempDir()
	source := []byte("def transform(data):\n    return data\n")
	git := func(args ...string) string {
		t.Helper()
		b, err := exec.Command("git", append([]string{"-C", root}, args...)...).CombinedOutput()
		if err != nil {
			t.Fatalf("git: %s %v", b, err)
		}
		return strings.TrimSpace(string(b))
	}
	git("init", "-q")
	git("config", "user.name", "Fixture")
	git("config", "user.email", "fixture@example.invalid")
	if err := os.WriteFile(filepath.Join(root, "job.py"), source, 0600); err != nil {
		t.Fatal(err)
	}
	git("add", "job.py")
	git("commit", "-qm", "fixture")
	commit := git("rev-parse", "HEAD")
	a, err := CompileGit(context.Background(), root, commit, "job.py", "transform", []string{"data"})
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "job.py"), []byte("invalid working tree"), 0600); err != nil {
		t.Fatal(err)
	}
	b, err := CompileGit(context.Background(), root, commit, "job.py", "transform", []string{"data"})
	if err != nil || a.ID != b.ID {
		t.Fatal("working tree changed compilation")
	}
	encoded, _ := json.Marshal(a)
	var decoded Method
	if err := json.Unmarshal(encoded, &decoded); err != nil || decoded.ID != methodID(decoded) {
		t.Fatal("contract round trip changed digest")
	}
}

func TestCopiesAreGroupedWithTheirTransformation(t *testing.T) {
	source := []byte(`def group(dag):
    transform = OperatorFactory(job_name='derive', job_reference='jobs.Derive').operate(compute='spark')
    internal = OperatorFactory(job_name='internal', job_reference='datamart.core.standard_jobs.adls_to_adls.AdlsToAdlsCopyApi', override_activity_args={'dataset':'D2P', 'outputResource':'Internal'}).operate(compute='batch')
    client = OperatorFactory(job_name='client', job_reference='di_pyjobs.job.standard.batch.AdlsToAdlsCopy', override_activity_args={'dataset':'D2P', 'outputResource':'Client'}).operate(compute='batch')
    orphan = OperatorFactory(job_name='orphan', job_reference='di_pyjobs.job.standard.batch.AdlsToAdlsCopy').operate(compute='batch')
    [internal, client] << transform
    return transform
`)
	tree, err := parse(source)
	if err != nil {
		t.Fatal(err)
	}
	defer tree.Close()
	units := extractUnits(tree.RootNode(), source, Source{strings.Repeat("a", 40), "dag.py", hash(source)})
	if len(units) != 2 {
		t.Fatalf("units=%+v", units)
	}
	for _, u := range units {
		if u.PredictionReady || len(u.Unresolved) == 0 {
			t.Fatal("uncompiled units became ready")
		}
		if u.Task == "derive" {
			if len(u.Copies) != 2 || u.Copies[0].Arguments["outputResource"] != "Client" || u.Copies[1].Arguments["outputResource"] != "Internal" {
				t.Fatalf("copies=%+v", u.Copies)
			}
		}
	}
}

func TestSemanticBindingsAndQualifiedColumnsFailClosed(t *testing.T) {
	source := []byte("from other import functions as F\ndef transform(data):\n    return data.filter(F.col('x') > 0)\n")
	m, err := Compile(source, Source{strings.Repeat("a", 40), "job.py", hash(source)}, "transform", []string{"data"})
	if err != nil || m.Status != "unknown" {
		t.Fatalf("unknown semantic binding compiled: %+v %v", m, err)
	}
	m = compiled(t, "def transform(data, other):\n    return data.filter(other.amount > 0)\n", "transform", "data", "other")
	_, err = Evaluate(context.Background(), m, Bindings{Tables: map[string][]Row{"data": {{"amount": float64(5)}}, "other": {{"amount": float64(0)}}}})
	if err == nil {
		t.Fatal("cross-relation column silently rebound")
	}
}

func TestLocalHelpersCompileToContentAddressedMethods(t *testing.T) {
	m := compiled(t, `from pyspark.sql import functions as F
LIMIT = 2
def keep(data, cutoff):
    return data.filter(F.col('amount') > cutoff)
def transform(data):
    return keep(data, LIMIT)
`, "transform", "data")
	if len(m.Library) != 1 || len(m.Assumptions) != 1 {
		t.Fatalf("closure=%+v assumptions=%v", m.Library, m.Assumptions)
	}
	rows, err := Evaluate(context.Background(), m, Bindings{Tables: map[string][]Row{"data": {{"amount": float64(1)}, {"amount": float64(3)}}}})
	if err != nil || len(rows) != 1 || rows[0]["amount"] != float64(3) {
		t.Fatalf("rows=%v err=%v", rows, err)
	}
	rows, err = Evaluate(context.Background(), m, Bindings{Tables: map[string][]Row{"data": {}}, Schemas: map[string][]string{"data": {"amount"}}})
	if err != nil || len(rows) != 0 {
		t.Fatalf("empty linked schema lost: %v %v", rows, err)
	}
	for id, child := range m.Library {
		child.Source.Path = "changed.py"
		m.Library[id] = child
	}
	if _, err := Evaluate(context.Background(), m, Bindings{}); err == nil {
		t.Fatal("tampered helper accepted")
	}
}

func TestHelperRecursionAndUnsupportedClosuresRemainUnknown(t *testing.T) {
	source := []byte("def first(data):\n    return second(data)\ndef second(data):\n    return first(data)\n")
	m, err := Compile(source, Source{strings.Repeat("a", 40), "job.py", hash(source)}, "first", []string{"data"})
	if err != nil || m.Status != "unknown" || len(m.Steps) != 0 {
		t.Fatalf("recursive closure: %+v %v", m, err)
	}
}

func TestGroupKeyListCompositionAndMinimum(t *testing.T) {
	m := compiled(t, `from pyspark.sql import functions as F
def transform(data):
    keys = ['id']
    result = data.groupby(keys + ['type']).agg(F.min(data.amount).alias('minimum'))
    return result
`, "transform", "data")
	rows, err := Evaluate(context.Background(), m, Bindings{Tables: map[string][]Row{"data": {{"id": "a", "type": "x", "amount": float64(3)}, {"id": "a", "type": "x", "amount": float64(1)}}}})
	if err != nil || len(rows) != 1 || rows[0]["minimum"] != float64(1) {
		t.Fatalf("rows=%v err=%v", rows, err)
	}
}

func TestDeferredColumnBindingsCaptureTheirInputs(t *testing.T) {
	m := compiled(t, `from pyspark.sql import functions as F
def transform(data):
    threshold = 2
    predicate = F.col('amount') > threshold
    threshold = 5
    return data.filter(predicate)
`, "transform", "data")
	rows, err := Evaluate(context.Background(), m, Bindings{Tables: map[string][]Row{"data": {{"amount": float64(3)}}}})
	if err != nil || len(rows) != 1 {
		t.Fatalf("column binding changed after assignment: %v %v", rows, err)
	}
}

func TestMultipleRelationsAndHelperUnpackingRetainPorts(t *testing.T) {
	m := compiled(t, `from pyspark.sql import functions as F
def split(data):
    positive = data.filter(F.col('amount') > 0)
    other = data.filter(F.col('amount') <= 0)
    return positive, other
def transform(data):
    yes, no = split(data)
    return yes, no
`, "transform", "data")
	result, err := EvaluateOutputs(context.Background(), m, Bindings{Tables: map[string][]Row{"data": {{"amount": float64(3)}}}})
	if err != nil || len(result.Tables) != 2 || len(result.Tables["yes"]) != 1 || len(result.Tables["no"]) != 0 || len(result.Schemas["no"]) != 1 {
		t.Fatalf("ports=%+v err=%v", result, err)
	}
	if _, err := Evaluate(context.Background(), m, Bindings{Tables: map[string][]Row{"data": {{"amount": float64(3)}}}}); err == nil {
		t.Fatal("tuple implicitly collapsed")
	}
}

func TestScalarPythonErrorsDoNotBecomeSQLNullPredictions(t *testing.T) {
	for _, op := range []string{"+", "/"} {
		m := compiled(t, "from pyspark.sql import functions as F\ndef transform(data, value):\n    result = 1 "+op+" value\n    return data.withColumn('result', F.lit(result))\n", "transform", "data")
		value := any(nil)
		if op == "/" {
			value = float64(0)
		}
		if _, err := Evaluate(context.Background(), m, Bindings{Tables: map[string][]Row{"data": {{"id": "a"}}}, Scalars: map[string]any{"value": value}}); err == nil {
			t.Fatal("scalar Python error became a row value")
		}
	}
	m := compiled(t, "from pyspark.sql import functions as F\ndef transform(data, value):\n    result = value == None\n    return data.withColumn('result', F.lit(result))\n", "transform", "data")
	rows, err := Evaluate(context.Background(), m, Bindings{Tables: map[string][]Row{"data": {{"id": "a"}}}, Scalars: map[string]any{"value": nil}})
	if err != nil || rows[0]["result"] != true {
		t.Fatalf("Python None equality: %v %v", rows, err)
	}
}
