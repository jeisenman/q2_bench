package formalmethod

import "testing"

func TestImpossibleNumericBoundsRespectInclusivityFieldsAndOr(t *testing.T) {
	for _, test := range []struct {
		condition  string
		impossible bool
	}{
		{"(F.col('x') < -10) & (F.col('x') > 120)", true},
		{"(F.col('x') >= 0) & (F.col('x') < 0)", true},
		{"(F.col('x') >= 0) & (F.col('x') <= 0)", false},
		{"(F.col('x') < -10) | (F.col('x') > 120)", false},
		{"(F.col('x') < -10) & (F.col('y') > 120)", false},
	} {
		m := compiled(t, "from pyspark.sql import functions as F\ndef transform(data):\n    return data.filter("+test.condition+")\n", "transform", "data")
		_, reason := impossiblePredicate(m.Steps[0].Expression.Args[1], "data")
		if (reason != "") != test.impossible {
			t.Fatalf("%s -> %s", test.condition, reason)
		}
	}
}
