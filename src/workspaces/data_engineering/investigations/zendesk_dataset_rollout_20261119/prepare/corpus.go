package main

import (
	"encoding/json"
	"fmt"
	"path/filepath"
	"strings"
	"time"
)

type article struct {
	ParentID string `json:"parentId"`
	ID       int64  `json:"articleId"`
	Title    string `json:"title"`
	URL      string `json:"url"`
	Updated  string `json:"updatedAt"`
	Created  string `json:"createdAt"`
}
type chunk struct {
	ID           string `json:"chunkId"`
	ParentID     string `json:"parentId"`
	ArticleID    int64  `json:"articleId"`
	Title        string `json:"title"`
	Section      string `json:"section"`
	SectionSlug  string `json:"sectionSlug"`
	SectionIndex int    `json:"sectionIndex"`
	ChunkIndex   int    `json:"chunkIndex"`
	ChunkCount   int    `json:"chunkCount"`
	URL          string `json:"url"`
	Updated      string `json:"updatedAt"`
	Created      string `json:"createdAt"`
	Text         string `json:"chunk"`
}
type corpusData struct {
	articles map[int64]article
	chunks   []chunk
	byID     map[string]chunk
	hashes   map[string]string
	index    *searchIndex
}

func loadCorpus(root string, articleCount, chunkCount int) (corpusData, error) {
	return loadCorpusPolicy(root, articleCount, chunkCount, expectedPolicy)
}

func loadCorpusPolicy(root string, articleCount, chunkCount int, policySHA string) (corpusData, error) {
	c := corpusData{articles: map[int64]article{}, byID: map[string]chunk{}, hashes: map[string]string{}}
	files := map[string][]byte{}
	for _, name := range []string{"manifest.json", "article-filter-policy.json", "articles-normalized.json", "articles-chunked.json"} {
		b, err := read(filepath.Join(root, name))
		if err != nil {
			return c, err
		}
		files[name] = b
		c.hashes[name] = digest(b)
	}
	var m struct {
		RunID  string `json:"run_id"`
		Status string `json:"status"`
		Config struct {
			Policy string `json:"filter_policy_sha256"`
		} `json:"config"`
		Counts struct {
			Articles int `json:"normalized_articles"`
			Chunks   int `json:"chunks"`
		} `json:"counts"`
	}
	if err := decode(files["manifest.json"], &m); err != nil {
		return c, err
	}
	if m.RunID != expectedCorpus || m.Status != "success" || m.Config.Policy != policySHA || c.hashes["article-filter-policy.json"] != policySHA || m.Counts.Articles != articleCount || m.Counts.Chunks != chunkCount {
		return c, fmt.Errorf("corpus manifest/count/policy pin mismatch")
	}
	var normalized struct {
		Articles []article `json:"articles"`
		Source   struct {
			Filter struct {
				SHA string `json:"sha256"`
			} `json:"filterPolicy"`
		} `json:"source"`
	}
	var chunked struct {
		Chunks []chunk `json:"chunks"`
		Counts struct {
			Articles int `json:"articles"`
			Chunks   int `json:"chunks"`
		} `json:"counts"`
	}
	if err := decode(files["articles-normalized.json"], &normalized); err != nil {
		return c, err
	}
	if err := decode(files["articles-chunked.json"], &chunked); err != nil {
		return c, err
	}
	if len(normalized.Articles) != articleCount || len(chunked.Chunks) != chunkCount || chunked.Counts.Articles != articleCount || chunked.Counts.Chunks != chunkCount || normalized.Source.Filter.SHA != policySHA {
		return c, fmt.Errorf("corpus document counts or normalized policy mismatch")
	}
	parents := map[string]bool{}
	for _, a := range normalized.Articles {
		if _, ok := c.articles[a.ID]; ok || a.ID <= 0 || a.ParentID == "" || parents[a.ParentID] || !strings.HasPrefix(a.URL, "https://support.precisionlender.com/hc/en-us/articles/") || a.Title == "" {
			return c, fmt.Errorf("invalid/duplicate normalized article %d", a.ID)
		}
		c.articles[a.ID] = a
		parents[a.ParentID] = true
	}
	for _, ch := range chunked.Chunks {
		a, ok := c.articles[ch.ArticleID]
		_, duplicate := c.byID[ch.ID]
		if !ok || duplicate || ch.ID == "" || ch.ParentID != a.ParentID || ch.URL != a.URL || ch.Title != a.Title || ch.Created != a.Created || ch.Updated != a.Updated || strings.TrimSpace(ch.Text) == "" {
			return c, fmt.Errorf("chunk association/content mismatch %s", ch.ID)
		}
		for _, date := range []string{ch.Created, ch.Updated} {
			if _, err := time.Parse(time.RFC3339, date); err != nil {
				return c, fmt.Errorf("invalid chunk date %s", ch.ID)
			}
		}
		c.chunks = append(c.chunks, ch)
		c.byID[ch.ID] = ch
	}
	c.index = buildIndex(c.chunks)
	return c, nil
}

func originalChunks(raw json.RawMessage, c corpusData) ([]chunk, error) {
	if len(raw) == 0 {
		return nil, nil
	}
	var context struct {
		Snapshot string  `json:"snapshotId"`
		Chunks   []chunk `json:"chunks"`
	}
	if err := decode(raw, &context); err != nil {
		return nil, err
	}
	if context.Snapshot != expectedCorpus {
		return nil, fmt.Errorf("original request Zendesk snapshot mismatch")
	}
	out := []chunk{}
	for _, supplied := range context.Chunks {
		canonical, ok := c.byID[supplied.ID]
		if !ok || supplied != canonical {
			return nil, fmt.Errorf("original request chunk differs from corpus %s", supplied.ID)
		}
		out = append(out, canonical)
	}
	return out, nil
}
