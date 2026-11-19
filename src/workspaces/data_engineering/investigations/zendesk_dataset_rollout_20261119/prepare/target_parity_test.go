package main

import (
	"bytes"
	"flag"
	"os"
	"path/filepath"
	"testing"

	"github.com/jeisenman/q2_bench/src/workspaces/data_engineering/investigations/zendesk_dataset_rollout_20261119/contract"
)

var parityRun = flag.String("frozen-target-parity-run", "", "Read-only opt-in comparison against all frozen target artifacts")

func TestFrozenTargetParity(t *testing.T) {
	if *parityRun == "" {
		t.Skip("explicit frozen run is required; ordinary tests use synthetic fixtures")
	}
	root, err := filepath.Abs(*parityRun)
	if err != nil {
		t.Fatal(err)
	}
	load := func(relative string) []byte {
		t.Helper()
		b, err := os.ReadFile(filepath.Join(root, relative))
		if err != nil {
			t.Fatal(err)
		}
		return b
	}
	var manifest runManifest
	if err := decode(load("manifest.json"), &manifest); err != nil {
		t.Fatal(err)
	}
	source := func(name string) []byte {
		t.Helper()
		pin, ok := manifest.Sources[name]
		if !ok {
			t.Fatalf("missing source pin %s", name)
		}
		b := load(pin.Path)
		if digest(b) != pin.SHA256 {
			t.Fatalf("source hash mismatch %s", name)
		}
		return b
	}
	graphBytes := source("graph")
	if digest(graphBytes) != expectedGraph {
		t.Fatal("frozen graph identity differs")
	}
	var graph contract.Graph
	if err := decode(graphBytes, &graph); err != nil {
		t.Fatal(err)
	}
	stageBytes := source("staged")
	var staged stagedDocument
	if err := decode(stageBytes, &staged); err != nil {
		t.Fatal(err)
	}
	requests, _, err := lines(source("requests"), func(r request) string { return r.NodeID })
	if err != nil {
		t.Fatal(err)
	}
	responses, _, err := lines(source("responses"), func(d definition) string { return d.NodeID })
	if err != nil {
		t.Fatal(err)
	}
	targets, err := selectTargets(graph, staged, requests, responses, digest(stageBytes), 553)
	if err != nil {
		t.Fatal(err)
	}
	if len(manifest.Targets) != 553 || manifest.SelectedCount != 553 {
		t.Fatal("frozen target count differs")
	}
	originals := map[string]targetRecord{}
	for _, record := range manifest.Targets {
		if _, ok := originals[record.NodeID]; ok {
			t.Fatal("duplicate frozen target")
		}
		originals[record.NodeID] = record
	}
	fields, producers, consumers, pins := 0, 0, 0, 0
	for _, target := range targets {
		original, ok := originals[target.NodeID]
		if !ok {
			t.Errorf("new selected identity %s", target.NodeID)
			continue
		}
		p := original.Files["target"]
		frozen := load(p.Path)
		if digest(frozen) != p.SHA256 {
			t.Errorf("frozen target hash differs: %s", target.NodeID)
			continue
		}
		regenerated, err := formatted(target)
		if err != nil {
			t.Fatal(err)
		}
		if !bytes.Equal(regenerated, frozen) {
			t.Errorf("target wire bytes differ: %s", target.NodeID)
		}
		fields += len(target.Columns)
		producers += len(target.Producers)
		consumers += len(target.Consumers)
		pins += len(target.Dataset.Sources)
		for _, nodes := range [][]contract.Node{target.Columns, target.Producers, target.Consumers, target.Copies} {
			for _, node := range nodes {
				pins += len(node.Sources)
			}
		}
	}
	t.Logf("Compared all %d targets byte-for-byte; columns=%d producer references=%d consumer references=%d source-pin occurrences=%d; no artifacts written", len(targets), fields, producers, consumers, pins)
}
