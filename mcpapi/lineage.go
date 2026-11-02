package mcpapi

import (
	"context"
	"maps"
	"os"
	"strings"

	lineageworkflow "github.com/jeisenman/q2_bench/workflows/lineage"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

type lineageSearchInput struct {
	Query string `json:"query"`
	Limit int    `json:"limit,omitempty"`
}

type lineageTraversalInput struct {
	NodeID string `json:"node_id"`
	Depth  int    `json:"depth,omitempty"`
	Limit  int    `json:"limit,omitempty"`
}

type lineageWalkInput struct {
	NodeID    string
	Depth     int
	Limit     int
	Direction lineageworkflow.Direction
}

type lineageNodeInput struct {
	NodeID string `json:"node_id"`
}

type lineageHistoryInput struct {
	NodeID string `json:"node_id"`
	Limit  int    `json:"limit,omitempty"`
}

type lineageAPI struct {
	source lineageworkflow.QuerySource
}

func registerLineage(server *mcp.Server) error {
	if strings.TrimSpace(os.Getenv("LINEAGE_STORE_PATH")) != "" {
		registerLineageWithSource(server, localLineageStore())
		return nil
	}
	source, err := lineageworkflow.JSONSourceFromEnvironment()
	if err != nil {
		return err
	}
	registerLineageWithSource(server, source)
	return nil
}

func registerLineageWithSource(
	server *mcp.Server,
	source lineageworkflow.QuerySource,
) {
	api := &lineageAPI{source: source}
	registerLineageChecks(server, localLineageStore())
	annotations := lineageReadOnlyAnnotations()
	mcp.AddTool(server, &mcp.Tool{
		Name:        "search_lineage_datasets",
		Description: "Search staged datasets, Snowflake tables, and synchronized semantic meaning.",
		Annotations: annotations,
	}, api.search)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "get_lineage_upstream",
		Description: "Traverse bounded upstream jobs and datasets from a lineage node.",
		Annotations: annotations,
	}, api.upstream)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "get_lineage_downstream",
		Description: "Traverse bounded downstream jobs and datasets from a lineage node.",
		Annotations: annotations,
	}, api.downstream)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "get_lineage_transformation",
		Description: "Read schema, locations, transformations, sources, and semantic meaning for one node.",
		Annotations: annotations,
	}, api.transformation)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "get_lineage_change_history",
		Description: "Read versioned creation, change, and removal history for one node.",
		Annotations: annotations,
	}, api.history)
}

func lineageReadOnlyAnnotations() *mcp.ToolAnnotations {
	destructive := false
	return &mcp.ToolAnnotations{
		ReadOnlyHint:    true,
		DestructiveHint: &destructive,
		IdempotentHint:  true,
	}
}

func (a *lineageAPI) service() (*lineageworkflow.Service, error) {
	return lineageworkflow.NewService(a.source)
}

func (a *lineageAPI) search(
	ctx context.Context,
	_ *mcp.CallToolRequest,
	input lineageSearchInput,
) (*mcp.CallToolResult, map[string]any, error) {
	service, err := a.service()
	if err != nil {
		return nil, nil, err
	}
	result, err := service.SearchDatasets(ctx, input.Query, input.Limit)
	if err != nil {
		return nil, nil, err
	}
	datasets := make([]map[string]any, len(result.Nodes))
	for index, node := range result.Nodes {
		datasets[index] = node.SearchSummary()
	}
	return nil, map[string]any{
		"graph": result.Graph.Manifest,
		"count": len(datasets), "datasets": datasets,
	}, nil
}

func (a *lineageAPI) upstream(
	ctx context.Context,
	request *mcp.CallToolRequest,
	input lineageTraversalInput,
) (*mcp.CallToolResult, map[string]any, error) {
	return a.traverse(ctx, request, lineageWalkInput{
		NodeID: input.NodeID, Depth: input.Depth, Limit: input.Limit,
		Direction: lineageworkflow.Upstream,
	})
}

func (a *lineageAPI) downstream(
	ctx context.Context,
	request *mcp.CallToolRequest,
	input lineageTraversalInput,
) (*mcp.CallToolResult, map[string]any, error) {
	return a.traverse(ctx, request, lineageWalkInput{
		NodeID: input.NodeID, Depth: input.Depth, Limit: input.Limit,
		Direction: lineageworkflow.Downstream,
	})
}

func (a *lineageAPI) traverse(
	ctx context.Context,
	_ *mcp.CallToolRequest,
	input lineageWalkInput,
) (*mcp.CallToolResult, map[string]any, error) {
	service, err := a.service()
	if err != nil {
		return nil, nil, err
	}
	result, err := service.Traverse(
		ctx, input.NodeID, input.Direction,
		input.Depth, input.Limit,
	)
	if err != nil {
		return nil, nil, err
	}
	nodes := make([]map[string]any, len(result.Nodes))
	for index, node := range result.Nodes {
		nodes[index] = node.Summary()
	}
	edges := make([]map[string]any, len(result.Edges))
	for index, edge := range result.Edges {
		edges[index] = edge.Output()
	}
	return nil, map[string]any{
		"graph": result.Graph.Manifest, "root": result.Root.Summary(),
		"direction": result.Direction, "depth": result.Depth,
		"truncated": result.Truncated, "nodeCount": len(nodes),
		"edgeCount": len(edges), "nodes": nodes, "edges": edges,
	}, nil
}

func (a *lineageAPI) transformation(
	ctx context.Context,
	_ *mcp.CallToolRequest,
	input lineageNodeInput,
) (*mcp.CallToolResult, map[string]any, error) {
	service, err := a.service()
	if err != nil {
		return nil, nil, err
	}
	graph, node, err := service.TransformationDetails(ctx, input.NodeID)
	if err != nil {
		return nil, nil, err
	}
	return nil, map[string]any{
		"graph": graph.Manifest, "node": lineageNodeDetails(node),
	}, nil
}

func (a *lineageAPI) history(
	ctx context.Context,
	_ *mcp.CallToolRequest,
	input lineageHistoryInput,
) (*mcp.CallToolResult, map[string]any, error) {
	service, err := a.service()
	if err != nil {
		return nil, nil, err
	}
	revisions, err := service.ChangeHistory(ctx, input.NodeID, input.Limit)
	if err != nil {
		return nil, nil, err
	}
	output := make([]map[string]any, len(revisions))
	for index, revision := range revisions {
		var node any
		if revision.Node != nil {
			node = revision.Node.Summary()
		}
		output[index] = map[string]any{
			"graph":       revision.Graph.Manifest,
			"changeType":  revision.ChangeType,
			"present":     revision.Node != nil,
			"contentHash": revision.ContentHash,
			"node":        node,
		}
	}
	return nil, map[string]any{
		"nodeId": input.NodeID, "count": len(output), "revisions": output,
	}, nil
}

func lineageNodeDetails(node lineageworkflow.Node) map[string]any {
	details := maps.Clone(node.Data)
	if details == nil {
		details = map[string]any{}
	}
	details["contentHash"] = node.ContentHash()
	return details
}
