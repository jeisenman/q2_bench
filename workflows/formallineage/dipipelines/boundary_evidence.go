package dipipelines

import (
	"context"
	"encoding/json"
	"fmt"
)

// ClauseObservation is one Databricks comparison result, retaining errors.
type ClauseObservation struct {
	ID               string                          `json:"id"`
	MethodID         string                          `json:"method_id"`
	Source           Source                          `json:"source"`
	BindingsSHA256   string                          `json:"bindings_sha256"`
	PredictionSHA256 string                          `json:"prediction_sha256"`
	Status           string                          `json:"status"`
	Error            string                          `json:"error"`
	Outputs          map[string]ClauseOutputEvidence `json:"outputs"`
}

// ClauseOutputEvidence retains the remote row-bag and schema comparison outcome.
type ClauseOutputEvidence struct {
	Status         string         `json:"status"`
	SchemaMatches  bool           `json:"schema_matches"`
	PredictedCount int            `json:"predicted_count"`
	ObservedCount  int            `json:"observed_count"`
	Missing        map[string]int `json:"missing"`
	Unexpected     map[string]int `json:"unexpected"`
}

// BoundaryJobEvidence reports isolated clause evidence without passing a job.
type BoundaryJobEvidence struct {
	EntryPoint     string `json:"entrypoint"`
	Clauses        int    `json:"audited_clause_candidates"`
	FixtureClauses int    `json:"clauses_with_fixtures"`
	Passed         int    `json:"passed_clause_cases"`
	Failed         int    `json:"failed_clause_cases"`
	Missing        int    `json:"unobserved_clause_cases"`
	Status         string `json:"status"`
}

// BoundaryEvidence joins observations to their exact current input/method pins.
// Historical failures whose cases are now unsupported remain separate findings.
type BoundaryEvidence struct {
	Format         string                `json:"format"`
	Commit         string                `json:"commit"`
	Expected       int                   `json:"expected_clause_cases"`
	Passed         int                   `json:"passed_clause_cases"`
	Failed         int                   `json:"failed_clause_cases"`
	Missing        int                   `json:"unobserved_clause_cases"`
	Historical     []ClauseObservation   `json:"historical_failures_outside_current_profile"`
	Jobs           []BoundaryJobEvidence `json:"jobs"`
	WholeJobPasses int                   `json:"whole_job_passes"`
	Status         string                `json:"status"`
}

// PendingBoundaryCases selects manifest-declared cases lacking exact passing evidence.
// Stale method/input observations require another Databricks execution.
func PendingBoundaryCases(ctx context.Context, suite BoundarySuite, observations []ClauseObservation) ([]ComparisonCase, error) {
	seen := map[string]ClauseObservation{}
	for _, o := range observations {
		if _, duplicate := seen[o.ID]; duplicate {
			return nil, fmt.Errorf("duplicate observation for %s; select an explicit run", o.ID)
		}
		seen[o.ID] = o
	}
	pending := []ComparisonCase{}
	for _, c := range suite.Cases {
		if c.Clause == nil {
			return nil, fmt.Errorf("case %s lacks original clause evidence", c.ID)
		}
		o, ok := seen[c.ID]
		b, _ := json.Marshal(c.Bindings)
		if !ok || o.Status != "pass" || o.MethodID != c.Method.ID || o.Source != c.Clause.Source || o.BindingsSHA256 != hash(b) {
			pending = append(pending, c)
			continue
		}
		prediction, err := EvaluateOutputs(ctx, c.Method, c.Bindings)
		if err != nil {
			return nil, err
		}
		matches := o.PredictionSHA256 == hash([]byte(boundaryResultKey(prediction))) && len(o.Outputs) == len(prediction.Tables)
		for port, rows := range prediction.Tables {
			output, ok := o.Outputs[port]
			if !ok || output.Status != "pass" || !output.SchemaMatches || output.PredictedCount != len(rows) || output.ObservedCount != len(rows) || len(output.Missing) > 0 || len(output.Unexpected) > 0 {
				matches = false
			}
		}
		if !matches {
			pending = append(pending, c)
		}
	}
	return pending, nil
}

// DecodeBoundaryObservations accepts embedded Jobs API output or result JSON.
func DecodeBoundaryObservations(content []byte) ([]ClauseObservation, error) {
	var wrapper struct {
		Notebook struct {
			Result string `json:"result"`
		} `json:"notebook_output"`
	}
	if err := json.Unmarshal(content, &wrapper); err != nil {
		return nil, err
	}
	if wrapper.Notebook.Result != "" {
		content = []byte(wrapper.Notebook.Result)
	}
	var result struct {
		Format   string              `json:"format"`
		WholeJob bool                `json:"whole_job_coverage"`
		Results  []ClauseObservation `json:"results"`
	}
	if err := json.Unmarshal(content, &result); err != nil {
		return nil, err
	}
	if !in(result.Format, "q2-formal-comparison-result/v1", "q2-formal-comparison-result/v2") || result.WholeJob || len(result.Results) == 0 {
		return nil, fmt.Errorf("require nonempty versioned isolated comparison results")
	}
	return result.Results, nil
}

