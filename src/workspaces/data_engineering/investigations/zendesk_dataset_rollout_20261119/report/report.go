package main

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

func report(run, output string, allowIncomplete bool, count int) error {
	if run == "" || output == "" {
		return fmt.Errorf("--run and --output are required")
	}
	root, err := filepath.Abs(run)
	if err != nil {
		return err
	}
	out, err := filepath.Abs(output)
	if err != nil {
		return err
	}
	if _, err := os.Lstat(out); err == nil {
		return fmt.Errorf("output already exists: %s", out)
	} else if !os.IsNotExist(err) {
		return err
	}
	var m manifest
	manifestBytes, err := readJSON(filepath.Join(root, "manifest.json"), &m)
	if err != nil {
		return err
	}
	effective, err := verifyManifest(root, m, count)
	if err != nil {
		return err
	}
	s := summary{Format: "zendesk-dataset-artifact-report/1", Complete: true, Selected: count, Counts: map[string]int{"changed": 0, "unchanged": 0, "failed": 0, "pending": 0, "unresolved_attempt": 0}, Model: "gpt-6-luna", EditPasses: 1, ManifestSHA: digest(manifestBytes), Pins: m, NewArticleURLs: []string{}, Cited: []citation{}, Usage: map[string]int64{}, Nodes: []nodeRow{}, CitationAttribution: "Article URLs map to supplied candidate article/chunk IDs. This is candidate membership, not exact per-claim support proof.", Limits: []string{"All definitions are offline machine drafts; none is published or SME approved.", "Artifact reconciliation does not verify semantic accuracy, source coverage, runtime behavior, freshness or full technical equivalence.", "Failed raw outputs are not parsed, accepted, repaired or revalidated.", "No source or graph writes are performed. Frozen source hashes are verified; external service state is not inspected.", "Token usage is summed separately by emitted category; overlapping categories must not be added together."}}
	if err := verifyCorpus(root, m, &s); err != nil {
		return err
	}
	staged, err := pinned(root, m.Sources["staged"])
	if err != nil {
		return err
	}
	var stage struct {
		Manifest struct {
			Repositories []sourceRepository `json:"sourceRepositories"`
		} `json:"manifest"`
	}
	if err := decode(staged, &stage); err != nil {
		return err
	}
	if len(stage.Manifest.Repositories) == 0 {
		return fmt.Errorf("staged source repository pins missing")
	}
	s.SourceRepositories = stage.Manifest.Repositories
	newURLs := map[string]bool{}
	cited := map[citation]bool{}
	for _, t := range m.Targets {
		row, usage, err := reconcileTarget(root, t, effective)
		if err != nil {
			return fmt.Errorf("%s: %w", t.NodeID, err)
		}
		s.Nodes = append(s.Nodes, row)
		s.Counts[row.Status]++
		if row.ValidationContract != "" {
			s.ReconciledInitialFailures++
		}
		if row.AuditPrepared {
			s.AuditPrepared++
		}
		if row.ModelChanged {
			s.ModelChanged++
		}
		if row.AuditCleanupChanged {
			s.AuditCleanupChanged++
		}
		if row.Status == "pending" || row.Status == "unresolved_attempt" {
			s.Complete = false
		}
		for key, n := range usage {
			s.Usage[key] += n
		}
		for _, u := range row.NewArticleURLs {
			newURLs[u] = true
		}
		for _, c := range row.Cited {
			cited[c] = true
		}
	}
	if !s.Complete && !allowIncomplete {
		return fmt.Errorf("report incomplete: %d pending and %d unresolved attempts; wait for dispatch or use --allow-incomplete", s.Counts["pending"], s.Counts["unresolved_attempt"])
	}
	s.NewArticleURLs = sortedKeys(newURLs)
	for c := range cited {
		s.Cited = append(s.Cited, c)
	}
	sort.Slice(s.Cited, func(i, j int) bool {
		a, b := s.Cited[i], s.Cited[j]
		if a.URL != b.URL {
			return a.URL < b.URL
		}
		if a.ArticleID != b.ArticleID {
			return a.ArticleID < b.ArticleID
		}
		return a.ChunkID < b.ChunkID
	})
	sort.Slice(s.Nodes, func(i, j int) bool { return s.Nodes[i].NodeID < s.Nodes[j].NodeID })
	return writeReport(root, out, s)
}

func verifyCorpus(root string, m manifest, s *summary) error {
	names := map[string]string{"manifest.json": "zendesk_manifest.json", "article-filter-policy.json": "zendesk_policy.json", "articles-normalized.json": "zendesk_articles.json", "articles-chunked.json": "zendesk_chunks.json"}
	for name, frozenName := range names {
		expected, ok := m.Corpus[name]
		if !ok || expected == "" {
			return fmt.Errorf("missing corpus pin %s", name)
		}
		b, err := os.ReadFile(filepath.Join(filepath.Dir(root), "frozen-inputs", frozenName))
		if err != nil {
			return fmt.Errorf("retained corpus verification requires sibling frozen-inputs/%s: %w", frozenName, err)
		}
		if digest(b) != expected {
			return fmt.Errorf("retained corpus hash mismatch %s", name)
		}
		if name == "manifest.json" {
			var corpus struct {
				RunID  string `json:"run_id"`
				Status string `json:"status"`
				Counts struct {
					Articles int `json:"normalized_articles"`
					Chunks   int `json:"chunks"`
				} `json:"counts"`
			}
			if err := decode(b, &corpus); err != nil {
				return err
			}
			if corpus.RunID != snapshot || corpus.Status != "success" || corpus.Counts.Articles != 396 || corpus.Counts.Chunks != 3404 {
				return fmt.Errorf("corpus snapshot/count/status mismatch")
			}
			s.Corpus.Snapshot = corpus.RunID
			s.Corpus.Articles = corpus.Counts.Articles
			s.Corpus.Chunks = corpus.Counts.Chunks
		}
	}
	s.Corpus.Verification = "All four retained corpus documents match frozen preparation hashes; successful snapshot manifest declares 396 articles and 3404 chunks. Retrieval relevance is not established by these checks."
	return nil
}
