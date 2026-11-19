package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	"github.com/jeisenman/q2_bench/src/workspaces/data_engineering/investigations/zendesk_dataset_rollout_20261119/contract"
)

func identityFixture() (contract.Graph, stagedDocument, map[string]request, map[string]definition) {
	id := contract.NodeID{Namespace: "q2://test/a", Name: "punctuation[]/#.name"}
	key := "dataset:" + id.Namespace + "/" + id.Name
	d := definition{NodeID: key, Description: "Pinned processing.", BusinessContext: "Supplied meaning."}
	evidenceTarget, _ := json.Marshal(map[string]string{"id": key, "kind": "dataset", "namespace": id.Namespace, "name": id.Name})
	req := request{NodeID: key, RequestID: "request", BundleID: "bundle", LineageNodeKey: "opaque", EvidenceSHA: "evidence", Evidence: map[string]json.RawMessage{"lineageNodeKey": json.RawMessage(`"opaque"`), "targetNode": evidenceTarget}}
	s := stagedDocument{Nodes: []stagedNode{{ID: key, Kind: "dataset", Namespace: id.Namespace, Name: id.Name}}}
	s.Manifest.Semantic.Generation = expectedGeneration
	s.Manifest.Semantic.RequestsSHA = expectedRequests
	s.Manifest.Semantic.Bundle = "bundle"
	s.Manifest.Semantic.Count = 1
	s.Nodes[0].Facets.Meaning.Entries = []semanticEntry{{Key: "opaque", Description: d.Description, BusinessContext: d.BusinessContext, EvidenceSHA: "evidence"}}
	n := contract.Node{ID: id, Dataset: &contract.Dataset{}, Sources: []contract.Source{{Repository: "repo", Path: "file.go", Commit: "commit", SnapshotID: "snapshot"}}}
	n.Facets.Meaning.Machine = &contract.MachineMeaning{GenerationID: expectedGeneration, Description: d.Description, BusinessContext: d.BusinessContext, EvidenceSHA256: "evidence"}
	return contract.Graph{Nodes: []contract.Node{n}}, s, map[string]request{key: req}, map[string]definition{key: d}
}

func TestIdentityExactSuccessAndFailure(t *testing.T) {
	g, s, r, d := identityFixture()
	targets, err := selectTargets(g, s, r, d, "snapshot", 1)
	if err != nil {
		t.Fatal(err)
	}
	if len(targets) != 1 || targets[0].NodeID != s.Nodes[0].ID || targets[0].CopiesStatus != "unavailable" {
		t.Fatal("identity or missing-copy evidence changed")
	}
	for _, test := range []struct {
		name   string
		change func(*contract.Graph, *stagedDocument, map[string]request, map[string]definition)
	}{
		{"duplicate", func(g *contract.Graph, _ *stagedDocument, _ map[string]request, _ map[string]definition) {
			g.Nodes = append(g.Nodes, g.Nodes[0])
		}},
		{"snapshot", func(g *contract.Graph, _ *stagedDocument, _ map[string]request, _ map[string]definition) {
			g.Nodes[0].Sources[0].SnapshotID = "other"
		}},
		{"facet", func(_ *contract.Graph, s *stagedDocument, _ map[string]request, _ map[string]definition) {
			s.Nodes[0].Facets.Meaning.Entries[0].Key = "wrong"
		}},
		{"missing response", func(_ *contract.Graph, _ *stagedDocument, _ map[string]request, d map[string]definition) {
			for k := range d {
				delete(d, k)
			}
		}},
	} {
		t.Run(test.name, func(t *testing.T) {
			g, s, r, d := identityFixture()
			test.change(&g, &s, r, d)
			if _, err := selectTargets(g, s, r, d, "snapshot", 1); err == nil {
				t.Fatal("invalid identity accepted")
			}
		})
	}
	if _, err := selectTargets(g, s, r, d, "snapshot", 553); err == nil {
		t.Fatal("wrong dataset count accepted")
	}
}

func TestCleanupExactAuditAndCaveats(t *testing.T) {
	regression := "Candidate records are joined to accounts. Zendesk evidence audit: no candidate chunks supplied. Status: no_support."
	regressionOut, _, regressionErr := cleanText("description", regression)
	if regressionErr != nil || regressionOut != "Candidate records are joined to accounts." {
		t.Fatalf("technical candidate sentence changed: %q %v", regressionOut, regressionErr)
	}
	original := "Processing uses a 30-day window. Zendesk evidence audit: status no_support; no candidate chunks were supplied. Runtime freshness is not established."
	out, removals, err := cleanText("description", original)
	if err != nil {
		t.Fatal(err)
	}
	if out != "Processing uses a 30-day window. Runtime freshness is not established." || len(removals) != 1 {
		t.Fatalf("unexpected cleanup: %q %+v", out, removals)
	}
	for _, r := range removals {
		if original[r.Start:r.End] != r.Text {
			t.Fatal("removed span differs")
		}
	}
	clean := "Keep the [source](https://example.com/source). No runtime execution is established."
	result, changes, err := cleanText("description", clean)
	if err != nil || result != clean || len(changes) != 0 {
		t.Fatal("clean technical text changed")
	}
	for _, unsafe := range []string{"Zendesk audit: no_support; runtime freshness is not established.", "Zendesk evidence audit: see https://example.com/source.", "Technical description and Zendesk status no_support share one sentence.", "Zendesk status: no_support."} {
		if _, _, err := cleanText("description", unsafe); err == nil {
			t.Fatalf("unsafe text accepted: %s", unsafe)
		}
	}
}

