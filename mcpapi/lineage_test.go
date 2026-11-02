package mcpapi

import (
	"context"
	"encoding/json"
	"reflect"
	"sort"
	"testing"

	lineageworkflow "github.com/jeisenman/q2_bench/workflows/lineage"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func TestLineageToolRegistrationAndSearch(t *testing.T) {
	server := mcp.NewServer(&mcp.Implementation{Name: "test", Version: "1"}, nil)
	registerLineageWithSource(
		server,
		lineageTestSource{graph: lineageTestGraph()},
	)
	serverTransport, clientTransport := mcp.NewInMemoryTransports()
	if _, err := server.Connect(context.Background(), serverTransport, nil); err != nil {
		t.Fatal(err)
	}
	client := mcp.NewClient(&mcp.Implementation{Name: "test-client", Version: "1"}, nil)
	session, err := client.Connect(context.Background(), clientTransport, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer session.Close()

	result, err := session.ListTools(context.Background(), nil)
	if err != nil {
		t.Fatal(err)
	}
	names := make([]string, len(result.Tools))
	for index, tool := range result.Tools {
		names[index] = tool.Name
		if tool.Annotations == nil ||
			!tool.Annotations.ReadOnlyHint ||
			tool.Annotations.DestructiveHint == nil ||
			*tool.Annotations.DestructiveHint ||
			!tool.Annotations.IdempotentHint {
			t.Fatalf("%s annotations = %#v", tool.Name, tool.Annotations)
		}
	}
	sort.Strings(names)
	want := []string{
		"compare_lineage_backfill",
		"compare_lineage_versions",
		"get_lineage_change_history",
		"get_lineage_downstream",
		"get_lineage_manifest",
		"get_lineage_transformation",
		"get_lineage_upstream",
		"search_lineage_datasets",
	}
	if !reflect.DeepEqual(names, want) {
		t.Fatalf("tools = %v, want %v", names, want)
	}

	call, err := session.CallTool(context.Background(), &mcp.CallToolParams{
		Name:      "search_lineage_datasets",
		Arguments: map[string]any{"query": "engagement"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if call.IsError {
		t.Fatalf("tool returned error: %#v", call.Content)
	}
	var output struct {
		Count    int              `json:"count"`
		Datasets []map[string]any `json:"datasets"`
	}
	payload, err := json.Marshal(call.StructuredContent)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(payload, &output); err != nil {
		t.Fatal(err)
	}
	if output.Count != 1 || len(output.Datasets) != 1 {
		t.Fatalf("output = %#v", output)
	}
	for _, name := range []string{"get_lineage_manifest", "compare_lineage_versions", "compare_lineage_backfill"} {
		arguments := map[string]any{"snapshot_id": "../../unapproved"}
		if name == "compare_lineage_versions" {
			arguments = map[string]any{"base_id": "../../unapproved", "head_id": "../../unapproved", "policy": map[string]any{"mode": "additive", "replacements": []any{}}}
		}
		if name == "compare_lineage_backfill" {
			arguments = map[string]any{"snapshot_id": "../../unapproved", "plan": map[string]any{}}
		}
		call, err := session.CallTool(context.Background(), &mcp.CallToolParams{Name: name, Arguments: arguments})
		if err != nil {
			t.Fatal(err)
		}
		if !call.IsError {
			t.Fatalf("%s accepted an invalid snapshot ID", name)
		}
	}
}

type lineageTestSource struct {
	graph lineageworkflow.Graph
}

func (s lineageTestSource) Latest(context.Context) (lineageworkflow.Graph, error) {
	return s.graph, nil
}

func (s lineageTestSource) History(
	context.Context,
	int,
) ([]lineageworkflow.Graph, error) {
	return []lineageworkflow.Graph{s.graph}, nil
}

func lineageTestGraph() lineageworkflow.Graph {
	return lineageworkflow.Graph{
		Manifest: map[string]any{"commit": "test"},
		Nodes: []lineageworkflow.Node{
			{
				ID: "dataset:engagement", Kind: "dataset",
				Data: map[string]any{
					"id": "dataset:engagement", "kind": "dataset",
					"name": "engagement",
				},
			},
		},
	}
}
