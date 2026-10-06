package mcpapi

import (
	"context"
	"encoding/json"
	"os"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func registerProdSupportResources(server *mcp.Server, api *prodSupportAPI) {
	addTextResource(
		server,
		"agent://prod-support/definition",
		"prod-support definition",
		"Deterministic production Airflow failure investigation and reporting.",
	)
	addTextResource(
		server,
		"agent://prod-support/follow-up/definition",
		"prod-support follow-up definition",
		"Approval-gated exact Airflow retry execution.",
	)
	server.AddResource(&mcp.Resource{
		URI: "agent://prod-support/omissions", Name: "prod-support omission settings",
		Description: "Configured Data Internal omission groups.", MIMEType: "application/json",
	}, func(
		_ context.Context,
		_ *mcp.ReadResourceRequest,
	) (*mcp.ReadResourceResult, error) {
		values, err := api.readOmissions()
		if err != nil {
			return nil, err
		}
		content, err := json.MarshalIndent(map[string]any{
			"path": api.omissionsPath, "data_internal_omissions": values,
		}, "", "  ")
		if err != nil {
			return nil, err
		}
		return textResource("agent://prod-support/omissions", "application/json", string(content)), nil
	})
	server.AddResource(&mcp.Resource{
		URI: "support://prod-support/updates", Name: "genuine production-support updates",
		Description: "Validated read-only updates from pl-data-plugins.",
		MIMEType:    "application/json",
	}, func(
		_ context.Context,
		_ *mcp.ReadResourceRequest,
	) (*mcp.ReadResourceResult, error) {
		content, err := os.ReadFile(api.updatesPath)
		if err != nil {
			return nil, err
		}
		var updates []map[string]any
		if err := json.Unmarshal(content, &updates); err != nil {
			return nil, err
		}
		encoded, err := json.MarshalIndent(updates, "", "  ")
		if err != nil {
			return nil, err
		}
		return textResource(
			"support://prod-support/updates",
			"application/json",
			string(encoded),
		), nil
	})
	server.AddPrompt(&mcp.Prompt{
		Name: "prod_support_request", Description: "Prepare a production-support request.",
		Arguments: []*mcp.PromptArgument{{
			Name: "request", Description: "The production-support request.", Required: true,
		}},
	}, func(
		_ context.Context,
		request *mcp.GetPromptRequest,
	) (*mcp.GetPromptResult, error) {
		value := request.Params.Arguments["request"]
		return &mcp.GetPromptResult{
			Description: "Production-support investigation request.",
			Messages: []*mcp.PromptMessage{{
				Role: mcp.Role("user"),
				Content: &mcp.TextContent{
					Text: "Investigate production Airflow failures with exact evidence. Request: " + value,
				},
			}},
		}, nil
	})
}

func addTextResource(server *mcp.Server, uri, name, content string) {
	server.AddResource(&mcp.Resource{
		URI: uri, Name: name, MIMEType: "text/plain",
	}, func(
		_ context.Context,
		_ *mcp.ReadResourceRequest,
	) (*mcp.ReadResourceResult, error) {
		return textResource(uri, "text/plain", content), nil
	})
}

func textResource(uri, mimeType, content string) *mcp.ReadResourceResult {
	return &mcp.ReadResourceResult{Contents: []*mcp.ResourceContents{{
		URI: uri, MIMEType: mimeType, Text: content,
	}}}
}
