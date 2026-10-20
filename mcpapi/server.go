// Package mcpapi exposes the Q2 SDK through Model Context Protocol.
package mcpapi

import (
	"context"
	"fmt"
	"net/http"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// Config selects one API surface and its external dependencies.
type Config struct {
	Name              string
	ConfigurationPath string
	UpdatesPath       string
	OmissionsPath     string
}

// NewServer builds one versioned MCP capability server.
func NewServer(config Config) (*mcp.Server, error) {
	if config.Name == "" {
		return nil, fmt.Errorf("MCP server name must not be empty")
	}
	server := mcp.NewServer(&mcp.Implementation{
		Name: config.Name, Version: "1.0.0",
	}, nil)
	switch config.Name {
	case "airflow":
		if err := registerAirflow(server, config); err != nil {
			return nil, err
		}
	case "resource-discovery":
		if err := registerResourceDiscovery(server); err != nil {
			return nil, err
		}
	case "oms":
		registerOMS(server)
	case "remote-data":
		registerRemoteData(server)
	case "warehouse":
		registerWarehouse(server)
	case "cortex":
		registerWarehouse(server)
	case "lineage":
		if err := registerLineage(server); err != nil {
			return nil, err
		}
	case "prod-support":
		if err := registerProdSupport(server, config); err != nil {
			return nil, err
		}
	default:
		return nil, fmt.Errorf("unsupported MCP server %q", config.Name)
	}
	return server, nil
}

// RunStdio serves one MCP server over standard input and output.
func RunStdio(ctx context.Context, server *mcp.Server) error {
	return server.Run(ctx, &mcp.StdioTransport{})
}

// HTTPHandler returns a stateless Streamable HTTP handler.
func HTTPHandler(server *mcp.Server) http.Handler {
	return mcp.NewStreamableHTTPHandler(
		func(*http.Request) *mcp.Server { return server },
		&mcp.StreamableHTTPOptions{Stateless: true},
	)
}