// CheckBoundaryEvidence rejects foreign passing cases and stale input evidence.
func CheckBoundaryEvidence(ctx context.Context, suite BoundarySuite, observations []ClauseObservation) (BoundaryEvidence, error) {
	report := BoundaryEvidence{Format: "q2-boundary-evidence/v1", Commit: suite.Commit, Expected: len(suite.Cases), Historical: []ClauseObservation{}, Jobs: []BoundaryJobEvidence{}, Status: "blocked"}
	expected := map[string]ComparisonCase{}
	clauses := map[string]BoundaryClause{}
	for _, clause := range suite.Clauses {
		clauses[clause.ID] = clause
	}
	for _, c := range suite.Cases {
		if _, exists := expected[c.ID]; exists || c.Clause == nil {
			return report, fmt.Errorf("expected clause case IDs must be unique with original evidence")
		}
		expected[c.ID] = c
	}
	declared := map[string]bool{}
	for _, clause := range suite.Clauses {
		for _, id := range clause.CaseIDs {
			c, ok := expected[id]
			if !ok || c.Clause.Source != clause.Source || c.Clause.StartByte != clause.StartByte || c.Clause.EndByte != clause.EndByte {
				return report, fmt.Errorf("clause %s has missing or inconsistent case %s", clause.ID, id)
			}
			declared[id] = true
		}
	}
	if len(declared) != len(expected) {
		return report, fmt.Errorf("comparison cases and declared clause coverage differ")
	}
	seen := map[string]string{}
	for _, o := range observations {
		if err := ctx.Err(); err != nil {
			return report, err
		}
		if !in(o.Status, "pass", "fail", "error") {
			return report, fmt.Errorf("case %s has unsupported observation status", o.ID)
		}
		c, exists := expected[o.ID]
		if !exists {
			if o.Status == "pass" {
				return report, fmt.Errorf("passing case %s is absent from current suite", o.ID)
			}
			report.Historical = append(report.Historical, o)
			continue
		}
		if _, duplicate := seen[o.ID]; duplicate {
			return report, fmt.Errorf("duplicate observation for %s; select an explicit run", o.ID)
		}
		if o.Status != "error" {
			b, _ := json.Marshal(c.Bindings)
			if o.MethodID != c.Method.ID || o.Source != c.Clause.Source || o.BindingsSHA256 != hash(b) {
				return report, fmt.Errorf("case %s observation does not match current method, source and inputs", o.ID)
			}
		}
		if o.Status == "pass" {
			prediction, err := EvaluateOutputs(ctx, c.Method, c.Bindings)
			if err != nil {
				return report, err
			}
			if o.PredictionSHA256 != hash([]byte(boundaryResultKey(prediction))) {
				return report, fmt.Errorf("case %s has stale/missing predicted-output digest; rerun with comparison protocol v2", o.ID)
			}
			if len(o.Outputs) != len(prediction.Tables) {
				return report, fmt.Errorf("case %s has incomplete output evidence", o.ID)
			}
			for port, rows := range prediction.Tables {
				output, ok := o.Outputs[port]
				if !ok || output.Status != "pass" || !output.SchemaMatches || output.PredictedCount != len(rows) || output.ObservedCount != len(rows) || len(output.Missing) > 0 || len(output.Unexpected) > 0 {
					return report, fmt.Errorf("case %s has inconsistent passing output evidence", o.ID)
				}
			}
		}
		seen[o.ID] = o.Status
		if o.Status == "pass" {
			report.Passed++
		} else {
			report.Failed++
		}
	}
	report.Missing = report.Expected - report.Passed - report.Failed
	for _, job := range suite.Jobs {
		r := BoundaryJobEvidence{EntryPoint: job.EntryPoint, Clauses: len(job.ClauseIDs), Status: "blocked_whole_job"}
		for _, id := range job.ClauseIDs {
			clause, ok := clauses[id]
			if !ok {
				return report, fmt.Errorf("job %s references missing clause %s", job.EntryPoint, id)
			}
			if len(clause.CaseIDs) > 0 {
				r.FixtureClauses++
			}
			for _, caseID := range clause.CaseIDs {
				switch seen[caseID] {
				case "pass":
					r.Passed++
				case "fail", "error":
					r.Failed++
				default:
					r.Missing++
				}
			}
		}
		report.Jobs = append(report.Jobs, r)
	}
	return report, nil
}
