// Package radar discovers notebook/library transforms and ADF orchestration.
package radar

import (
	"context"
	"encoding/json"
	"fmt"
	"github.com/jeisenman/q2_bench/workflows/formallineage/discovery"
	"github.com/jeisenman/q2_bench/workflows/formallineage/model"
	"github.com/jeisenman/q2_bench/workflows/formallineage/projects"
	"github.com/jeisenman/q2_bench/workflows/formallineage/source"
	"strings"
)

// Parse uses the common Python grammar or ADF JSON activity declarations.
func Parse(ctx context.Context, repository string, receipt model.Source, content []byte) (model.ParsedFile, error) {
	if err := projects.Allows("radar", repository); err != nil {
		return model.ParsedFile{}, err
	}
	if repository == "radar-adf-pipeline" {
		return parseADF(ctx, receipt, content)
	}
	if !strings.HasSuffix(receipt.Path, ".py") {
		return model.ParsedFile{}, fmt.Errorf("RADAR notebook/library parsing requires Python SOURCE")
	}
	return discovery.Parse(ctx, "radar", repository, receipt, content)
}

type activity struct {
	Name      string `json:"name"`
	Type      string `json:"type"`
	DependsOn []struct {
		Activity   string   `json:"activity"`
		Conditions []string `json:"dependencyConditions"`
	} `json:"dependsOn"`
	Properties json.RawMessage `json:"typeProperties"`
}

func parseADF(ctx context.Context, receipt model.Source, content []byte) (model.ParsedFile, error) {
	actual, err := source.Receipt(receipt.Commit, receipt.Path, content)
	if err != nil || actual != receipt || len(content) > 1<<20 {
		return model.ParsedFile{}, fmt.Errorf("ADF requires matching source receipt and at most 1 MiB")
	}
	if !strings.HasPrefix(receipt.Path, "pipeline/") || !strings.HasSuffix(receipt.Path, ".json") {
		return model.ParsedFile{}, fmt.Errorf("ADF discovery currently supports pipeline/*.json only")
	}
	var document struct {
		Name       string `json:"name"`
		Properties struct {
			Activities []json.RawMessage `json:"activities"`
		} `json:"properties"`
	}
	if err := json.Unmarshal(content, &document); err != nil {
		return model.ParsedFile{}, fmt.Errorf("parse ADF: %w", err)
	}
	if document.Name == "" || document.Properties.Activities == nil {
		return model.ParsedFile{}, fmt.Errorf("ADF requires pipeline name and activities")
	}
	result := model.ParsedFile{Format: "q2-formal-source-catalog/v1", Project: "radar", Repository: "radar-adf-pipeline", Source: receipt, Runtime: model.ADF, Status: "unknown", Declarations: []model.Declaration{}, ModuleCalls: []model.Operation{}, Imports: []string{}, Unresolved: []string{"ADF expressions, conditional execution, referenced pipelines, datasets and side effects need semantic binding.", "Activity dependencies are source declarations, not executed data lineage."}}
	var walk func([]json.RawMessage, string, int) error
	walk = func(raws []json.RawMessage, pointer string, depth int) error {
		if err := ctx.Err(); err != nil {
			return err
		}
		if depth > 32 {
			return fmt.Errorf("ADF nesting exceeds 32")
		}
		names := map[string]bool{}
		for i, raw := range raws {
			if len(result.Declarations) >= 5000 {
				return fmt.Errorf("ADF exceeds 5000 activities")
			}
			var a activity
			if err := json.Unmarshal(raw, &a); err != nil {
				return err
			}
			if a.Name == "" || a.Type == "" || names[a.Name] {
				return fmt.Errorf("ADF activity requires unique sibling name and type")
			}
			names[a.Name] = true
			p := fmt.Sprintf("%s/%d", pointer, i)
			m := model.Method{Format: model.Format, Profile: "adf/unbound/v1", Source: receipt, Function: document.Name + ":" + p + ":" + a.Name, Status: "unknown", Steps: []model.Step{}, Diagnostics: []model.Diagnostic{{Message: "Orchestration runtime and external effects unresolved."}}}
			m.ID, err = model.MethodID(m)
			if err != nil {
				return err
			}
			d := model.Declaration{Method: m, Runtime: model.ADF, Span: model.Span{JSONPointer: p}, Operations: []model.Operation{{Kind: "orchestrate", Expression: string(raw), Span: model.Span{JSONPointer: p}}}, Dependencies: []string{}}
			for _, dep := range a.DependsOn {
				d.Dependencies = append(d.Dependencies, "activity:"+dep.Activity)
			}
			var properties struct {
				Pipeline struct {
					ReferenceName string `json:"referenceName"`
				} `json:"pipeline"`
				Activities []json.RawMessage `json:"activities"`
				True       []json.RawMessage `json:"ifTrueActivities"`
				False      []json.RawMessage `json:"ifFalseActivities"`
				Default    []json.RawMessage `json:"defaultActivities"`
				Cases      []struct {
					Activities []json.RawMessage `json:"activities"`
				} `json:"cases"`
			}
			if len(a.Properties) > 0 {
				if err := json.Unmarshal(a.Properties, &properties); err != nil {
					return err
				}
			}
			if properties.Pipeline.ReferenceName != "" {
				d.Dependencies = append(d.Dependencies, "pipeline:"+properties.Pipeline.ReferenceName)
			}
			result.Declarations = append(result.Declarations, d)
			for _, nested := range []struct {
				name   string
				values []json.RawMessage
			}{{"activities", properties.Activities}, {"ifTrueActivities", properties.True}, {"ifFalseActivities", properties.False}, {"defaultActivities", properties.Default}} {
				if err := walk(nested.values, p+"/typeProperties/"+nested.name, depth+1); err != nil {
					return err
				}
			}
			for j, c := range properties.Cases {
				if err := walk(c.Activities, fmt.Sprintf("%s/typeProperties/cases/%d/activities", p, j), depth+1); err != nil {
					return err
				}
			}
		}
		return nil
	}
	if err := walk(document.Properties.Activities, "/properties/activities", 0); err != nil {
		return model.ParsedFile{}, err
	}
	return result, nil
}
