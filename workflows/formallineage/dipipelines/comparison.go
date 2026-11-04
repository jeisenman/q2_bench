package dipipelines

import (
	"bytes"
	"compress/gzip"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
)

// ComparisonCase binds an independently evaluated method to Spark input schemas.
type ComparisonCase struct {
	ID             string              `json:"id"`
	Method         Method              `json:"method"`
	Bindings       Bindings            `json:"bindings"`
	SparkSchemas   map[string]string   `json:"spark_schemas"`
	Clause         *ClauseEvidence     `json:"clause,omitempty"`
	ObserveColumns []string            `json:"observe_columns,omitempty"`
	ObserveRows    bool                `json:"observe_rows,omitempty"`
	Generation     *PropertyGeneration `json:"generation,omitempty"`
}

// CaseRecipe selects source and boundary types without supplying a formal program.
type CaseRecipe struct {
	ID           string            `json:"id"`
	Commit       string            `json:"commit"`
	Path         string            `json:"path"`
	Function     string            `json:"function"`
	Tables       []string          `json:"tables"`
	Bindings     Bindings          `json:"bindings"`
	SparkSchemas map[string]string `json:"spark_schemas"`
}

// CompileCases mechanically derives every method from its pinned source recipe.
func CompileCases(ctx context.Context, root string, recipes []CaseRecipe) ([]ComparisonCase, error) {
	result := []ComparisonCase{}
	for _, r := range recipes {
		m, err := CompileGit(ctx, root, r.Commit, r.Path, r.Function, r.Tables)
		if err != nil {
			return nil, err
		}
		if m.Status != "compiled" {
			return nil, fmt.Errorf("case %s has unknown method: %+v", r.ID, m.Diagnostics)
		}
		result = append(result, ComparisonCase{ID: r.ID, Method: m, Bindings: r.Bindings, SparkSchemas: r.SparkSchemas})
	}
	return result, nil
}

// Prediction retains exact input identity and the independently computed row bag.
type Prediction struct {
	Case             ComparisonCase      `json:"case"`
	Rows             []Row               `json:"predicted_rows"`
	Outputs          map[string][]Row    `json:"predicted_outputs"`
	Schemas          map[string][]string `json:"predicted_schemas"`
	BindingsSHA256   string              `json:"bindings_sha256"`
	PredictionSHA256 string              `json:"prediction_sha256"`
}

// ComparisonPayload binds original source bytes to independent Go predictions.
type ComparisonPayload struct {
	Format      string            `json:"format"`
	Sources     map[string]string `json:"sources"`
	Predictions []Prediction      `json:"predictions"`
}

// PrepareComparison evaluates every case in Go and creates an immutable payload.
// The remote notebook executes only selected original function definitions.
func PrepareComparison(ctx context.Context, root string, cases []ComparisonCase) (ComparisonPayload, error) {
	p := ComparisonPayload{Format: "q2-formal-comparison/v2", Sources: map[string]string{}, Predictions: []Prediction{}}
	if len(cases) < 1 || len(cases) > 1000 {
		return p, fmt.Errorf("comparison requires 1..1000 cases")
	}
	seen := map[string]bool{}
	for _, c := range cases {
		if c.ID == "" || seen[c.ID] {
			return p, fmt.Errorf("comparison IDs must be nonempty and unique")
		}
		seen[c.ID] = true
		source := c.Method.Source
		key := source.Commit + ":" + source.Path
		if c.Clause != nil {
			if err := prepareClause(ctx, root, c, &p); err != nil {
				return p, err
			}
		}
		if _, ok := p.Sources[key]; !ok {
			b, err := readGit(ctx, root, source.Commit, source.Path)
			if err != nil {
				return p, err
			}
			if hash(b) != source.SHA256 {
				return p, fmt.Errorf("comparison source digest mismatch")
			}
			p.Sources[key] = string(b)
		}
		for name := range c.Bindings.Tables {
			if c.SparkSchemas[name] == "" {
				return p, fmt.Errorf("case %s table %s needs Spark schema", c.ID, name)
			}
		}
		result, err := EvaluateOutputs(ctx, c.Method, c.Bindings)
		if err != nil {
			return p, fmt.Errorf("case %s: %w", c.ID, err)
		}
		b, err := json.Marshal(c.Bindings)
		if err != nil {
			return p, err
		}
		var rows []Row
		if len(c.Method.Outputs) == 1 {
			rows = result.Tables[c.Method.Outputs[0].Name]
		}
		p.Predictions = append(p.Predictions, Prediction{Case: c, Rows: rows, Outputs: result.Tables, Schemas: result.Schemas, BindingsSHA256: hash(b), PredictionSHA256: hash([]byte(boundaryResultKey(result)))})
	}
	return p, nil
}

// Notebook encodes bounded source/predictions alongside reviewed notebook code.
func (p ComparisonPayload) Notebook(template string) (string, error) {
	b, err := json.Marshal(p)
	if err != nil {
		return "", err
	}
	b = floatJSON(b)
	var compressed bytes.Buffer
	w := gzip.NewWriter(&compressed)
	if _, err = w.Write(b); err != nil {
		return "", err
	}
	if err = w.Close(); err != nil {
		return "", err
	}
	source := "# Databricks notebook source\nimport base64, gzip, json\nPAYLOAD = json.loads(gzip.decompress(base64.b64decode(" + fmt.Sprintf("%q", base64.StdEncoding.EncodeToString(compressed.Bytes())) + ")))\n" + template
	if len(source) > 990000 {
		return "", fmt.Errorf("comparison notebook exceeds SOURCE bound")
	}
	return source, nil
}
