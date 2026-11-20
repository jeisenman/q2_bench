package main

import (
	"bytes"
	"encoding/json"
	"reflect"
	"testing"

	"github.com/jeisenman/q2_bench/src/workspaces/data_engineering/investigations/zendesk_dataset_rollout_20261119/contract"
)

func TestContextProjectionPreservesCodeTargetAndAllRelations(t *testing.T) {
	graph := json.RawMessage(`{"incoming":[{"node":{"id":"job:test/a","kind":"job","namespace":"test","name":"a","version":null,"description":"Declared input.","sourceLocations":[{"line":1,"path":"a.go"}],"transformations":[{"name":"a","implementation":"pkg.A","source":{"line":1,"path":"a.go"}}]},"relationship":"produces"}],"outgoing":[{"node":{"id":"job:test/b","kind":"job","namespace":"test","name":"b","version":"v2","description":"Declared output.","sourceLocations":[],"transformations":[]},"relationship":"consumes"},{"node":{"id":"dataset:test/c","kind":"dataset","namespace":"test","name":"c","version":null},"relationship":"depends_on"}]}`)
	code := json.RawMessage(`{ "sourceLocations": [{"path":"a.go","line":1}], "transformationCount":1,"transformations":[{"source":"x","snippet":"return rows.Where(active)","operations":["filter"]}] }`)
	target := json.RawMessage(`{"fields":[{"name":"x","type":"decimal","nullable":false}],"locations":[{"resource":"ADLS","pathConvention":"{client}/x"}],"attributes":{"units":"USD"},"transformations":[{"source":"x"}],"context":"30-day window"}`)
	evidence := map[string]json.RawMessage{"graphContext": graph, "codeContext": code, "targetNode": target, "zendeskContext": json.RawMessage(`{}`)}
	projected, proof, err := projectTechnical(evidence, fileRecord{Path: "target.json", SHA256: "target-pin"}, fileRecord{Path: "original-request.json", SHA256: "request-pin"})
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(projected["codeContext"], code) || !bytes.Equal(projected["targetNode"], target) {
		t.Fatal("target source facts or code changed")
	}
	if proof.CodeSourceRawSHA != digest(code) || proof.CodeProjectedRawSHA != digest(code) || proof.Contract.SHA256 != contextPolicySHA || digest(contextPolicy) != contextPolicySHA {
		t.Fatal("projection/code pin changed")
	}
	var original relationContext
	var result relationContext
	if err := decode(graph, &original); err != nil {
		t.Fatal(err)
	}
	if err := decode(projected["graphContext"], &result); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(original, result) {
		t.Fatalf("relation IDs/kinds/versions changed: %+v %+v", original, result)
	}
	if bytes.Contains(projected["graphContext"], []byte("sourceLocations")) || bytes.Contains(projected["graphContext"], []byte("description")) {
		t.Fatal("neighbor inventory was not projected")
	}
	if proof.OriginalRequest.SHA256 != "request-pin" || proof.FullTarget.SHA256 != "target-pin" || len(proof.OmittedNeighborKeys) != 3 {
		t.Fatal("full evidence references missing")
	}
	if _, ok := projected["zendeskContext"]; ok {
		t.Fatal("old Zendesk context retained")
	}
}

func TestThinTargetPreservesSchemaSourcesAndJobIdentity(t *testing.T) {
	source := contract.Source{Repository: "repo", Commit: "commit", SnapshotID: "snapshot", Path: "file.go", SHA256: "digest"}
	field := contract.Node{ID: contract.NodeID{Namespace: "test", Name: "dataset", Column: "amount"}, Column: &contract.Column{Type: "decimal", Nullable: false}}
	job := contract.Node{ID: contract.NodeID{Namespace: "test", Name: "job"}, Job: &contract.Job{DAG: "dag"}, Sources: []contract.Source{source}}
	full := target{NodeID: "dataset:test/dataset", Dataset: contract.Node{ID: contract.NodeID{Namespace: "test", Name: "dataset"}, Sources: []contract.Source{source}}, Columns: []contract.Node{field}, Producers: []contract.Node{job}, Consumers: []contract.Node{job}}
	projected := thinTarget(full)
	if projected.NodeID != full.NodeID || projected.Columns[0].ID != field.ID || projected.Columns[0].Type != "decimal" || projected.Columns[0].Nullable || projected.Producers[0].ID != job.ID || projected.Producers[0].DAG != "dag" {
		t.Fatal("schema or job identity changed")
	}
	location := projected.SourcePool.Locations[projected.Sources[0]]
	restored := projected.SourcePool.Pins[location.Pin]
	restored.Path = location.Path
	restored.SHA256 = location.SHA256
	if restored != source || len(projected.SourcePool.Pins) != 1 || len(projected.SourcePool.Locations) != 1 || !reflect.DeepEqual(projected.Producers[0].Sources, projected.Consumers[0].Sources) {
		t.Fatal("source facts lost or duplicate pool entries")
	}
}

func TestNeighborCodeCannotBeOmitted(t *testing.T) {
	for _, raw := range []string{`{"incoming":[],"outgoing":[],"code":"return rows"}`, `{"incoming":[{"node":{"code":"return rows"},"relationship":"consumes"}],"outgoing":[]}`, "{\"incoming\":[{\"node\":{\"description\":\"```python\"},\"relationship\":\"consumes\"}],\"outgoing\":[]}"} {
		if _, err := projectRelations([]byte(raw)); err == nil {
			t.Fatalf("possible raw code omitted: %s", raw)
		}
	}
}
