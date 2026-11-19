package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"regexp"
	"sort"
	"strings"
)

var errIdentityMismatch = errors.New("definition identity changed")

type definition struct {
	Description     string `json:"description"`
	BusinessContext string `json:"business_context"`
	NodeID          string `json:"node_id"`
}

var urlPattern = regexp.MustCompile(`https?://[^\s<>\)\]"` + "`" + `]+`)
var auditPattern = regexp.MustCompile(`(?i)(Zendesk evidence audit|candidateCount|no_support|weak_support|evidence[ -]audit|Zendesk.{0,30}(?:support status|audit status|audit verdict)|\[(?:TODO|citation needed|source needed)\]|\]\((?:null|#|TODO)\))`)
var absencePattern = regexp.MustCompile(`(?i)\b(?:no|none of the)\s+(?:supplied\s+|relevant\s+)?Zendesk\s+(?:articles?|candidates?|chunks?|documentation)\b|\bconfidence\s*[:=]\s*[0-9]`)
var codePattern = regexp.MustCompile("`[^`\\n]+`")
var numberPattern = regexp.MustCompile(`\b[0-9]+(?:\.[0-9]+)?\b`)

func isAuditLiteral(token string) bool {
	s := strings.ToLower(token)
	for _, marker := range []string{"zendesk", "no_support", "weak_support", "candidatecount", "snapshotid", "chunkid", "evidence audit", "supportstatus", "support_status"} {
		if strings.Contains(s, marker) {
			return true
		}
	}
	return false
}

func containsCodeLiteral(text, token string) bool {
	if strings.Contains(text, token) {
		return true
	}
	value := strings.Trim(token, "`")
	identifier := regexp.MustCompile("^[A-Za-z_][A-Za-z0-9_]*$")
	if identifier.MatchString(value) {
		return regexp.MustCompile("(?:^|[^A-Za-z0-9_])" + regexp.QuoteMeta(value) + "(?:$|[^A-Za-z0-9_])").MatchString(text)
	}
	return strings.Contains(text, value)
}

func auditMetadataLiteral(before, token string) bool {
	pattern := regexp.MustCompile(`(?i)(?:node(?: ID)?|relationship|chunkId(?:/URL)?|URL|snapshotId|status)\s*[:=]?\s*` + regexp.QuoteMeta(token))
	return pattern.MatchString(before)
}

