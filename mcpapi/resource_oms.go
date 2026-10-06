package mcpapi

import (
	"context"
	"fmt"

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

func registerResourceDiscovery(server *mcp.Server) error {
	config, err := rdadapter.ConfigFromEnvironment()
	if err != nil {
		return err
	}
	source := rdadapter.APISource{Config: config}
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
		records, err := source.Lookup(ctx, identifier)
		if err != nil {
			return nil, nil, err
		}
		return nil, map[string]any{
			"identifier_kind":  input.IdentifierKind,
			"identifier_value": input.IdentifierValue,
			"count":            len(records), "records": records,
		}, nil
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
		records, err := source.LookupBatch(ctx, identifiers)
		if err != nil {
			return nil, nil, err
		}
		results := make([]map[string]any, len(records))
		for index, values := range records {
			results[index] = map[string]any{
				"identifier_kind":  input.Identifiers[index].IdentifierKind,
				"identifier_value": input.Identifiers[index].IdentifierValue,
				"count":            len(values), "records": values,
			}
		}
		return nil, map[string]any{"count": len(results), "results": results}, nil
	})
	return nil
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
