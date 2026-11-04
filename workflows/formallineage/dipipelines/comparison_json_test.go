package dipipelines

import (
	"context"
	"encoding/json"
	"math"
	"testing"
)

func TestComparisonJSONRetainsNegativeZeroWithoutChangingStringsOrFractions(t *testing.T) {
	b, err := json.Marshal(map[string]any{"negative_zero": math.Copysign(0, -1), "positive_zero": float64(0), "text": "-0, \"-0\"", "negative_fraction": float64(-0.5)})
	if err != nil {
		t.Fatal(err)
	}
	encoded := floatJSON(b)
	var decoded map[string]any
	if err := json.Unmarshal(encoded, &decoded); err != nil {
		t.Fatal(err)
	}
	if !math.Signbit(decoded["negative_zero"].(float64)) || math.Signbit(decoded["positive_zero"].(float64)) || decoded["text"] != "-0, \"-0\"" || decoded["negative_fraction"] != float64(-0.5) {
		t.Fatalf("float transport changed values: %s", encoded)
	}
	if string(floatJSON([]byte(`[-0,-0.1,"-0",-0e0]`))) != `[-0.0,-0.1,"-0",-0e0]` {
		t.Fatal("number token boundaries changed")
	}
}

func TestSelectStarExpandsSchemaAndPreservesAllRows(t *testing.T) {
	for _, projection := range []string{"'*'", "F.col('*')", "data.columns", "['id','value']"} {
		m := compiled(t, "from pyspark.sql import functions as F\ndef transform(data):\n    return data.select("+projection+")\n", "transform", "data")
		result, err := EvaluateOutputs(context.Background(), m, Bindings{Tables: map[string][]Row{"data": {{"id": "a", "value": nil}, {"id": "a", "value": nil}}}})
		if err != nil || len(result.Tables["output_1"]) != 2 || len(result.Schemas["output_1"]) != 2 {
			t.Fatalf("SELECT * lost rows or fields: %+v %v", result, err)
		}
	}
}
