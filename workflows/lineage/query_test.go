package lineage

import (
	"context"
	"strings"
	"testing"
)

type memorySource struct {
	latest  Graph
	history []Graph
}

func (s memorySource) Latest(context.Context) (Graph, error) {
	return s.latest, nil
}

func (s memorySource) History(_ context.Context, limit int) ([]Graph, error) {
	if limit > len(s.history) {
		limit = len(s.history)
	}
	return s.history[:limit], nil
}

func TestSearchDatasetsRanksExactMatchesAndFields(t *testing.T) {
	service := testService(t)

	result, err := service.SearchDatasets(context.Background(), "engagement", 0)
	if err != nil {
		t.Fatal(err)
	}
	if len(result.Nodes) != 1 || result.Nodes[0].ID != "dataset:engagement" {
		t.Fatalf("nodes = %#v", result.Nodes)
	}
	if got := result.Nodes[0].Summary()["fieldCount"]; got != 1 {
		t.Fatalf("field count = %#v", got)
	}
}

func TestTraverseBoundsAndDirections(t *testing.T) {
	service := testService(t)

	upstream, err := service.Traverse(
		context.Background(), "dataset:engagement", Upstream, 2, 10,
	)
	if err != nil {
		t.Fatal(err)
	}
	got := nodeIDs(upstream.Nodes)
	want := []string{"dataset:raw", "job:transform"}
	if !equalStrings(got, want) {
		t.Fatalf("upstream nodes = %v, want %v", got, want)
	}
	if len(upstream.Edges) != 2 || upstream.Truncated {
		t.Fatalf("upstream result = %#v", upstream)
	}

	downstream, err := service.Traverse(
		context.Background(), "dataset:raw", Downstream, 2, 1,
	)
	if err != nil {
		t.Fatal(err)
	}
	if got := nodeIDs(downstream.Nodes); !equalStrings(got, []string{"job:transform"}) {
		t.Fatalf("downstream nodes = %v", got)
	}
	if !downstream.Truncated {
		t.Fatal("expected traversal to report truncation")
	}
}

func TestLineageQueryValidation(t *testing.T) {
	service := testService(t)
	tests := []struct {
		name string
		call func() error
		want string
	}{
		{
			name: "empty search",
			call: func() error {
				_, err := service.SearchDatasets(context.Background(), " ", 0)
				return err
			},
			want: "query must not be empty",
		},
		{
			name: "invalid direction",
			call: func() error {
				_, err := service.Traverse(
					context.Background(), "dataset:raw", Direction("sideways"), 1, 1,
				)
				return err
			},
			want: "direction must be upstream or downstream",
		},
		{
			name: "missing node",
			call: func() error {
				_, _, err := service.TransformationDetails(context.Background(), "missing")
				return err
			},
			want: "lineage node does not exist",
		},
		{
			name: "depth above maximum",
			call: func() error {
				_, err := service.Traverse(
					context.Background(), "dataset:raw", Downstream, maxTraversalDepth+1, 1,
				)
				return err
			},
			want: "depth must be between 1 and 10",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if err := test.call(); err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("error = %v, want %q", err, test.want)
			}
		})
	}
}

func TestChangeHistoryClassifiesCreatedAndChangedNodes(t *testing.T) {
	latest := testGraph()
	changed := testGraph()
	changed.Nodes[2].Data["description"] = "changed"
	source := memorySource{
		latest:  latest,
		history: []Graph{latest, changed},
	}
	service, err := NewService(source)
	if err != nil {
		t.Fatal(err)
	}

	revisions, err := service.ChangeHistory(context.Background(), "dataset:engagement", 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(revisions) != 2 ||
		revisions[0].ChangeType != "changed" ||
		revisions[1].ChangeType != "created" {
		t.Fatalf("revisions = %#v", revisions)
	}

	revisions, err = service.ChangeHistory(context.Background(), "dataset:new", 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(revisions) != 0 {
		t.Fatalf("unknown node revisions = %#v", revisions)
	}
}

func testService(t *testing.T) *Service {
	t.Helper()
	service, err := NewService(memorySource{latest: testGraph()})
	if err != nil {
		t.Fatal(err)
	}
	return service
}

func testGraph() Graph {
	return Graph{
		Manifest: map[string]any{"commit": "abc123", "profile": "test"},
		Nodes: []Node{
			{
				ID: "dataset:raw", Kind: "dataset",
				Data: map[string]any{"id": "dataset:raw", "kind": "dataset", "name": "raw"},
			},
			{
				ID: "job:transform", Kind: "job",
				Data: map[string]any{
					"id": "job:transform", "kind": "job", "name": "transform",
				},
			},
			{
				ID: "dataset:engagement", Kind: "dataset",
				Data: map[string]any{
					"id": "dataset:engagement", "kind": "dataset",
					"name":   "engagement",
					"fields": []any{map[string]any{"name": "engagement_id"}},
				},
			},
		},
		Edges: []Edge{
			{
				ID: "edge:raw-transform", Source: "dataset:raw",
				Target: "job:transform", Kind: "input",
				Data: map[string]any{
					"id": "edge:raw-transform", "source": "dataset:raw",
					"target": "job:transform", "kind": "input",
				},
			},
			{
				ID: "edge:transform-engagement", Source: "job:transform",
				Target: "dataset:engagement", Kind: "output",
				Data: map[string]any{
					"id": "edge:transform-engagement", "source": "job:transform",
					"target": "dataset:engagement", "kind": "output",
				},
			},
		},
	}
}

func nodeIDs(nodes []Node) []string {
	ids := make([]string, len(nodes))
	for index, node := range nodes {
		ids[index] = node.ID
	}
	return ids
}

func equalStrings(left, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}
