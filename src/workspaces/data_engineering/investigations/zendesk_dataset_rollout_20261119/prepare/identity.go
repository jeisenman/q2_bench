package main

import (
	"encoding/json"
	"fmt"
	"sort"

	"github.com/jeisenman/q2_bench/src/workspaces/data_engineering/investigations/zendesk_dataset_rollout_20261119/contract"
)

type request struct {
	NodeID         string                     `json:"nodeId"`
	BundleID       string                     `json:"bundleId"`
	RequestID      string                     `json:"requestId"`
	LineageNodeKey string                     `json:"lineageNodeKey"`
	EvidenceSHA    string                     `json:"evidenceSha256"`
	Evidence       map[string]json.RawMessage `json:"evidence"`
}
type definition struct {
	BusinessContext string `json:"business_context"`
	Description     string `json:"description"`
	NodeID          string `json:"node_id"`
}
type semanticEntry struct {
	Key             string `json:"lineageNodeKey"`
	Description     string `json:"description"`
	BusinessContext string `json:"businessContext"`
	EvidenceSHA     string `json:"evidenceSha256"`
}
type stagedNode struct {
	ID        string `json:"id"`
	Kind      string `json:"kind"`
	Namespace string `json:"namespace"`
	Name      string `json:"name"`
	Sources   []struct {
		Path string `json:"path"`
	} `json:"sources"`
	Facets struct {
		Meaning struct {
			Entries []semanticEntry `json:"entries"`
		} `json:"q2_semanticMeaning"`
	} `json:"facets"`
}
type stagedDocument struct {
	Nodes    []stagedNode `json:"nodes"`
	Manifest struct {
		Repositories []struct {
			Repository string `json:"repository"`
			Commit     string `json:"commitSha"`
		} `json:"sourceRepositories"`
		Semantic struct {
			Generation  string `json:"generationId"`
			Bundle      string `json:"bundleId"`
			RequestsSHA string `json:"requestsSha256"`
			Count       int    `json:"requestCount"`
		} `json:"semanticLayer"`
	} `json:"manifest"`
}
type target struct {
	NodeID       string          `json:"node_id"`
	Kind         string          `json:"kind"`
	Scope        string          `json:"scope"`
	Generation   string          `json:"generation_id"`
	Bundle       string          `json:"bundle_id"`
	Key          string          `json:"lineage_node_key"`
	Dataset      contract.Node   `json:"dataset"`
	Columns      []contract.Node `json:"columns"`
	Producers    []contract.Node `json:"producers"`
	Consumers    []contract.Node `json:"consumers"`
	Copies       []contract.Node `json:"copies"`
	CopiesStatus string          `json:"copies_status"`
}

