package main

import (
	"reflect"
	"strings"
	"testing"
)

func TestSinglePassFallbackPreservesOriginalText(t *testing.T) {
	original := definition{NodeID: "dataset:test/a", Description: "  Keep the 30-day window and [source](https://example.com).\n", BusinessContext: "Zendesk audit: no_support; runtime freshness is not established."}
	got, record, err := prepareDefinition(original, "single-luna-pass")
	if err != nil || !reflect.DeepEqual(got, original) {
		t.Fatalf("original bytes changed: %+v %v", got, err)
	}
	if record.Status != "pending_single_luna_cleanup" || record.CleanupError == "" || len(record.UnsafeSpans) != 1 || len(record.Removals) != 0 {
		t.Fatalf("missing fallback evidence: %+v", record)
	}
	span := record.UnsafeSpans[0]
	if span.Text != original.BusinessContext[span.Start:span.End] {
		t.Fatal("unsafe span changed")
	}
	if _, _, err := prepareDefinition(original, "conservative"); err == nil {
		t.Fatal("default conservative contract weakened")
	}
}

func TestCallerPolicyPinAndSafeCleanup(t *testing.T) {
	policy, err := selectedPolicy("single-luna-pass")
	if err != nil {
		t.Fatal(err)
	}
	if policy.Version != "single-luna-audit-cleanup/1" || policy.SHA256 != callerPolicySHA || digest(callerPolicy) != callerPolicySHA || policy.Path != "sources/caller-policy.md" {
		t.Fatal("caller policy pin changed")
	}
	for _, phrase := range []string{"same single Luna pass", "only audit cleanup", "Do not publish"} {
		if !strings.Contains(string(callerPolicy), phrase) {
			t.Fatalf("required policy instruction absent: %s", phrase)
		}
	}
	if policy, err := selectedPolicy(""); err != nil || policy != nil {
		t.Fatal("default policy changed")
	}
	if _, err := selectedPolicy("unapproved"); err == nil {
		t.Fatal("unknown policy accepted")
	}
	original := definition{NodeID: "dataset:test/a", Description: "Keep exact technical text.", BusinessContext: "Keep the 30-day window. Zendesk evidence audit: status no_support."}
	got, record, err := prepareDefinition(original, "single-luna-pass")
	if err != nil || got.Description != original.Description || got.BusinessContext != "Keep the 30-day window." || record.Status != "audit_cleanup_prepared" || len(record.Removals) != 1 {
		t.Fatalf("safe cleanup changed: %+v %+v %v", got, record, err)
	}
}
