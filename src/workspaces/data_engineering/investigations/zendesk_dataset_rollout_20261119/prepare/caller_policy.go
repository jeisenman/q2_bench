package main

import (
	_ "embed"
	"fmt"
	"regexp"
	"strconv"
	"strings"
)

const callerPolicyVersion = "single-luna-audit-cleanup/1"
const callerPolicySHA = "0b0a9ac8e4ac0d0ab811bdb09955b613bb6d5d0c5c9d3db243a84efcca7acf4f"

//go:embed policies/single-luna-audit-cleanup-v1.md
var callerPolicy []byte

type policyRecord struct {
	Version string `json:"version"`
	Path    string `json:"path"`
	SHA256  string `json:"sha256"`
}
type unsafeSpan struct {
	Field string `json:"field"`
	Start int    `json:"start_byte"`
	End   int    `json:"end_byte"`
	Text  string `json:"text"`
}
type preparationRecord struct {
	Contract     string       `json:"contract"`
	Status       string       `json:"status"`
	Removals     []removal    `json:"removals"`
	CleanupError string       `json:"cleanup_error,omitempty"`
	UnsafeSpans  []unsafeSpan `json:"unsafe_spans"`
}

var spanError = regexp.MustCompile(`^(description|business_context).* at bytes ([0-9]+):([0-9]+)$`)

func selectedPolicy(mode string) (*policyRecord, error) {
	if mode == "" || mode == "conservative" {
		return nil, nil
	}
	if mode != "single-luna-pass" {
		return nil, fmt.Errorf("unsupported cleanup policy %q", mode)
	}
	if digest(callerPolicy) != callerPolicySHA {
		return nil, fmt.Errorf("caller cleanup policy digest mismatch")
	}
	return &policyRecord{Version: callerPolicyVersion, Path: "sources/caller-policy.md", SHA256: callerPolicySHA}, nil
}

func prepareDefinition(d definition, mode string) (definition, preparationRecord, error) {
	record := preparationRecord{Contract: "audit-only-sentence/v1", Status: "unchanged", Removals: []removal{}, UnsafeSpans: []unsafeSpan{}}
	cleaned, changes, err := cleanDefinition(d)
	if err == nil {
		record.Removals = changes
		if len(changes) > 0 {
			record.Status = "audit_cleanup_prepared"
		}
		return cleaned, record, nil
	}
	if mode != "single-luna-pass" {
		return d, record, err
	}
	record.Status = "pending_single_luna_cleanup"
	record.CleanupError = err.Error()
	if match := spanError.FindStringSubmatch(err.Error()); match != nil {
		start, _ := strconv.Atoi(match[2])
		end, _ := strconv.Atoi(match[3])
		text := d.Description
		if match[1] == "business_context" {
			text = d.BusinessContext
		}
		if start >= 0 && end >= start && end <= len(text) {
			record.UnsafeSpans = append(record.UnsafeSpans, unsafeSpan{Field: match[1], Start: start, End: end, Text: text[start:end]})
		}
	}
	if strings.TrimSpace(d.Description) == "" || strings.TrimSpace(d.BusinessContext) == "" {
		return d, record, fmt.Errorf("original definition has empty required text %s", d.NodeID)
	}
	// Preserve both original strings, even if cleanup succeeded for the first field.
	return d, record, nil
}
