package resourcediscovery

import (
	"context"
	"testing"

	agent "github.com/jeisenman/q2_bench/agents/resourcediscovery"
)

type countingSource struct {
	calls int
}

func (s *countingSource) Lookup(
	_ context.Context,
	_ agent.Identifier,
) ([]map[string]any, error) {
	s.calls++
	return nil, nil
}

func TestIndexedSourceShortCircuitsCompleteLocalUUID(t *testing.T) {
	t.Parallel()
	const clientID = "1f06da19-2f61-401c-a1b7-38902e4f3543"
	local := &JSONClientLookupSource{Index: agent.NewClientLookupIndex(map[string]any{
		clientID: map[string]any{
			"name": "Example Bank", "source": "resource-discovery-api",
			"api_status": "unique-match",
		},
	})}
	primary := &countingSource{}
	source := IndexedSource{Primary: primary, Fallback: local}

	records, err := source.Lookup(context.Background(), agent.Identifier{
		Kind: agent.ClientID, Value: clientID,
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(records) != 1 ||
		records[0]["provisioned_client_id"] != clientID {
		t.Fatalf("records = %#v", records)
	}
	if primary.calls != 0 {
		t.Fatalf("remote calls = %d", primary.calls)
	}
}