func normalizeOutput(raw []byte) ([]byte, string) {
	s := strings.TrimSpace(string(raw))
	if strings.HasPrefix(s, "```json\n") && strings.HasSuffix(s, "\n```") {
		return []byte(strings.TrimSuffix(strings.TrimPrefix(s, "```json\n"), "\n```")), "Removed one outer JSON Markdown fence; values unchanged."
	}
	return []byte(s), "Whitespace trimmed; definition values unchanged."
}
func decodeDefinition(raw []byte) (definition, error) {
	var d definition
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.DisallowUnknownFields()
	if e := dec.Decode(&d); e != nil {
		return d, e
	}
	if e := dec.Decode(&struct{}{}); e != io.EOF {
		return d, errors.New("output contains trailing content")
	}
	var keys map[string]json.RawMessage
	if e := json.Unmarshal(raw, &keys); e != nil {
		return d, e
	}
	if len(keys) != 3 {
		return d, errors.New("definition keys changed")
	}
	if strings.TrimSpace(d.Description) == "" || strings.TrimSpace(d.BusinessContext) == "" {
		return d, errors.New("required definition text is empty")
	}
	return d, nil
}
func urls(text string) map[string]bool {
	out := map[string]bool{}
	for _, u := range urlPattern.FindAllString(text, -1) {
		out[strings.TrimRight(u, ".,;:")] = true
	}
	return out
}
func validateDefinition(raw, prepared, input []byte, nodeID string, cleanup ...bool) ([]byte, []citation, error) {
	d, e := decodeDefinition(raw)
	if e != nil {
		return nil, nil, fmt.Errorf("invalid model definition: %w", e)
	}
	old, e := decodeDefinition(prepared)
	if e != nil {
		return nil, nil, e
	}
	if d.NodeID != nodeID || old.NodeID != nodeID {
		return nil, nil, errIdentityMismatch
	}
	text := d.Description + "\n" + d.BusinessContext
	before := old.Description + "\n" + old.BusinessContext
	if auditPattern.MatchString(text) || absencePattern.MatchString(text) {
		return nil, nil, errors.New("reader-facing audit, verdict or placeholder detected")
	}
	for _, token := range codePattern.FindAllString(before, -1) {
		if len(cleanup) > 0 && cleanup[0] && (isAuditLiteral(token) || token == "`"+nodeID+"`" || auditMetadataLiteral(before, token)) {
			continue
		}
		if !containsCodeLiteral(text, token) {
			return nil, nil, fmt.Errorf("existing code literal was removed: %s", token)
		}
	}
	guardedDescription := old.Description
	if len(cleanup) > 0 && cleanup[0] {
		metadata := regexp.MustCompile(`(?i)2026-09-02T205953Z-zendesk-corpus|candidateCount\s*[:=]?\s*[0-9]+`)
		guardedDescription = metadata.ReplaceAllString(guardedDescription, "")
	}
	beforeNumbers := numberPattern.FindAllString(guardedDescription, -1)
	afterNumbers := map[string]bool{}
	for _, n := range numberPattern.FindAllString(text, -1) {
		afterNumbers[n] = true
	}
	for _, n := range beforeNumbers {
		if !afterNumbers[n] {
			return nil, nil, fmt.Errorf("existing technical numeric token was removed: %s", n)
		}
	}
	var payload struct {
		ZendeskEvidence json.RawMessage `json:"zendesk_evidence"`
	}
	if e = json.Unmarshal(input, &payload); e != nil {
		return nil, nil, e
	}
	var evidence any
	if e = json.Unmarshal(payload.ZendeskEvidence, &evidence); e != nil {
		return nil, nil, e
	}
	candidates := []citation{}
	collectCitations(evidence, &candidates)
	allowed := urls(before)
	for _, c := range candidates {
		allowed[c.URL] = true
	}
	for u := range urls(before) {
		if !urls(text)[u] {
			return nil, nil, fmt.Errorf("existing source citation was removed: %s", u)
		}
	}
	outputURLs := urls(text)
	for u := range outputURLs {
		if !allowed[u] {
			return nil, nil, fmt.Errorf("new URL is outside supplied evidence: %s", u)
		}
	}
	if len(candidates) == 0 && d != old && !(len(cleanup) > 0 && cleanup[0]) {
		return nil, nil, errors.New("no-article definition changed after recorded audit preparation")
	}
	cited := []citation{}
	seen := map[string]bool{}
	for _, c := range candidates {
		key := c.ArticleID + "\x00" + c.ChunkID
		if outputURLs[c.URL] && !seen[key] {
			cited = append(cited, c)
			seen[key] = true
		}
	}
	if d != old && len(cited) == 0 && !(len(cleanup) > 0 && cleanup[0]) {
		return nil, nil, errors.New("changed definition has no link to a supplied article")
	}
	sort.Slice(cited, func(i, j int) bool { return cited[i].ChunkID < cited[j].ChunkID })
	out, e := json.MarshalIndent(d, "", "  ")
	if e != nil {
		return nil, nil, e
	}
	return append(out, '\n'), cited, nil
}
func collectCitations(value any, out *[]citation) {
	switch v := value.(type) {
	case []any:
		for _, item := range v {
			collectCitations(item, out)
		}
	case map[string]any:
		text := func(keys ...string) string {
			for _, key := range keys {
				switch s := v[key].(type) {
				case string:
					return s
				case float64:
					return fmt.Sprintf("%.0f", s)
				}
			}
			return ""
		}
		c := citation{ArticleID: text("articleId", "article_id"), ChunkID: text("chunkId", "chunk_id"), URL: text("url", "original_url", "article_url")}
		if c.ArticleID != "" && c.ChunkID != "" && c.URL != "" {
			*out = append(*out, c)
		}
		for _, item := range v {
			collectCitations(item, out)
		}
	}
}
