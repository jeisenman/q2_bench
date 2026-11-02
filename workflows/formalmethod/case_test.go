package formalmethod

import (
	"context"
	"testing"
)

func TestCaseNullBranchDoesNotBecomeOtherwiseAndFirstMatchWins(t *testing.T) {
	m := compiled(t, `from pyspark.sql import functions as F
def transform(data):
    rule=F.when(F.col('x') >= 0,F.lit(None))
    rule=rule.when(F.col('x') >= -1,F.lit(10))
    return data.withColumn('value',rule.otherwise(20)).withColumn('fallback',F.coalesce('a','b',F.lit(30)))
`, "transform", "data")
	rows, err := Evaluate(context.Background(), m, Bindings{Tables: map[string][]Row{"data": {{"x": float64(0), "a": nil, "b": float64(1)}, {"x": float64(-1), "a": float64(2), "b": float64(1)}, {"x": nil, "a": nil, "b": nil}}}})
	if err != nil || len(rows) != 3 || rows[0]["value"] != nil || rows[1]["value"] != float64(10) || rows[2]["value"] != float64(20) || rows[0]["fallback"] != float64(1) || rows[1]["fallback"] != float64(2) || rows[2]["fallback"] != float64(30) {
		t.Fatalf("CASE semantics: %v %v", rows, err)
	}
}

func TestCaseRejectsImplicitCoercionAndEagerPythonErrorsOnEmptyInput(t *testing.T) {
	for _, expr := range []string{"F.when(F.col('x')>0,'text').otherwise(2)", "F.when(F.col('x')>0,F.lit(1/0)).otherwise(2)"} {
		m := compiled(t, "from pyspark.sql import functions as F\ndef transform(data):\n    return data.withColumn('value',"+expr+")\n", "transform", "data")
		if _, err := Evaluate(context.Background(), m, Bindings{Tables: map[string][]Row{"data": {}}, Schemas: map[string][]string{"data": {"x"}}}); err == nil {
			t.Fatalf("unmodeled coercion/Python construction error became empty success: %s", expr)
		}
	}
	m := compiled(t, `from pyspark.sql import functions as F
def transform(data):
    value='text'
    rule=F.when(F.col('x')>0,F.lit(value))
    value=2
    return data.withColumn('value',rule.otherwise(value))
`, "transform", "data")
	if _, err := Evaluate(context.Background(), m, Bindings{Tables: map[string][]Row{"data": {{"x": float64(1)}}}}); err == nil {
		t.Fatal("later scalar assignment hid captured CASE coercion")
	}
}
