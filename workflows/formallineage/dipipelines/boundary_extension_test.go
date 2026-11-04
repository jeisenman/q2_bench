package dipipelines

import (
	"context"
	"strings"
	"testing"
)

func TestLiteralBindingsArePinnedAndRejectParameterOrConditionalReplacement(t *testing.T) {
	for _, test := range []struct {
		source string
		want   bool
	}{
		{"IDS={'A','B'}\ndef transform(data):\n    return data.filter(F.col('kind').isin(IDS))\n", true},
		{"def transform(left,right):\n    keys=['id']\n    return left.join(right,on=keys,how='left')\n", true},
		{"LIMIT=2\ndef transform(data,LIMIT):\n    return data.filter(F.col('x') > LIMIT)\n", false},
		{"LIMIT=2\ndef transform(data):\n    if flag:\n        LIMIT=3\n    return data.filter(F.col('x') > LIMIT)\n", false},
		{"IDS=['A']\ndef transform(data):\n    IDS.append('B')\n    return data.filter(F.col('kind').isin(IDS))\n", false},
	} {
		m := boundaryModule(t, "from pyspark.sql import functions as F\n"+test.source)
		for _, c := range extractBoundaryClauses(m) {
			if !strings.HasPrefix(c.Expression, "data.filter") && !strings.HasPrefix(c.Expression, "left.join") {
				continue
			}
			cases, reason := clauseCases(context.Background(), m, c)
			if (len(cases) > 0) != test.want {
				t.Fatalf("literal capture want=%v: %s\n%s", test.want, reason, test.source)
			}
			if test.want && len(cases[0].Clause.Literals) == 0 {
				t.Fatal("literal source receipt missing")
			}
		}
	}
}

func TestFieldBoundariesPropagateThroughEarlierThresholdGuards(t *testing.T) {
	m := boundaryModule(t, `from pyspark.sql import functions as F
def transform(data):
    return data.filter((F.col('amount') > 500) & (F.col('balance') < F.col('amount')))
`)
	for _, c := range extractBoundaryClauses(m) {
		if c.Kind != "filter" {
			continue
		}
		cases, reason := clauseCases(context.Background(), m, c)
		if len(cases) != 2 {
			t.Fatal(reason)
		}
		mutations := fixtureMutations(context.Background(), cases)
		for _, mutation := range mutations {
			if mutation.Status != "killed" {
				t.Fatalf("guarded equality remained untested: %+v", mutation)
			}
		}
	}
}

func TestSparkStringOperationsAndLiteralArgumentCollections(t *testing.T) {
	m := compiled(t, `from pyspark.sql import functions as F
EXCLUDED={'bad','other'}
DROP=('gone','absent')
def transform(data):
    data=data.filter(~F.lower('name').contains('ppp'))
    data=data.filter(F.col('code').isin(('keep','ok')))
    data=data.filter(~F.col('code').isin(EXCLUDED))
    return data.drop(*DROP)
`, "transform", "data")
	rows, err := Evaluate(context.Background(), m, Bindings{Tables: map[string][]Row{"data": {{"name": "ordinary", "code": "keep", "gone": "x"}, {"name": "PPP facility", "code": "keep", "gone": "x"}, {"name": nil, "code": "keep", "gone": "x"}}}})
	if err != nil || len(rows) != 1 || len(rows[0]) != 2 {
		t.Fatalf("string/set/expansion: %v %v", rows, err)
	}
	for _, test := range []struct {
		op   string
		args []any
		want any
	}{{"like", []any{"a\nb", "a%b"}, true}, {"like", []any{"a%b", `a\%b`}, true}, {"trim", []any{" \t x \n "}, "\t x \n"}, {"length", []any{"🧪a"}, float64(2)}} {
		got, err := stringScalar(test.op, test.args)
		if err != nil || got != test.want {
			t.Fatalf("%s got=%v err=%v", test.op, got, err)
		}
	}
	if _, err := stringScalar("lower", []any{"İ"}); err == nil {
		t.Fatal("unverified Unicode case mapping accepted")
	}
}
