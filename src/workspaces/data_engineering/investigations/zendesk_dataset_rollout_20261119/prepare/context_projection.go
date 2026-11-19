package main

import (
	"bytes"
	_ "embed"
	"encoding/json"
	"fmt"
	"regexp"

	"github.com/jeisenman/q2_bench/src/workspaces/data_engineering/investigations/zendesk_dataset_rollout_20261119/contract"
)

const contextVersion = "dataset-edit-context/1"
const contextPolicySHA = "aeeb498c3ffee00a35b086e65294f5e38c5345780dc5737b20b1734baf52a860"

//go:embed policies/evidence-context-projection-v1.md
var contextPolicy []byte

type sourceLocation struct {
	Pin    int    `json:"pin"`
	Path   string `json:"path,omitempty"`
	SHA256 string `json:"sha256,omitempty"`
}
type sourcePool struct {
	Pins      []contract.Source `json:"pins"`
	Locations []sourceLocation  `json:"locations"`
}
type modelJob struct {
	ID      contract.NodeID `json:"id"`
	DAG     string          `json:"dag,omitempty"`
	Sources []int           `json:"source_refs"`
}
type modelColumn struct {
	ID       contract.NodeID `json:"id"`
	Type     string          `json:"type"`
	Nullable bool            `json:"nullable"`
}
type modelTarget struct {
	NodeID       string          `json:"node_id"`
	ID           contract.NodeID `json:"id"`
	Kind         string          `json:"kind"`
	Scope        string          `json:"scope"`
	Generation   string          `json:"generation_id"`
	Bundle       string          `json:"bundle_id"`
	Key          string          `json:"lineage_node_key"`
	Sources      []int           `json:"source_refs"`
	SourcePool   sourcePool      `json:"source_pool"`
	Columns      []modelColumn   `json:"columns"`
	Producers    []modelJob      `json:"producers"`
	Consumers    []modelJob      `json:"consumers"`
	CopiesStatus string          `json:"copies_status"`
}
type contextProvenance struct {
	Contract             policyRecord `json:"contract"`
	FullTarget           fileRecord   `json:"full_target"`
	OriginalRequest      fileRecord   `json:"original_request"`
	NeighborEvidencePath string       `json:"neighbor_evidence_path"`
	OmittedNeighborKeys  []string     `json:"omitted_neighbor_keys"`
	CodeSourceRawSHA     string       `json:"code_context_source_raw_sha256"`
	CodeProjectedRawSHA  string       `json:"code_context_projected_raw_sha256"`
	CodeCanonicalSHA     string       `json:"code_context_canonical_json_sha256"`
}
type neighbor struct {
	ID        string          `json:"id"`
	Kind      string          `json:"kind"`
	Namespace string          `json:"namespace"`
	Name      string          `json:"name"`
	Version   json.RawMessage `json:"version"`
}
type relation struct {
	Node         neighbor `json:"node"`
	Relationship string   `json:"relationship"`
}
type relationContext struct {
	Incoming []relation `json:"incoming"`
	Outgoing []relation `json:"outgoing"`
}

var unusualCode = regexp.MustCompile("(?i)```|\\bSELECT\\s|\\bdef\\s+\\w+\\(|\\bimport\\s+\\w+|\\bfunction\\s+\\w+\\(")

func thinTarget(t target) modelTarget {
	out := modelTarget{NodeID: t.NodeID, ID: t.Dataset.ID, Kind: t.Kind, Scope: t.Scope, Generation: t.Generation, Bundle: t.Bundle, Key: t.Key, Columns: []modelColumn{}, Producers: []modelJob{}, Consumers: []modelJob{}, CopiesStatus: t.CopiesStatus, SourcePool: sourcePool{Pins: []contract.Source{}, Locations: []sourceLocation{}}}
	pins := map[contract.Source]int{}
	locations := map[sourceLocation]int{}
	refs := func(sources []contract.Source) []int {
		result := []int{}
		for _, source := range sources {
			pin := source
			pin.Path = ""
			pin.SHA256 = ""
			pinID, ok := pins[pin]
			if !ok {
				pinID = len(out.SourcePool.Pins)
				pins[pin] = pinID
				out.SourcePool.Pins = append(out.SourcePool.Pins, pin)
			}
			location := sourceLocation{Pin: pinID, Path: source.Path, SHA256: source.SHA256}
			index, ok := locations[location]
			if !ok {
				index = len(out.SourcePool.Locations)
				locations[location] = index
				out.SourcePool.Locations = append(out.SourcePool.Locations, location)
			}
			result = append(result, index)
		}
		return result
	}
	out.Sources = refs(t.Dataset.Sources)
	for _, column := range t.Columns {
		out.Columns = append(out.Columns, modelColumn{ID: column.ID, Type: column.Column.Type, Nullable: column.Column.Nullable})
	}
	for _, job := range t.Producers {
		out.Producers = append(out.Producers, modelJob{ID: job.ID, DAG: job.Job.DAG, Sources: refs(job.Sources)})
	}
	for _, job := range t.Consumers {
		out.Consumers = append(out.Consumers, modelJob{ID: job.ID, DAG: job.Job.DAG, Sources: refs(job.Sources)})
	}
	return out
}

