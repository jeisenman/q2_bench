package radar

import (
	"context"
	"github.com/jeisenman/q2_bench/workflows/formallineage/source"
	"testing"
)

func TestADFNestedEdgesAndUnknowns(t *testing.T) {
	b := []byte(`{"name":"transform","properties":{"activities":[{"name":"copy","type":"Copy"},{"name":"loop","type":"ForEach","dependsOn":[{"activity":"copy","dependencyConditions":["Succeeded"]}],"typeProperties":{"activities":[{"name":"calculate","type":"ExecutePipeline","typeProperties":{"pipeline":{"referenceName":"relationship-family-calculation"}}}]}}]}}`)
	receipt, _ := source.Receipt("0123456789012345678901234567890123456789", "pipeline/transform.json", b)
	result, err := Parse(context.Background(), "radar-adf-pipeline", receipt, b)
	if err != nil {
		t.Fatal(err)
	}
	if result.PredictionReady || len(result.Declarations) != 3 {
		t.Fatalf("invalid catalog %+v", result)
	}
	if result.Declarations[1].Dependencies[0] != "activity:copy" || result.Declarations[2].Dependencies[0] != "pipeline:relationship-family-calculation" {
		t.Fatal("dependency lost")
	}
	if result.Declarations[2].Span.JSONPointer != "/properties/activities/1/typeProperties/activities/0" {
		t.Fatal("nested pointer lost")
	}
	for _, d := range result.Declarations {
		if d.Method.Status != "unknown" || len(d.Method.Steps) > 0 {
			t.Fatal("orchestration became executable")
		}
	}
	if _, err := Parse(context.Background(), "pl-dataingress", receipt, b); err == nil {
		t.Fatal("accepted foreign repository")
	}
	receipt.SHA256 = "bad"
	if _, err := Parse(context.Background(), "radar-adf-pipeline", receipt, b); err == nil {
		t.Fatal("accepted stale receipt")
	}
}
