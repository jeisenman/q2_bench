package agentmemory

import (
	"context"
	"errors"
	"testing"
)

func testMemory(t *testing.T, store Store, scopeID string) *Memory {
	t.Helper()
	memory, err := New(
		store,
		"resource-discovery",
		Scope{TenantID: "q2", Type: TeamScope, ID: scopeID},
		DefaultAliasConfirmations,
	)
	if err != nil {
		t.Fatal(err)
	}
	return memory
}

func TestNormalizeKey(t *testing.T) {
	t.Parallel()
	key, err := NormalizeKey(" C.N.B. ")
	if err != nil {
		t.Fatal(err)
	}
	if key != "c n b" {
		t.Fatalf("NormalizeKey() = %q", key)
	}
}

func TestAliasRequiresRepeatedConfirmation(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	memory := testMemory(t, NewMemoryStore(), "data-engineering")
	proposed, err := memory.ProposeAlias(
		ctx,
		"CNB",
		"resource-discovery-client",
		"11111111-1111-1111-1111-111111111111",
		"City National Bank",
	)
	if err != nil {
		t.Fatal(err)
	}
	for index := 0; index < DefaultAliasConfirmations; index++ {
		if _, err := memory.RecordAliasEvidence(
			ctx,
			proposed.ID,
			EvidenceConfirmed,
			string(rune('a'+index)),
		); err != nil {
			t.Fatal(err)
		}
	}
	resolution, err := memory.ResolveAlias(ctx, "cnb")
	if err != nil {
		t.Fatal(err)
	}
	if resolution.Status != AliasResolved {
		t.Fatalf("resolution = %#v", resolution)
	}
}

func TestMemoryIsolatedByScope(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	store := NewMemoryStore()
	first := testMemory(t, store, "one")
	second := testMemory(t, store, "two")
	if _, err := first.ProposeAlias(ctx, "CNB", "client", "1", "City National Bank"); err != nil {
		t.Fatal(err)
	}
	resolution, err := second.ResolveAlias(ctx, "CNB")
	if err != nil {
		t.Fatal(err)
	}
	if resolution.Status != AliasNotFound {
		t.Fatalf("resolution = %#v", resolution)
	}
}

func TestEvidenceIsIdempotentAndConflictsFail(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	memory := testMemory(t, NewMemoryStore(), "one")
	proposed, err := memory.ProposeAlias(ctx, "CNB", "client", "1", "City National Bank")
	if err != nil {
		t.Fatal(err)
	}
	first, err := memory.RecordAliasEvidence(ctx, proposed.ID, EvidenceConfirmed, "same")
	if err != nil {
		t.Fatal(err)
	}
	replay, err := memory.RecordAliasEvidence(ctx, proposed.ID, EvidenceConfirmed, "same")
	if err != nil {
		t.Fatal(err)
	}
	if first.EvidenceCount != 1 || replay.EvidenceCount != 1 {
		t.Fatalf("counts = %d, %d", first.EvidenceCount, replay.EvidenceCount)
	}
	_, err = memory.RecordAliasEvidence(ctx, proposed.ID, EvidenceRejected, "same")
	var conflict *ConflictError
	if !errors.As(err, &conflict) {
		t.Fatalf("expected ConflictError, got %v", err)
	}
}
