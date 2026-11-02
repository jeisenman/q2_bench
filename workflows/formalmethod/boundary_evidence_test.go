package formalmethod

import (
	"context"
	"encoding/json"
	"testing"
)

func TestBoundaryEvidenceRejectsStaleForeignDuplicateAndIncompletePasses(t *testing.T) {
	m := boundaryModule(t, "from pyspark.sql import functions as F\ndef transform(data):\n    return data.filter(F.col('x') > 0)\n")
	var clause BoundaryClause
	for _, c := range extractBoundaryClauses(m) {
		if c.Kind == "filter" {
			clause = c
			break
		}
	}
	cases, reason := clauseCases(context.Background(), m, clause)
	if len(cases) != 2 {
		t.Fatal(reason)
	}
	observations := []ClauseObservation{}
	for _, c := range cases {
		clause.CaseIDs = append(clause.CaseIDs, c.ID)
		b, _ := json.Marshal(c.Bindings)
		result, err := EvaluateOutputs(context.Background(), c.Method, c.Bindings)
		if err != nil {
			t.Fatal(err)
		}
		outputs := map[string]ClauseOutputEvidence{}
		for port, rows := range result.Tables {
			outputs[port] = ClauseOutputEvidence{Status: "pass", SchemaMatches: true, PredictedCount: len(rows), ObservedCount: len(rows)}
		}
		observations = append(observations, ClauseObservation{ID: c.ID, MethodID: c.Method.ID, Source: c.Clause.Source, BindingsSHA256: hash(b), PredictionSHA256: hash([]byte(boundaryResultKey(result))), Status: "pass", Outputs: outputs})
	}
	suite := BoundarySuite{Commit: m.source.Commit, Cases: cases, Clauses: []BoundaryClause{clause}, Jobs: []BoundaryJob{{EntryPoint: "job.Example", ClauseIDs: []string{clause.ID}}}}
	report, err := CheckBoundaryEvidence(context.Background(), suite, observations)
	if err != nil || report.Passed != 2 || report.Missing != 0 || report.WholeJobPasses != 0 || report.Status != "blocked" {
		t.Fatalf("evidence=%+v %v", report, err)
	}
	for _, field := range []string{"source", "inputs", "method", "foreign", "outputs"} {
		changed := append([]ClauseObservation{}, observations...)
		switch field {
		case "source":
			changed[0].Source.SHA256 = "stale"
		case "inputs":
			changed[0].BindingsSHA256 = "stale"
		case "method":
			changed[0].MethodID = "stale"
		case "foreign":
			changed[0].ID = "not_in_suite"
		case "outputs":
			changed[0].Outputs = nil
		}
		if _, err := CheckBoundaryEvidence(context.Background(), suite, changed); err == nil {
			t.Fatalf("accepted stale %s evidence", field)
		}
	}
	if _, err := CheckBoundaryEvidence(context.Background(), suite, append(observations, observations[0])); err == nil {
		t.Fatal("duplicate observation accepted")
	}
	partial, err := CheckBoundaryEvidence(context.Background(), suite, observations[:1])
	if err != nil || partial.Missing != 1 {
		t.Fatalf("missing observation disappeared: %+v %v", partial, err)
	}
	pending, err := PendingBoundaryCases(context.Background(), suite, observations)
	if err != nil || len(pending) != 0 {
		t.Fatalf("exact fresh observations not reusable: %v", err)
	}
	legacy := append([]ClauseObservation{}, observations...)
	legacy[0].PredictionSHA256 = ""
	pending, err = PendingBoundaryCases(context.Background(), suite, legacy)
	if err != nil || len(pending) != 1 {
		t.Fatal("legacy output evidence was silently reused")
	}
	historical, err := CheckBoundaryEvidence(context.Background(), suite, append(observations, ClauseObservation{ID: "now_unsupported", Status: "error", Error: "nested field"}))
	if err != nil || len(historical.Historical) != 1 {
		t.Fatal("historical failure disappeared")
	}
	mutants := fixtureMutations(context.Background(), cases)
	if len(mutants) != 1 || mutants[0].Status != "killed" {
		t.Fatalf("equality boundary failed to detect > becoming >=: %+v", mutants)
	}
}
