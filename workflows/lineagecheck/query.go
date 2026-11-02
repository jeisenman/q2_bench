package lineagecheck

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/jeisenman/q2_bench/workflows/lineage"
)

// Graph projects a local snapshot into the existing lineage query contract.
func (s Snapshot) Graph() (lineage.Graph, error) {
	if err := ValidateSnapshot(s); err != nil {
		return lineage.Graph{}, err
	}
	nodes := []map[string]any{}
	edges := []map[string]any{}
	for _, d := range s.Manifest.Datasets {
		nodes = append(nodes, map[string]any{"id": d.ID, "kind": "dataset", "name": d.ID, "fields": d.Fields, "version": fmt.Sprintf("v%d.%d", d.Major, d.Minor), "sources": d.Evidence, "facets": map[string]any{}, "partition": d.Partition, "keys": d.Keys})
	}
	for _, j := range s.Manifest.Jobs {
		nodes = append(nodes, map[string]any{"id": j.ID, "kind": "job", "name": j.ID, "sources": j.Evidence, "dag": j.DAG, "transformations": j.Dependencies, "replay": j.Replay, "facets": map[string]any{}})
		add := func(kind, from, to string) {
			edges = append(edges, map[string]any{"id": kind + ":" + from + "->" + to, "kind": kind, "source": from, "target": to})
		}
		for _, in := range j.Inputs {
			add("consumes", in.Dataset, j.ID)
		}
		for _, out := range j.Outputs {
			add("produces", j.ID, out)
		}
		for _, pre := range j.After {
			add("depends_on", pre, j.ID)
		}
	}
	b, err := json.Marshal(map[string]any{"manifest": map[string]any{"graphId": s.ID, "commitSha": s.ID, "profile": s.Manifest.Profile, "repository": "qtwo_bench/local-lineage", "scope": s.Manifest.Scope, "sourceRepositories": s.Manifest.Repositories, "extractorVersion": s.Extractor, "authority": "reviewed_source_contract"}, "nodes": nodes, "edges": edges})
	if err != nil {
		return lineage.Graph{}, err
	}
	return lineage.ParseGraph(b)
}

// Latest serves the most recently published snapshot through the existing MCP.
func (s Store) Latest(ctx context.Context) (lineage.Graph, error) {
	snap, err := s.Load(ctx, "")
	if err != nil {
		return lineage.Graph{}, err
	}
	return snap.Graph()
}

// History returns newest-first verified snapshots for the active scope/profile.
func (s Store) History(ctx context.Context, limit int) ([]lineage.Graph, error) {
	if limit < 1 || limit > 101 {
		return nil, fmt.Errorf("lineage history limit must be between 1 and 101")
	}
	index, err := s.index()
	if err != nil {
		return nil, err
	}
	graphs := []lineage.Graph{}
	scope, profile := "", ""
	for _, id := range index.IDs {
		snap, err := s.Load(ctx, id)
		if err != nil {
			return nil, err
		}
		if scope == "" {
			scope = snap.Manifest.Scope
			profile = snap.Manifest.Profile
		}
		if scope != snap.Manifest.Scope || profile != snap.Manifest.Profile {
			continue
		}
		graph, err := snap.Graph()
		if err != nil {
			return nil, err
		}
		graphs = append(graphs, graph)
		if len(graphs) == limit {
			break
		}
	}
	return graphs, nil
}
