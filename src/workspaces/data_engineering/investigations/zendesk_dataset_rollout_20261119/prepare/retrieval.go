package main

import (
	"math"
	"regexp"
	"sort"
	"strings"
)

var camelBoundary = regexp.MustCompile(`([a-z0-9])([A-Z])`)
var wordPattern = regexp.MustCompile(`[a-z][a-z0-9]+`)
var stopwords = func() map[string]bool {
	m := map[string]bool{}
	for _, w := range strings.Fields("the and for with from this that these those into its are was were has have had not does only supplied evidence dataset datasets node nodes job jobs data source sources field fields column columns table file csv parquet output input transform transforms transformation transformations code context graph lineage q2 di pipeline pipelines main l3 task group tg get build report reports schema count status none support zendesk candidate chunk chunks documentation snapshot no unknown technical implementation implemented business purpose consumer available shown listed named represents specific establishes establish processing read write record records metadata path location locations runtime execution current version name names method function class dataframe precisionlender radar notebook notebooks datamart derived pl true false null string select join filter produces consumes") {
		m[w] = true
	}
	return m
}()

func tokens(text string) []string {
	text = camelBoundary.ReplaceAllString(text, "$1 $2")
	words := wordPattern.FindAllString(strings.ToLower(text), -1)
	out := []string{}
	for _, word := range words {
		if len(word) > 4 && strings.HasSuffix(word, "s") && !strings.HasSuffix(word, "ss") {
			word = strings.TrimSuffix(word, "s")
		}
		if !stopwords[word] && len(word) > 2 {
			out = append(out, word)
		}
	}
	return out
}
func termSet(text string) map[string]bool {
	out := map[string]bool{}
	for _, t := range tokens(text) {
		out[t] = true
	}
	return out
}

type scoredChunk struct {
	ChunkID   string   `json:"chunk_id"`
	ArticleID int64    `json:"article_id"`
	Score     float64  `json:"score"`
	Terms     []string `json:"matched_terms"`
	Original  bool     `json:"original_request"`
}
type retrievalRecord struct {
	Contract   string        `json:"contract"`
	QueryTerms []string      `json:"query_terms"`
	Candidates []scoredChunk `json:"candidates"`
	ArticleIDs []int64       `json:"article_ids"`
	ChunkIDs   []string      `json:"chunk_ids"`
}

func retrieve(t target, d definition, c corpusData, original []chunk) ([]chunk, retrievalRecord) {
	identity := t.Dataset.ID.Name
	for _, j := range t.Producers {
		identity += " " + j.ID.Name
	}
	for _, j := range t.Consumers {
		identity += " " + j.ID.Name
	}
	anchors := termSet(identity)
	query := termSet(identity + " " + d.Description + " " + d.BusinessContext)
	terms := []string{}
	for term := range query {
		terms = append(terms, term)
	}
	sort.Strings(terms)
	record := retrievalRecord{Contract: "bm25-title-heading-v1;k1=1.2;b=0.75;title=3;heading=2;max_articles=4;max_chunks=12;identity-or-two-title-terms", QueryTerms: terms, Candidates: []scoredChunk{}, ArticleIDs: []int64{}, ChunkIDs: []string{}}
	index := c.index
	if index == nil {
		index = buildIndex(c.chunks)
	}
	docs, lengths, df, avg := index.docs, index.lengths, index.df, index.avg
	if avg == 0 {
		return []chunk{}, record
	}
	ranked := []scoredChunk{}
	for i, ch := range c.chunks {
		heading := index.headings[i]
		anchorHits, titleHits := 0, 0
		for term := range query {
			if heading[term] {
				titleHits++
				if anchors[term] {
					anchorHits++
				}
			}
		}
		if anchorHits == 0 && titleHits < 2 {
			continue
		}
		score := 0.0
		matched := []string{}
		for _, term := range terms {
			tf := float64(docs[i][term])
			if tf == 0 {
				continue
			}
			idf := math.Log(1 + (float64(len(docs)-df[term])+0.5)/(float64(df[term])+0.5))
			weight := 1.0
			if anchors[term] {
				weight = 2
			}
			score += weight * idf * (tf * 2.2) / (tf + 1.2*(0.25+0.75*float64(lengths[i])/avg))
			matched = append(matched, term)
		}
		if score > 0 {
			ranked = append(ranked, scoredChunk{ChunkID: ch.ID, ArticleID: ch.ArticleID, Score: math.Round(score*1e6) / 1e6, Terms: matched})
		}
	}
	sort.Slice(ranked, func(i, j int) bool {
		if ranked[i].Score == ranked[j].Score {
			return ranked[i].ChunkID < ranked[j].ChunkID
		}
		return ranked[i].Score > ranked[j].Score
	})
	selected := []chunk{}
	articles := map[int64]bool{}
	seen := map[string]bool{}
	perArticle := map[int64]int{}
	add := func(ch chunk, score scoredChunk) {
		if seen[ch.ID] {
			return
		}
		selected = append(selected, ch)
		seen[ch.ID] = true
		articles[ch.ArticleID] = true
		perArticle[ch.ArticleID]++
		record.Candidates = append(record.Candidates, score)
		record.ChunkIDs = append(record.ChunkIDs, ch.ID)
	}
	for _, ch := range original {
		add(ch, scoredChunk{ChunkID: ch.ID, ArticleID: ch.ArticleID, Terms: []string{}, Original: true})
	}
	for _, score := range ranked {
		if len(selected) >= 12 {
			break
		}
		if (!articles[score.ArticleID] && len(articles) >= 4) || perArticle[score.ArticleID] >= 3 {
			continue
		}
		add(c.byID[score.ChunkID], score)
	}
	for articleID := range articles {
		record.ArticleIDs = append(record.ArticleIDs, articleID)
	}
	sort.Slice(record.ArticleIDs, func(i, j int) bool { return record.ArticleIDs[i] < record.ArticleIDs[j] })
	return selected, record
}

type searchIndex struct {
	docs     []map[string]int
	lengths  []int
	headings []map[string]bool
	df       map[string]int
	avg      float64
}

func buildIndex(chunks []chunk) *searchIndex {
	docs := make([]map[string]int, len(chunks))
	lengths := make([]int, len(chunks))
	df := map[string]int{}
	avg := 0.0
	for i, ch := range chunks {
		docs[i] = map[string]int{}
		for _, term := range tokens(ch.Title + " " + ch.Title + " " + ch.Title + " " + ch.Section + " " + ch.Section + " " + ch.Text) {
			docs[i][term]++
			lengths[i]++
		}
		for term := range docs[i] {
			df[term]++
		}
		avg += float64(lengths[i])
	}
	if len(docs) > 0 {
		avg /= float64(len(docs))
	}
	headings := make([]map[string]bool, len(chunks))
	for i, ch := range chunks {
		headings[i] = termSet(ch.Title + " " + ch.Section)
	}
	return &searchIndex{docs: docs, lengths: lengths, df: df, avg: avg, headings: headings}
}
