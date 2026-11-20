package main

import (
	"encoding/json"
	"strings"
	"testing"
)

func fixtureDefinition(t *testing.T, d definition) []byte {
	t.Helper()
	b, e := json.Marshal(d)
	if e != nil {
		t.Fatal(e)
	}
	return b
}
func TestValidationPreservesIdentityAndTechnicalEvidence(t *testing.T) {
	d := definition{Description: "Filter `Status` to 30 days. [Source](https://example.test/code)", BusinessContext: "An intermediate dataset; runtime behavior is not established.", NodeID: "dataset:test/accounts"}
	before := fixtureDefinition(t, d)
	input := []byte(`{"zendesk_evidence":{"chunks":[{"articleId":"7","chunkId":"7-en-overview","url":"https://support.precisionlender.com/hc/en-us/articles/7"}]}}`)
	d.BusinessContext += " Product context is documented in [the article](https://support.precisionlender.com/hc/en-us/articles/7)."
	out, cited, e := validateDefinition(fixtureDefinition(t, d), before, input, d.NodeID)
	if e != nil || len(out) == 0 || len(cited) != 1 {
		t.Fatalf("valid draft failed: %v", e)
	}
	for _, change := range []func(*definition){func(x *definition) { x.NodeID = "other" }, func(x *definition) { x.Description = "Unrelated" }, func(x *definition) { x.BusinessContext += " Zendesk evidence audit: no_support" }, func(x *definition) { x.BusinessContext += " [Invented](https://bad.test/article)" }} {
		bad := d
		change(&bad)
		if _, _, e = validateDefinition(fixtureDefinition(t, bad), before, input, d.NodeID); e == nil {
			t.Fatal("accepted invalid draft")
		}
	}
}
func TestNoCandidateMeansUnchanged(t *testing.T) {
	d := definition{Description: "A dataset", BusinessContext: "Technical context", NodeID: "dataset:n/x"}
	before := fixtureDefinition(t, d)
	input := []byte(`{"zendesk_evidence":{"chunks":[]}}`)
	if _, _, e := validateDefinition(before, before, input, d.NodeID); e != nil {
		t.Fatal(e)
	}
	d.BusinessContext += " Added context"
	if _, _, e := validateDefinition(fixtureDefinition(t, d), before, input, d.NodeID); e == nil {
		t.Fatal("changed no-candidate definition")
	}
}
func TestOutputFormatAndArtifactPaths(t *testing.T) {
	d := definition{Description: "Data", BusinessContext: "Context", NodeID: "dataset:n/x"}
	b := fixtureDefinition(t, d)
	normal, note := normalizeOutput([]byte("```json\n" + string(b) + "\n```"))
	if string(normal) != string(b) || !strings.Contains(note, "fence") {
		t.Fatal("format normalization failed")
	}
	for _, bad := range []string{string(b) + " trailing", `{"node_id":"x","description":"d","business_context":"c","new":true}`, `{"node_id":"x"}`} {
		if _, e := decodeDefinition([]byte(bad)); e == nil {
			t.Fatal("accepted malformed definition")
		}
	}
	for _, path := range []string{"../escape", "/absolute"} {
		if _, e := resolve(t.TempDir(), path); e == nil {
			t.Fatal("accepted unsafe path")
		}
	}
}

func TestApprovedSinglePassCleanupException(t *testing.T) {
	original := definition{Description: "Keeps `Status` for 30 days. No Zendesk candidate was supplied (candidateCount 0; snapshotId 2026-09-02T205953Z-zendesk-corpus).", BusinessContext: "An intermediate output. Zendesk evidence audit: status `no_support`.", NodeID: "dataset:n/x"}
	cleaned := original
	cleaned.Description = "Keeps `Status` for 30 days."
	cleaned.BusinessContext = "An intermediate output."
	input := []byte(`{"zendesk_evidence":{"chunks":[]}}`)
	if _, _, e := validateDefinition(fixtureDefinition(t, cleaned), fixtureDefinition(t, original), input, original.NodeID, true); e != nil {
		t.Fatal(e)
	}
	if _, _, e := validateDefinition(fixtureDefinition(t, cleaned), fixtureDefinition(t, original), input, original.NodeID); e == nil {
		t.Fatal("cleanup exception applied without approval")
	}
	cleaned.Description = "Keeps `Status` for 15 days."
	if _, _, e := validateDefinition(fixtureDefinition(t, cleaned), fixtureDefinition(t, original), input, original.NodeID, true); e == nil {
		t.Fatal("cleanup removed technical numeric constraint")
	}
}

func TestAuditIdentityEchoAndCodeFormattingAreNotTechnicalEdits(t *testing.T) {
	d := definition{Description: "Read under `{runPath}/ApplicationInput/`.", BusinessContext: "Technical context. Audit: node ID: `dataset:n/x`; relationship `explains_purpose`; status `no_support`.", NodeID: "dataset:n/x"}
	edited := d
	edited.Description = "Read under `{runPath}/ApplicationInput/Accounts.csv`."
	edited.BusinessContext = "Technical context."
	input := []byte(`{"zendesk_evidence":{"chunks":[]}}`)
	if _, _, e := validateDefinition(fixtureDefinition(t, edited), fixtureDefinition(t, d), input, d.NodeID, true); e != nil {
		t.Fatal(e)
	}
	edited.NodeID = "dataset:n/other"
	if _, _, e := validateDefinition(fixtureDefinition(t, edited), fixtureDefinition(t, d), input, d.NodeID, true); e == nil {
		t.Fatal("audit identity exemption changed actual node identity")
	}
}

func TestCodeFormatGuardKeepsIdentifierBoundaries(t *testing.T) {
	if !containsCodeLiteral("The Status value remains.", "`Status`") {
		t.Fatal("lost unchanged unformatted identifier")
	}
	if containsCodeLiteral("The OldStatusCode value differs.", "`Status`") {
		t.Fatal("accepted a different identifier containing the original substring")
	}
}
