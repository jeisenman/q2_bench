package mcpapi

import (
	"context"
	"encoding/json"
	"testing"

	rdagent "github.com/jeisenman/q2_bench/agents/resourcediscovery"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

const resourceDiscoveryTestUUID = "1f06da19-2f61-401c-a1b7-38902e4f3543"

type resourceDiscoveryTestSource struct {
	identifiers []rdagent.Identifier
}

func (s *resourceDiscoveryTestSource) Lookup(
	_ context.Context,
	identifier rdagent.Identifier,
) ([]map[string]any, error) {
	s.identifiers = append(s.identifiers, identifier)
	return []map[string]any{{
		"client_name":           "Example Bank",
		"provisioned_client_id": resourceDiscoveryTestUUID,
		"client_secret":         "must-not-escape",
	}}, nil
}

func TestResourceDiscoveryMCPRoutesThroughAgent(t *testing.T) {
	t.Parallel()
	source := &resourceDiscoveryTestSource{}
	session := newResourceDiscoverySession(t, rdagent.Agent{Source: source})
	result, err := session.CallTool(context.Background(), &mcp.CallToolParams{
		Name: "lookup_resources",
		Arguments: map[string]any{
			"identifier_kind":  "client_id",
			"identifier_value": resourceDiscoveryTestUUID,
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	if result.IsError {
		t.Fatalf("tool error = %#v", result.Content)
	}
	payload := resourceDiscoveryPayload(t, result)
	if payload["identifier_value"] != resourceDiscoveryTestUUID ||
		payload["status"] != "unique" {
		t.Fatalf("payload = %#v", payload)
	}
	records := payload["records"].([]any)
	record := records[0].(map[string]any)
	if record["provisioned_client_id"] != resourceDiscoveryTestUUID {
		t.Fatalf("record = %#v", record)
	}
	if _, leaked := record["client_secret"]; leaked {
		t.Fatalf("record leaked a secret field: %#v", record)
	}
	if len(source.identifiers) != 1 ||
		source.identifiers[0].Value != resourceDiscoveryTestUUID {
		t.Fatalf("identifiers = %#v", source.identifiers)
	}
}

func TestResourceDiscoveryMCPRejectsAbbreviatedClientID(t *testing.T) {
	t.Parallel()
	source := &resourceDiscoveryTestSource{}
	session := newResourceDiscoverySession(t, rdagent.Agent{Source: source})
	result, err := session.CallTool(context.Background(), &mcp.CallToolParams{
		Name: "lookup_resources",
		Arguments: map[string]any{
			"identifier_kind": "client_id", "identifier_value": "1f0",
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	if !result.IsError {
		t.Fatalf("result = %#v", result)
	}
	if len(source.identifiers) != 0 {
		t.Fatalf("source was called: %#v", source.identifiers)
	}
}

func newResourceDiscoverySession(
	t *testing.T,
	agent rdagent.Agent,
) *mcp.ClientSession {
	t.Helper()
	server := mcp.NewServer(&mcp.Implementation{Name: "test", Version: "1"}, nil)
	registerResourceDiscoveryAgent(server, agent)
	serverTransport, clientTransport := mcp.NewInMemoryTransports()
	if _, err := server.Connect(context.Background(), serverTransport, nil); err != nil {
		t.Fatal(err)
	}
	client := mcp.NewClient(
		&mcp.Implementation{Name: "test-client", Version: "1"},
		nil,
	)
	session, err := client.Connect(context.Background(), clientTransport, nil)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = session.Close() })
	return session
}

func resourceDiscoveryPayload(
	t *testing.T,
	result *mcp.CallToolResult,
) map[string]any {
	t.Helper()
	var payload map[string]any
	encoded, err := json.Marshal(result.StructuredContent)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(encoded, &payload); err != nil {
		t.Fatal(err)
	}
	return payload
}
