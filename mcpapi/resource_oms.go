package mcpapi

import (
	"context"
	"fmt"
	"os"
	"strings"

	omsadapter "github.com/jeisenman/q2_bench/adapters/oms"
	rdadapter "github.com/jeisenman/q2_bench/adapters/resourcediscovery"
	omsagent "github.com/jeisenman/q2_bench/agents/oms"
	rdagent "github.com/jeisenman/q2_bench/agents/resourcediscovery"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

type lookupInput struct {
	IdentifierKind  string `json:"identifier_kind"`
	IdentifierValue string `json:"identifier_value"`
}

type lookupBatchInput struct {
	Identifiers []lookupInput `json:"identifiers"`
}

const defaultClientLookupPath = ".codex/skills/resource-discovery/references/client-guuid-lookup.json"

func registerResourceDiscovery(server *mcp.Server) error {
	config, err := rdadapter.ConfigFromEnvironment()
	if err != nil {
		return err
	}
	lookupPath := strings.TrimSpace(os.Getenv("RESOURCE_DISCOVERY_CLIENT_LOOKUP"))
	if lookupPath == "" {
		lookupPath = defaultClientLookupPath
	}
	local, err := rdadapter.NewJSONClientLookupSource(lookupPath)
	if err != nil {
		return err
	}
	agent := rdagent.Agent{Source: rdadapter.IndexedSource{
		Primary:  rdadapter.APISource{Config: config},
		Fallback: local,
	}}
	registerResourceDiscoveryAgent(server, agent)
	return nil
}

func registerResourceDiscoveryAgent(server *mcp.Server, agent rdagent.Agent) {
	mcp.AddTool(server, &mcp.Tool{
		Name:        "lookup_resources",
		Description: "Return every allowlisted Resource Discovery match for one identifier.",
	}, func(
		ctx context.Context,
		_ *mcp.CallToolRequest,
		input lookupInput,
	) (*mcp.CallToolResult, map[string]any, error) {
		identifier := rdagent.Identifier{
			Kind:  rdagent.IdentifierKind(input.IdentifierKind),
			Value: input.IdentifierValue,
		}
		if err := identifier.Validate(); err != nil {
			return nil, nil, err
		}
		search, err := agent.Search(ctx, identifier)
		if err != nil {
			return nil, nil, err
		}
		return nil, searchPayload(search), nil
	})
	mcp.AddTool(server, &mcp.Tool{
		Name:        "lookup_resources_batch",
		Description: "Return ordered Resource Discovery matches for several identifiers.",
	}, func(
		ctx context.Context,
		_ *mcp.CallToolRequest,
		input lookupBatchInput,
	) (*mcp.CallToolResult, map[string]any, error) {
		if len(input.Identifiers) == 0 {
			return nil, nil, fmt.Errorf("identifiers must not be empty")
		}
		identifiers := make([]rdagent.Identifier, len(input.Identifiers))
		for index, item := range input.Identifiers {
			identifiers[index] = rdagent.Identifier{
				Kind: rdagent.IdentifierKind(item.IdentifierKind), Value: item.IdentifierValue,
			}
			if err := identifiers[index].Validate(); err != nil {
				return nil, nil, fmt.Errorf("identifier %d: %w", index, err)
			}
		}
		searches, err := agent.SearchBatch(ctx, identifiers)
		if err != nil {
			return nil, nil, err
		}
		results := make([]map[string]any, len(searches))
		for index, search := range searches {
			results[index] = searchPayload(search)
		}
		return nil, map[string]any{"count": len(results), "results": results}, nil
	})
}

func searchPayload(search rdagent.Search) map[string]any {
	records := make([]map[string]any, len(search.Matches))
	for index, metadata := range search.Matches {
		records[index] = metadata.Record()
	}
	return map[string]any{
		"identifier_kind":  string(search.Identifier.Kind),
		"identifier_value": search.Identifier.Value,
		"status":           string(search.Status()),
		"count":            len(records),
		"records":          records,
	}
}

type omsQueryInput struct {
	Environment string `json:"environment"`
	Region      string `json:"region"`
	KQL         string `json:"kql"`
	Timespan    string `json:"timespan"`
}

func registerOMS(server *mcp.Server) {
	source := omsadapter.LogAnalyticsSource{
		TokenSource: omsadapter.AzureCLITokenSource{},
	}
	mcp.AddTool(server, &mcp.Tool{
		Name:        "query_oms",
		Description: "Run bounded KQL against one allowlisted OMS workspace.",
	}, func(
		ctx context.Context,
		_ *mcp.CallToolRequest,
		input omsQueryInput,
	) (*mcp.CallToolResult, map[string]any, error) {
		workspace, err := omsagent.ResolveWorkspace(
			omsagent.Environment(input.Environment),
			omsagent.Region(input.Region),
		)
		if err != nil {
			return nil, nil, err
		}
		result, err := source.Query(ctx, workspace, omsagent.Query{
			KQL: input.KQL, Timespan: input.Timespan,
		})
		if err != nil {
			return nil, nil, err
		}
		return nil, map[string]any{
			"environment": input.Environment, "region": input.Region,
			"workspace": workspace.Name, "columns": result.Columns, "rows": result.Rows,
		}, nil
	})
}

func regionForOMS(value string) (omsagent.Region, error) {
	switch value {
	case string(omsagent.US):
		return omsagent.US, nil
	case string(omsagent.CA):
		return omsagent.CA, nil
	default:
		return "", fmt.Errorf("region must be us or ca")
	}
}