func TestRetrievalRelevantNoneAndOriginal(t *testing.T) {
	a := chunk{ID: "deposit", ArticleID: 1, Title: "Deposit Balance", Section: "Deposit balances", Text: "Deposit balances describe deposit account amounts."}
	b := chunk{ID: "liquidity", ArticleID: 2, Title: "Liquidity Curve", Section: "Funding", Text: "Liquidity curve funding rates."}
	c := corpusData{chunks: []chunk{a, b}, byID: map[string]chunk{a.ID: a, b.ID: b}}
	target := target{Dataset: contract.Node{ID: contract.NodeID{Name: "DepositBalances"}}}
	selected, record := retrieve(target, definition{}, c, nil)
	if len(selected) != 1 || selected[0].ID != "deposit" || len(record.Candidates[0].Terms) == 0 {
		t.Fatalf("irrelevant retrieval: %+v", record)
	}
	target.Dataset.ID.Name = "UnmatchableZyzq"
	selected, _ = retrieve(target, definition{}, c, nil)
	if len(selected) != 0 {
		t.Fatal("no-match query invented candidates")
	}
	selected, record = retrieve(target, definition{}, c, []chunk{b})
	if len(selected) != 1 || !record.Candidates[0].Original {
		t.Fatal("verified original evidence lost")
	}
	if !reflect.DeepEqual(tokens("deposit_balance AccountId"), []string{"deposit", "balance", "account"}) {
		t.Fatalf("identifier tokens: %v", tokens("deposit_balance AccountId"))
	}
}

func TestBoundsAndDuplicateRows(t *testing.T) {
	if err := validateInputBound([]byte("small"), nil); err != nil {
		t.Fatal(err)
	}
	if err := validateInputBound(make([]byte, maximumEstimatedTokens*3), nil); err != nil {
		t.Fatal("exact token estimate bound rejected", err)
	}
	if err := validateInputBound(make([]byte, maximumEstimatedTokens*3+1), nil); err == nil {
		t.Fatal("token bound ignored")
	}
	if err := validateInputBound(make([]byte, maximumInputBytes+1), nil); err == nil {
		t.Fatal("byte bound ignored")
	}
	if _, _, err := lines([]byte("{\"node_id\":\"a\"}\n{\"node_id\":\"a\"}\n"), func(d definition) string { return d.NodeID }); err == nil {
		t.Fatal("duplicate row accepted")
	}
}

func writeJSON(t *testing.T, path string, value any) {
	t.Helper()
	b, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, b, 0600); err != nil {
		t.Fatal(err)
	}
}

func corpusFixture(t *testing.T) string {
	t.Helper()
	root := t.TempDir()
	policy := []byte("synthetic policy")
	if err := os.WriteFile(filepath.Join(root, "article-filter-policy.json"), policy, 0600); err != nil {
		t.Fatal(err)
	}
	a := article{ID: 1, ParentID: "1-en-us", Title: "Deposits", URL: "https://support.precisionlender.com/hc/en-us/articles/1-Deposits", Created: "2020-01-01T00:00:00Z", Updated: "2026-01-01T00:00:00Z"}
	ch := chunk{ID: "1-en-us-overview", ArticleID: 1, ParentID: a.ParentID, Title: a.Title, URL: a.URL, Created: a.Created, Updated: a.Updated, Text: "Deposit balance."}
	writeJSON(t, filepath.Join(root, "manifest.json"), map[string]any{"run_id": expectedCorpus, "status": "success", "config": map[string]any{"filter_policy_sha256": digest(policy)}, "counts": map[string]any{"normalized_articles": 1, "chunks": 1}})
	writeJSON(t, filepath.Join(root, "articles-normalized.json"), map[string]any{"articles": []article{a}, "source": map[string]any{"filterPolicy": map[string]any{"sha256": digest(policy)}}})
	writeJSON(t, filepath.Join(root, "articles-chunked.json"), map[string]any{"chunks": []chunk{ch}, "counts": map[string]any{"articles": 1, "chunks": 1}})
	return root
}

func TestCorpusIntegrity(t *testing.T) {
	root := corpusFixture(t)
	c, err := loadCorpusPolicy(root, 1, 1, digest([]byte("synthetic policy")))
	if err != nil {
		t.Fatal(err)
	}
	original, _ := json.Marshal(map[string]any{"snapshotId": expectedCorpus, "chunks": c.chunks})
	if _, err := originalChunks(original, c); err != nil {
		t.Fatal(err)
	}
	c.chunks[0].URL = "https://invalid.example"
	writeJSON(t, filepath.Join(root, "articles-chunked.json"), map[string]any{"chunks": c.chunks, "counts": map[string]any{"articles": 1, "chunks": 1}})
	if _, err := loadCorpusPolicy(root, 1, 1, digest([]byte("synthetic policy"))); err == nil || !strings.Contains(err.Error(), "association") {
		t.Fatalf("altered URL accepted: %v", err)
	}
}
