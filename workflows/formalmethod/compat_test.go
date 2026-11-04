package formalmethod_test

import (
	"context"
	"encoding/json"
	"github.com/jeisenman/q2_bench/workflows/formallineage/model"
	"github.com/jeisenman/q2_bench/workflows/formallineage/source"
	"github.com/jeisenman/q2_bench/workflows/formalmethod"
	"testing"
)

func TestLegacyFacadeUsesSharedContract(t *testing.T) {
	b := []byte("def transform(df):\n    return df.filter(df.value > 0)\n")
	receipt, _ := source.Receipt("0123456789012345678901234567890123456789", "example.py", b)
	var method model.Method
	var err error
	method, err = formalmethod.Compile(b, receipt, "transform", []string{"df"})
	if err != nil || method.Status != "compiled" {
		t.Fatalf("compile %v %+v", err, method)
	}
	id, err := model.MethodID(method)
	if err != nil || method.ID != id {
		t.Fatal("method hash drift")
	}
	rows, err := formalmethod.Evaluate(context.Background(), method, formalmethod.Bindings{Tables: map[string][]formalmethod.Row{"df": {{"value": -1.0}, {"value": 0.0}, {"value": 1.0}}}})
	if err != nil || len(rows) != 1 {
		t.Fatalf("evaluate %v %+v", err, rows)
	}
	encoded, err := json.Marshal(method)
	if err != nil || len(encoded) == 0 {
		t.Fatal("JSON contract unavailable")
	}
}