func selectTargets(graph contract.Graph, staged stagedDocument, requests map[string]request, responses map[string]definition, stagedSHA string, count int) ([]target, error) {
	if staged.Manifest.Semantic.Generation != expectedGeneration || staged.Manifest.Semantic.RequestsSHA != expectedRequests {
		return nil, fmt.Errorf("staged generation or published request digest does not match frozen contract")
	}
	raw := map[string]stagedNode{}
	for _, n := range staged.Nodes {
		if _, ok := raw[n.ID]; ok {
			return nil, fmt.Errorf("duplicate staged node %s", n.ID)
		}
		raw[n.ID] = n
	}
	if len(requests) != staged.Manifest.Semantic.Count || len(responses) != len(requests) || len(raw) != len(requests) {
		return nil, fmt.Errorf("published graph/request/response coverage differs")
	}
	for id, n := range raw {
		r, ok := requests[id]
		d, found := responses[id]
		if !ok || !found || r.NodeID != id || d.NodeID != id || r.BundleID != staged.Manifest.Semantic.Bundle || n.ID != n.Kind+":"+n.Namespace+"/"+n.Name {
			return nil, fmt.Errorf("published identity mismatch %s", id)
		}
		if err := validateRequestEvidence(r, n); err != nil {
			return nil, err
		}
	}
	nodes := map[contract.NodeID]contract.Node{}
	for _, n := range graph.Nodes {
		if err := n.ID.Validate(); err != nil {
			return nil, err
		}
		if _, ok := nodes[n.ID]; ok {
			return nil, fmt.Errorf("duplicate frozen identity %s", n.ID.String())
		}
		nodes[n.ID] = n
	}
	result := []target{}
	for _, n := range graph.Nodes {
		if n.Dataset == nil {
			continue
		}
		if n.ID.Column != "" {
			return nil, fmt.Errorf("dataset has column identity")
		}
		id := "dataset:" + n.ID.Namespace + "/" + n.ID.Name
		r, ok := requests[id]
		d, found := responses[id]
		s, present := raw[id]
		if !ok || !found || !present || s.Kind != "dataset" || s.Namespace != n.ID.Namespace || s.Name != n.ID.Name {
			return nil, fmt.Errorf("dataset lacks exact published identity %s", id)
		}
		if len(s.Facets.Meaning.Entries) != 1 {
			return nil, fmt.Errorf("dataset has ambiguous semantic entries %s", id)
		}
		e := s.Facets.Meaning.Entries[0]
		m := n.Facets.Meaning.Machine
		if r.LineageNodeKey == "" || e.Key != r.LineageNodeKey || e.Description != d.Description || e.BusinessContext != d.BusinessContext || e.EvidenceSHA != r.EvidenceSHA || m == nil || m.GenerationID != expectedGeneration || m.Description != d.Description || m.BusinessContext != d.BusinessContext || m.EvidenceSHA256 != r.EvidenceSHA {
			return nil, fmt.Errorf("semantic evidence mismatch %s", id)
		}
		if len(n.Sources) == 0 {
			return nil, fmt.Errorf("dataset lacks source snapshot %s", id)
		}
		for _, pin := range n.Sources {
			if pin.SnapshotID != stagedSHA || pin.Commit == "" || pin.Repository == "" || pin.Path == "" {
				return nil, fmt.Errorf("source pin mismatch %s", id)
			}
		}
		t := target{NodeID: id, Kind: "dataset", Scope: "Frozen RA to DI-Pipelines dataset identity; related products and jobs are separate evidence.", Generation: expectedGeneration, Bundle: r.BundleID, Key: r.LineageNodeKey, Dataset: n, Columns: []contract.Node{}, Producers: []contract.Node{}, Consumers: []contract.Node{}, Copies: []contract.Node{}, CopiesStatus: "unavailable"}
		seen := map[string]bool{}
		for _, edge := range graph.Edges {
			from, fromOK := nodes[edge.Source]
			to, toOK := nodes[edge.Target]
			if !fromOK || !toOK {
				return nil, fmt.Errorf("frozen edge has missing endpoint")
			}
			key := edge.Kind + ":" + edge.Source.String() + ":" + edge.Target.String()
			if seen[key] {
				continue
			}
			seen[key] = true
			if edge.Kind == "contains" && edge.Source == n.ID && to.Column != nil {
				t.Columns = append(t.Columns, to)
			}
			if edge.Kind == "produces" && edge.Target == n.ID && from.Job != nil {
				t.Producers = append(t.Producers, from)
			}
			if edge.Kind == "consumes" && edge.Source == n.ID && to.Job != nil {
				t.Consumers = append(t.Consumers, to)
			}
		}
		result = append(result, t)
	}
	if len(result) != count {
		return nil, fmt.Errorf("expected exactly %d unique datasets; got %d", count, len(result))
	}
	sort.Slice(result, func(i, j int) bool { return result[i].NodeID < result[j].NodeID })
	return result, nil
}

func validateRequestEvidence(r request, n stagedNode) error {
	if r.RequestID == "" || r.EvidenceSHA == "" || r.LineageNodeKey == "" {
		return fmt.Errorf("incomplete published request %s", r.NodeID)
	}
	var id string
	if err := decode(r.Evidence["lineageNodeKey"], &id); err != nil || id != r.LineageNodeKey {
		return fmt.Errorf("request evidence key mismatch %s", r.NodeID)
	}
	var target struct {
		ID        string `json:"id"`
		Kind      string `json:"kind"`
		Namespace string `json:"namespace"`
		Name      string `json:"name"`
	}
	if err := decode(r.Evidence["targetNode"], &target); err != nil || target.ID != n.ID || target.Kind != n.Kind || target.Namespace != n.Namespace || target.Name != n.Name {
		return fmt.Errorf("request target evidence identity mismatch %s", r.NodeID)
	}
	return nil
}
