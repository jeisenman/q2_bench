package main

import (
	"fmt"
	"regexp"
	"sort"
	"strings"
)

var urlPattern = regexp.MustCompile(`https?://[^\s<>\)\]"` + "`" + `]+`)

func urls(d definition) map[string]bool {
	out := map[string]bool{}
	for _, u := range urlPattern.FindAllString(d.Description+"\n"+d.BusinessContext, -1) {
		out[strings.TrimRight(u, ".,;:")] = true
	}
	return out
}
func sortedKeys(m map[string]bool) []string {
	out := []string{}
	for k := range m {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}
func equalStrings(a, b []string) bool {
	x := append([]string{}, a...)
	y := append([]string{}, b...)
	sort.Strings(x)
	sort.Strings(y)
	return fmt.Sprint(x) == fmt.Sprint(y)
}
func verifyCitations(payload input, prepared, final definition, r result) error {
	candidates := map[citation]bool{}
	allowed := urls(prepared)
	articleURLs := map[string]bool{}
	for _, ch := range payload.Zendesk.Chunks {
		c := citation{ArticleID: ch.ArticleID.String(), ChunkID: ch.ID, URL: ch.URL}
		if c.ArticleID == "" || c.ChunkID == "" || c.URL == "" {
			return fmt.Errorf("incomplete candidate citation")
		}
		candidates[c] = true
		allowed[c.URL] = true
		articleURLs[c.URL] = true
	}
	finalURLs := urls(final)
	for original := range urls(prepared) {
		if !finalURLs[original] {
			return fmt.Errorf("emitted draft lost an existing source citation: %s", original)
		}
	}
	for u := range finalURLs {
		if !allowed[u] {
			return fmt.Errorf("emitted draft URL is outside supplied originals: %s", u)
		}
	}
	cited := map[citation]bool{}
	for _, c := range r.Cited {
		if !candidates[c] || !finalURLs[c.URL] || cited[c] {
			return fmt.Errorf("reported citation does not map exactly to a used candidate URL/chunk: %s", c.ChunkID)
		}
		cited[c] = true
	}
	// The executor reports every supplied candidate chunk sharing a used article URL.
	for c := range candidates {
		if finalURLs[c.URL] && !cited[c] {
			return fmt.Errorf("reported citation mapping omits a supplied candidate chunk: %s", c.ChunkID)
		}
	}
	newURLs := map[string]bool{}
	oldURLs := urls(prepared)
	for u := range finalURLs {
		if articleURLs[u] && !oldURLs[u] {
			newURLs[u] = true
		}
	}
	if !equalStrings(r.NewArticleURLs, sortedKeys(newURLs)) {
		return fmt.Errorf("reported new_article_urls differs from emitted definition")
	}
	return nil
}
