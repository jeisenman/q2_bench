package main

import (
	"fmt"
	"regexp"
	"strings"
)

type removal struct {
	Field string `json:"field"`
	Start int    `json:"start_byte"`
	End   int    `json:"end_byte"`
	Text  string `json:"removed_text"`
	Rule  string `json:"rule"`
}

var auditSignal = regexp.MustCompile(`(?i)zendesk|no_support|candidateCount|snapshotId|chunkId|evidence audit|documentation audit`)
var explicitAudit = regexp.MustCompile(`(?i)^(?:\*\*)?(?:Zendesk (?:evidence )?audit|Evidence audit|Audit):|^(?:\*\*)?Zendesk evidence audit \(`)
var auditSentence = regexp.MustCompile(`(?i)^(?:the |no |overall |status:?\s*|` + "`" + `)?(?:supplied )?(?:Zendesk|candidate|no_support)|^no (?:supplied )?(?:candidate|documentation)|^there (?:are|is) no (?:Zendesk|candidate)|^(?:claim|status|node ID|relationship|chunkId|URL|snapshotId):|^this audit `)
var auditMetadata = regexp.MustCompile(`(?i)^(?:claim|status|node ID|relationship|chunkId|URL|snapshotId):`)
var technicalMixed = regexp.MustCompile(`(?i)\b(?:runtime|freshness|SME|code|technical|graph evidence|source evidence|lineage evidence|filter|join|aggregation|calculation|uniqueness|causal|profitability)\b`)

// sentenceSpans retains exact byte boundaries and does not split inside code, links or brackets.
func sentenceSpans(text string) [][2]int {
	spans := [][2]int{}
	start := 0
	backtick := false
	depth := 0
	for i := 0; i < len(text); i++ {
		switch text[i] {
		case '`':
			backtick = !backtick
		case '(', '[', '{':
			if !backtick {
				depth++
			}
		case ')', ']', '}':
			if !backtick && depth > 0 {
				depth--
			}
		}
		if !backtick && depth == 0 && (text[i] == '.' || text[i] == '!' || text[i] == '?') && (i+1 == len(text) || text[i+1] == ' ' || text[i+1] == '\n') {
			spans = append(spans, [2]int{start, i + 1})
			start = i + 1
		}
	}
	if start < len(text) {
		spans = append(spans, [2]int{start, len(text)})
	}
	return spans
}

func cleanText(field, text string) (string, []removal, error) {
	if !auditSignal.MatchString(text) {
		return text, []removal{}, nil
	}
	removed := []removal{}
	kept := strings.Builder{}
	auditBlock := false
	for _, span := range sentenceSpans(text) {
		raw := text[span[0]:span[1]]
		sentence := strings.TrimSpace(raw)
		if sentence == "" {
			kept.WriteString(raw)
			continue
		}
		explicit := explicitAudit.MatchString(sentence)
		if explicit {
			auditBlock = true
		}
		audit := explicit || (auditSignal.MatchString(sentence) && auditSentence.MatchString(sentence)) || (auditBlock && auditMetadata.MatchString(sentence))
		if audit {
			if strings.Contains(sentence, "http://") || strings.Contains(sentence, "https://") || technicalMixed.MatchString(sentence) {
				return "", nil, fmt.Errorf("%s audit sentence mixes useful links or technical caveats at bytes %d:%d", field, span[0], span[1])
			}
			removed = append(removed, removal{Field: field, Start: span[0], End: span[1], Text: raw, Rule: "audit-only-sentence/v1"})
			continue
		}
		if auditSignal.MatchString(sentence) {
			return "", nil, fmt.Errorf("%s contains ambiguous audit prose at bytes %d:%d", field, span[0], span[1])
		}
		auditBlock = false
		kept.WriteString(raw)
	}
	out := strings.TrimSpace(kept.String())
	if out == "" {
		return "", nil, fmt.Errorf("%s cleanup would remove all definition text", field)
	}
	return out, removed, nil
}

func cleanDefinition(d definition) (definition, []removal, error) {
	out := d
	description, a, err := cleanText("description", d.Description)
	if err != nil {
		return d, nil, err
	}
	business, b, err := cleanText("business_context", d.BusinessContext)
	if err != nil {
		return d, nil, err
	}
	out.Description = description
	out.BusinessContext = business
	return out, append(a, b...), nil
}
