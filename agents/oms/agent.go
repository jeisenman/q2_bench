package oms

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/jeisenman/q2_bench/domain"
)

// QuerySource executes read-only KQL against a workspace.
type QuerySource interface {
	Query(context.Context, Workspace, Query) (QueryResult, error)
}

// LogSink appends custom records to a workspace.
type LogSink interface {
	Write(context.Context, Workspace, LogRecord) error
}

// Agent coordinates OMS operations through injected ports.
type Agent struct {
	QuerySource           QuerySource
	LogSink               LogSink
	AllowWrites           bool
	AllowProductionWrites bool
}

// Definition returns immutable OMS agent metadata.
func (a Agent) Definition() domain.AgentDefinition {
	return domain.AgentDefinition{
		Name: "oms-agent", Version: "1",
		Description:  "Query or append records to an explicitly selected OMS workspace.",
		Instructions: "Require an environment, region, and operation; writes require authorization.",
		Tools: []domain.ToolDefinition{
			{Name: "QueryOms", Description: "Run bounded KQL against one OMS workspace."},
			{Name: "WriteOmsLog", Description: "Append one authorized custom OMS record."},
		},
	}
}

// Query executes one read-only query.
func (a Agent) Query(
	ctx context.Context,
	environment Environment,
	region Region,
	query Query,
) (QueryResult, error) {
	if a.QuerySource == nil {
		return QueryResult{}, fmt.Errorf("OMS query source must not be nil")
	}
	if err := query.Validate(); err != nil {
		return QueryResult{}, err
	}
	workspace, err := ResolveWorkspace(environment, region)
	if err != nil {
		return QueryResult{}, err
	}
	return a.QuerySource.Query(ctx, workspace, query)
}

// WriteLog appends one custom record after enforcing mutation policy.
func (a Agent) WriteLog(
	ctx context.Context,
	environment Environment,
	region Region,
	record LogRecord,
) error {
	if !a.AllowWrites {
		return fmt.Errorf("OMS writes are disabled")
	}
	if environment == Production && !a.AllowProductionWrites {
		return fmt.Errorf("production OMS writes require explicit authorization")
	}
	if a.LogSink == nil {
		return fmt.Errorf("OMS log sink must not be nil")
	}
	if err := record.Validate(); err != nil {
		return err
	}
	workspace, err := ResolveWorkspace(environment, region)
	if err != nil {
		return err
	}
	return a.LogSink.Write(ctx, workspace, record)
}

// Run executes a structured query or log-write request.
func (a Agent) Run(
	ctx context.Context,
	request domain.AgentRequest,
) (domain.AgentResult, error) {
	if err := request.Validate(); err != nil {
		return domain.AgentResult{}, err
	}
	attributes, err := uniqueAttributes(request.Attributes)
	if err != nil {
		return domain.AgentResult{}, err
	}
	environment, err := parseEnvironment(attributes)
	if err != nil {
		return domain.AgentResult{}, err
	}
	region, err := parseRegion(attributes)
	if err != nil {
		return domain.AgentResult{}, err
	}
	operation, err := textAttribute(attributes, "operation")
	if err != nil {
		return domain.AgentResult{}, err
	}
	workspace, err := ResolveWorkspace(environment, region)
	if err != nil {
		return domain.AgentResult{}, err
	}
	var output string
	var toolCalls []string
	switch operation {
	case "query":
		timespan, attributeErr := textAttribute(attributes, "timespan")
		if attributeErr != nil {
			return domain.AgentResult{}, attributeErr
		}
		result, queryErr := a.Query(
			ctx,
			environment,
			region,
			Query{KQL: request.Prompt, Timespan: timespan},
		)
		if queryErr != nil {
			return domain.AgentResult{}, queryErr
		}
		encoded, marshalErr := json.Marshal(result)
		if marshalErr != nil {
			return domain.AgentResult{}, fmt.Errorf("encode OMS query result: %w", marshalErr)
		}
		output = string(encoded)
		toolCalls = []string{"QueryOms"}
	case "write_log":
		logType, attributeErr := textAttribute(attributes, "log_type")
		if attributeErr != nil {
			return domain.AgentResult{}, attributeErr
		}
		writeErr := a.WriteLog(ctx, environment, region, LogRecord{
			LogType: logType,
			Fields: map[string]any{
				"message": request.Prompt, "correlation_id": request.CorrelationID,
				"environment": environment, "region": region,
			},
		})
		if writeErr != nil {
			return domain.AgentResult{}, writeErr
		}
		output = fmt.Sprintf("Wrote one %s record to %s.", logType, workspace.Name)
		toolCalls = []string{"WriteOmsLog"}
	default:
		return domain.AgentResult{}, fmt.Errorf("operation must be 'query' or 'write_log'")
	}
	return domain.AgentResult{
		Output: output, CorrelationID: request.CorrelationID, ToolCalls: toolCalls,
		Attributes: domain.Attributes{
			{Name: "environment", Value: string(environment)},
			{Name: "region", Value: string(region)},
			{Name: "workspace", Value: workspace.Name},
		},
	}, nil
}

func uniqueAttributes(attributes domain.Attributes) (map[string]any, error) {
	values := make(map[string]any, len(attributes))
	for _, attribute := range attributes {
		if _, exists := values[attribute.Name]; exists {
			return nil, fmt.Errorf("request attribute %q is duplicated", attribute.Name)
		}
		values[attribute.Name] = attribute.Value
	}
	return values, nil
}

func textAttribute(attributes map[string]any, name string) (string, error) {
	value, ok := attributes[name].(string)
	if !ok || strings.TrimSpace(value) == "" {
		return "", fmt.Errorf("request must include non-empty string attribute %q", name)
	}
	return value, nil
}

func parseEnvironment(attributes map[string]any) (Environment, error) {
	value, err := textAttribute(attributes, "environment")
	if err != nil {
		return "", err
	}
	environment := Environment(value)
	switch environment {
	case Production, Staging, Development:
		return environment, nil
	default:
		return "", fmt.Errorf("environment must be one of: production, staging, development")
	}
}

func parseRegion(attributes map[string]any) (Region, error) {
	value, err := textAttribute(attributes, "region")
	if err != nil {
		return "", err
	}
	region := Region(value)
	switch region {
	case US, CA:
		return region, nil
	default:
		return "", fmt.Errorf("region must be one of: us, ca")
	}
}
