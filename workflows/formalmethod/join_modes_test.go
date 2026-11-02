package formalmethod

import (
	"context"
	"testing"
)

func TestNamedJoinModesPreserveDuplicatesNullsAndUnmatchedKeys(t *testing.T) {
	for _, test := range []struct {
		how           string
		rows, columns int
	}{{"inner", 4, 3}, {"left", 6, 3}, {"right", 6, 3}, {"full", 8, 3}, {"left_semi", 2, 2}, {"left_anti", 2, 2}, {"left_outer", 6, 3}, {"full_outer", 8, 3}} {
		t.Run(test.how, func(t *testing.T) {
			m := compiled(t, "def transform(left, right):\n    return left.join(right, on='id', how='"+test.how+"')\n", "transform", "left", "right")
			result, err := EvaluateOutputs(context.Background(), m, Bindings{Tables: map[string][]Row{
				"left":  {{"id": "match", "left": "L"}, {"id": "match", "left": "L"}, {"id": "left_only", "left": "L"}, {"id": nil, "left": "L"}},
				"right": {{"id": "match", "right": "R"}, {"id": "match", "right": "R"}, {"id": "right_only", "right": "R"}, {"id": nil, "right": "R"}},
			}})
			if err != nil || len(result.Tables["output_1"]) != test.rows || len(result.Schemas["output_1"]) != test.columns {
				t.Fatalf("mode %s: %+v %v", test.how, result, err)
			}
			if test.how == "right" || test.how == "full" {
				found := false
				for _, row := range result.Tables["output_1"] {
					if row["id"] == "right_only" {
						found = true
						if row["left"] != nil || row["right"] != "R" {
							t.Fatal("unmatched right row/key lost")
						}
					}
				}
				if !found {
					t.Fatal("right-only key was lost")
				}
			}
		})
	}
}

func TestSemiJoinDoesNotRequireDistinctNonKeyNames(t *testing.T) {
	m := compiled(t, "def transform(left, right):\n    return left.join(right, on='id', how='left_semi')\n", "transform", "left", "right")
	rows, err := Evaluate(context.Background(), m, Bindings{Tables: map[string][]Row{"left": {{"id": "a", "value": "left"}}, "right": {{"id": "a", "value": "right"}}}})
	if err != nil || len(rows) != 1 || rows[0]["value"] != "left" {
		t.Fatalf("semi schema: %v %v", rows, err)
	}
}
