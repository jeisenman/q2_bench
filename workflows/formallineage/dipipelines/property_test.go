package dipipelines

import (
	"context"
	"encoding/json"
	"reflect"
	"testing"
)

func propertyFixture(t *testing.T) BoundarySuite {
	t.Helper()
	m := compiled(t, "def transform(data):\n    return data.filter(data.amount > 0)\n", "transform", "data")
	c := ComparisonCase{ID: "clause:example:0", Method: m, Clause: &ClauseEvidence{Source: m.Source},
		Bindings:     Bindings{Tables: map[string][]Row{"data": {{"amount": float64(-1)}, {"amount": float64(0)}, {"amount": float64(1)}, {"amount": nil}}}},
		SparkSchemas: map[string]string{"data": "`amount` double"}}
	return BoundarySuite{Format: "q2-boundary-suite/v1", Commit: m.Source.Commit, ScenarioLimit: 10, Cases: []ComparisonCase{c},
		Clauses: []BoundaryClause{{ID: "example", CaseIDs: []string{c.ID}}}}
}

func TestPropertyManifestRoundTripReplaysAllInstances(t *testing.T) {
	suite, err := GeneratePropertySuite(context.Background(), propertyFixture(t), PropertyConfig{Seeds: []uint64{1, 42}, SamplesPerTable: 3})
	if err != nil {
		t.Fatal(err)
	}
	dir := t.TempDir()
	if err := WriteBoundarySuite(dir, suite); err != nil {
		t.Fatal(err)
	}
	loaded, err := LoadBoundarySuite(dir)
	if err != nil || len(loaded.Cases) != 3 || len(loaded.Clauses[0].CaseIDs) != 3 {
		t.Fatalf("property manifest lost instances: %v", err)
	}
	if !reflect.DeepEqual(suite.Cases, loaded.Cases) {
		t.Fatal("property manifest changed seed metadata or generated bindings")
	}
}

func TestSeededPropertiesReplayRetainBoundariesAndDoNotMutateInputs(t *testing.T) {
	suite := propertyFixture(t)
	before, _ := json.Marshal(suite)
	config := PropertyConfig{Seeds: []uint64{0, 42}, SamplesPerTable: 32}
	a, err := GeneratePropertySuite(context.Background(), suite, config)
	if err != nil {
		t.Fatal(err)
	}
	b, err := GeneratePropertySuite(context.Background(), suite, config)
	if err != nil || !reflect.DeepEqual(a, b) || len(a.Cases) != 3 {
		t.Fatalf("properties are not reproducible: %v", err)
	}
	if reflect.DeepEqual(a.Cases[1].Bindings, a.Cases[2].Bindings) {
		t.Fatal("different seeds produced identical generated fixtures")
	}
	for _, c := range a.Cases[1:] {
		rows := c.Bindings.Tables["data"]
		if len(rows) != 36 || !reflect.DeepEqual(rows[:4], suite.Cases[0].Bindings.Tables["data"]) || c.Generation == nil {
			t.Fatal("exact boundary rows or requested sample count changed")
		}
		result, err := EvaluateOutputs(context.Background(), c.Method, c.Bindings)
		if err != nil {
			t.Fatal(err)
		}
		for _, row := range result.Tables["output_1"] {
			if !(row["amount"].(float64) > 0) {
				t.Fatal("filter returned a null, equal, or below-boundary value")
			}
		}
	}
	config.Seeds[0] = 99
	if err := validatePropertyReplay(a); err != nil {
		t.Fatal(err)
	}
	after, _ := json.Marshal(suite)
	if string(before) != string(after) || a.PropertyConfig.Seeds[0] != 0 {
		t.Fatal("generation aliased caller-owned inputs")
	}
}

func TestPropertyReplayRejectsChangedSamplesAndMetadata(t *testing.T) {
	suite, err := GeneratePropertySuite(context.Background(), propertyFixture(t), PropertyConfig{Seeds: []uint64{42}, SamplesPerTable: 2})
	if err != nil {
		t.Fatal(err)
	}
	suite.Cases[1].Bindings.Tables["data"][4]["amount"] = "tampered"
	if err := validatePropertyReplay(suite); err == nil {
		t.Fatal("modified generated rows accepted as seeded evidence")
	}
	suite.PropertyConfig = nil
	if err := validatePropertyReplay(suite); err == nil {
		t.Fatal("orphaned generator metadata accepted")
	}
	suite.PropertyConfig = &PropertyConfig{Seeds: []uint64{42}, SamplesPerTable: 2}
	suite.Cases = suite.Cases[:1]
	suite.Clauses[0].CaseIDs = suite.Clauses[0].CaseIDs[:1]
	if err := validatePropertyReplay(suite); err == nil {
		t.Fatal("removing all seeded tests silently reduced property coverage")
	}
}

func TestPropertyBoundsAndUnsupportedSchemasFailExplicitly(t *testing.T) {
	for _, config := range []PropertyConfig{{}, {Seeds: []uint64{1}, SamplesPerTable: 0}, {Seeds: []uint64{1}, SamplesPerTable: 257}, {Seeds: []uint64{1, 1}, SamplesPerTable: 1}} {
		if _, err := GeneratePropertySuite(context.Background(), propertyFixture(t), config); err == nil {
			t.Fatalf("invalid property bounds accepted: %+v", config)
		}
	}
	suite := propertyFixture(t)
	suite.Cases[0].SparkSchemas["data"] = "amount struct<value:double>"
	if _, err := GeneratePropertySuite(context.Background(), suite, PropertyConfig{Seeds: []uint64{1}, SamplesPerTable: 1}); err == nil {
		t.Fatal("unsupported schema silently generated primitive values")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := GeneratePropertySuite(ctx, propertyFixture(t), PropertyConfig{Seeds: []uint64{1}, SamplesPerTable: 1}); err == nil {
		t.Fatal("cancelled generation continued")
	}
}