func canonicalSHA(raw []byte) (string, error) {
	var compact bytes.Buffer
	if err := json.Compact(&compact, raw); err != nil {
		return "", err
	}
	return digest(compact.Bytes()), nil
}

func projectTechnical(evidence map[string]json.RawMessage, fullTarget, original fileRecord) (map[string]json.RawMessage, contextProvenance, error) {
	proof := contextProvenance{Contract: policyRecord{Version: contextVersion, Path: "sources/evidence-context-projection.md", SHA256: contextPolicySHA}, FullTarget: fullTarget, OriginalRequest: original, NeighborEvidencePath: "evidence.graphContext", OmittedNeighborKeys: []string{"description", "sourceLocations", "transformations"}}
	if digest(contextPolicy) != contextPolicySHA {
		return nil, proof, fmt.Errorf("evidence context projection policy digest mismatch")
	}
	out := map[string]json.RawMessage{}
	for key, value := range evidence {
		if key != "zendeskContext" && key != "prompt" {
			out[key] = value
		}
	}
	raw, ok := evidence["graphContext"]
	if !ok {
		return nil, proof, fmt.Errorf("published request lacks graphContext")
	}
	projected, err := projectRelations(raw)
	if err != nil {
		return nil, proof, err
	}
	out["graphContext"] = projected
	if _, ok := evidence["targetNode"]; !ok {
		return nil, proof, fmt.Errorf("published request lacks targetNode")
	}
	code, ok := evidence["codeContext"]
	if !ok {
		return nil, proof, fmt.Errorf("published request lacks codeContext")
	}
	proof.CodeSourceRawSHA = digest(code)
	proof.CodeProjectedRawSHA = digest(out["codeContext"])
	if proof.CodeSourceRawSHA != proof.CodeProjectedRawSHA {
		return nil, proof, fmt.Errorf("codeContext changed during projection")
	}
	proof.CodeCanonicalSHA, err = canonicalSHA(code)
	if err != nil {
		return nil, proof, err
	}
	return out, proof, nil
}

func projectRelations(raw []byte) (json.RawMessage, error) {
	var sides map[string]json.RawMessage
	if err := decode(raw, &sides); err != nil {
		return nil, err
	}
	if len(sides) != 2 || sides["incoming"] == nil || sides["outgoing"] == nil {
		return nil, fmt.Errorf("unknown graphContext shape; refuse to omit possible code")
	}
	result := relationContext{Incoming: []relation{}, Outgoing: []relation{}}
	for _, side := range []string{"incoming", "outgoing"} {
		var entries []map[string]json.RawMessage
		if err := decode(sides[side], &entries); err != nil {
			return nil, err
		}
		relations := []relation{}
		for _, entry := range entries {
			if len(entry) != 2 || entry["node"] == nil || entry["relationship"] == nil {
				return nil, fmt.Errorf("unknown graphContext relation shape")
			}
			var n map[string]json.RawMessage
			if err := decode(entry["node"], &n); err != nil {
				return nil, err
			}
			for key := range n {
				switch key {
				case "id", "kind", "namespace", "name", "version", "description", "sourceLocations", "transformations":
				default:
					return nil, fmt.Errorf("unknown neighbor key %s; possible code cannot be omitted", key)
				}
			}
			var description string
			if value, ok := n["description"]; ok {
				if err := decode(value, &description); err != nil {
					return nil, err
				}
				if unusualCode.MatchString(description) {
					return nil, fmt.Errorf("possible raw code in neighbor description")
				}
			}
			if transformations, ok := n["transformations"]; ok {
				var inventory []map[string]json.RawMessage
				if err := decode(transformations, &inventory); err != nil {
					return nil, err
				}
				for _, operation := range inventory {
					for key, value := range operation {
						if key != "name" && key != "implementation" && key != "source" {
							return nil, fmt.Errorf("unknown neighbor operation key %s; possible code cannot be omitted", key)
						}
						if key != "source" {
							var text string
							if err := decode(value, &text); err != nil {
								return nil, err
							}
							if unusualCode.MatchString(text) {
								return nil, fmt.Errorf("possible raw code in neighbor operation")
							}
						}
					}
				}
			}
			var rel relation
			if err := decode(entry["node"], &rel.Node); err != nil {
				return nil, err
			}
			if err := decode(entry["relationship"], &rel.Relationship); err != nil {
				return nil, err
			}
			if rel.Node.ID == "" || rel.Node.Kind == "" || rel.Node.Namespace == "" || rel.Node.Name == "" || rel.Relationship == "" || len(rel.Node.Version) == 0 {
				return nil, fmt.Errorf("incomplete neighbor relation identity/version")
			}
			relations = append(relations, rel)
		}
		if side == "incoming" {
			result.Incoming = relations
		} else {
			result.Outgoing = relations
		}
	}
	encoded, err := json.Marshal(result)
	return encoded, err
}
