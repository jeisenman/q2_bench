package mcpapi

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/jeisenman/q2_bench/adapters/snowflake"
	"github.com/jeisenman/q2_bench/domain"
	"github.com/jeisenman/q2_bench/ports"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

const cortexRequestTimeout = 60 * time.Second

type cortexCompleteInput struct {
	Model       string  `json:"model" jsonschema:"Snowflake Cortex model name"`
	Prompt      string  `json:"prompt" jsonschema:"Prompt sent to Cortex"`
	Temperature float64 `json:"temperature,omitempty" jsonschema:"Sampling temperature from 0.0 through 1.0"`
	Environment string  `json:"environment,omitempty" jsonschema:"dev, stage, prod, or sandbox"`
}

type cortexTokenInput struct {
	Model       string `json:"model" jsonschema:"Snowflake Cortex model name"`
	Text        string `json:"text" jsonschema:"Text to count"`
	Environment string `json:"environment,omitempty" jsonschema:"dev, stage, prod, or sandbox"`
}

type cortexAgentInput struct {
	AgentName                string `json:"agent_name" jsonschema:"Fully qualified Snowflake Cortex Agent name"`
	Version                  string `json:"version,omitempty" jsonschema:"VERSION$N, alias, LIVE, DEFAULT, LAST, or FIRST"`
	RequestBody              string `json:"request_body" jsonschema:"JSON request body passed to DATA_AGENT_RUN"`
	CreateThreadIfNotPresent bool   `json:"create_thread_if_not_present,omitempty" jsonschema:"Create a thread when request_body has no thread_id"`
	Environment              string `json:"environment,omitempty" jsonschema:"dev, stage, prod, or sandbox"`
}

type cortexResolver func(domain.Environment) (ports.CortexInference, error)
type cortexAgentResolver func(domain.Environment) (ports.CortexAgent, error)

type warehouseAPI struct {
	resolve      cortexResolver
	resolveAgent cortexAgentResolver
}

func registerWarehouse(server *mcp.Server) {
	api := &warehouseAPI{resolve: resolveCortex, resolveAgent: resolveCortexAgent}
	mcp.AddTool(server, &mcp.Tool{
		Name:        "run_cortex_complete",
		Description: "Run one bounded Snowflake Cortex completion. Live environments are non-deterministic; sandbox responses are recorded replays.",
	}, api.runCortexComplete)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "count_cortex_tokens",
		Description: "Count tokens with Snowflake Cortex without running inference. Sandbox counts come from a recording.",
	}, api.countCortexTokens)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "run_cortex_agent",
		Description: "Run one explicitly selected Snowflake Cortex Agent version. Sandbox responses are recorded replays.",
	}, api.runCortexAgent)
}

func (a *warehouseAPI) runCortexComplete(
	ctx context.Context,
	_ *mcp.CallToolRequest,
	input cortexCompleteInput,
) (*mcp.CallToolResult, map[string]any, error) {
	environment, err := requestedEnvironment(input.Environment)
	if err != nil {
		return nil, nil, err
	}
	request := ports.CortexRequest{
		Model: input.Model, Prompt: input.Prompt, Temperature: input.Temperature,
	}
	if err := request.Validate(); err != nil {
		return nil, nil, err
	}
	cortex, err := a.resolve(environment)
	if err != nil {
		return nil, nil, err
	}
	bounded, cancel := context.WithTimeout(ctx, cortexRequestTimeout)
	defer cancel()
	response, err := cortex.Complete(bounded, request)
	if err != nil {
		return nil, nil, err
	}
	return nil, map[string]any{
		"environment":   response.Environment,
		"model":         response.Model,
		"completion":    response.Text,
		"recorded":      response.Recorded,
		"deterministic": response.Recorded,
	}, nil
}

func (a *warehouseAPI) countCortexTokens(
	ctx context.Context,
	_ *mcp.CallToolRequest,
	input cortexTokenInput,
) (*mcp.CallToolResult, map[string]any, error) {
	environment, err := requestedEnvironment(input.Environment)
	if err != nil {
		return nil, nil, err
	}
	request := ports.CortexRequest{Model: input.Model, Prompt: input.Text}
	if err := request.Validate(); err != nil {
		return nil, nil, err
	}
	cortex, err := a.resolve(environment)
	if err != nil {
		return nil, nil, err
	}
	bounded, cancel := context.WithTimeout(ctx, cortexRequestTimeout)
	defer cancel()
	count, err := cortex.CountTokens(bounded, input.Model, input.Text)
	if err != nil {
		return nil, nil, err
	}
	return nil, map[string]any{
		"environment":   environment,
		"model":         input.Model,
		"token_count":   count,
		"recorded":      environment.Deterministic(),
		"deterministic": environment.Deterministic(),
	}, nil
}

func (a *warehouseAPI) runCortexAgent(
	ctx context.Context,
	_ *mcp.CallToolRequest,
	input cortexAgentInput,
) (*mcp.CallToolResult, map[string]any, error) {
	environment, err := requestedEnvironment(input.Environment)
	if err != nil {
		return nil, nil, err
	}
	request := ports.CortexAgentRequest{
		AgentName: input.AgentName, Version: input.Version,
		RequestBody:              input.RequestBody,
		CreateThreadIfNotPresent: input.CreateThreadIfNotPresent,
	}
	if err := request.Validate(); err != nil {
		return nil, nil, err
	}
	agent, err := a.resolveAgent(environment)
	if err != nil {
		return nil, nil, err
	}
	bounded, cancel := context.WithTimeout(ctx, cortexRequestTimeout)
	defer cancel()
	response, err := agent.Run(bounded, request)
	if err != nil {
		return nil, nil, err
	}
	version := response.Version
	if version == "" {
		version = "DEFAULT"
	}
	return nil, map[string]any{
		"environment":   response.Environment,
		"agent_name":    response.AgentName,
		"version":       version,
		"response":      response.Response,
		"recorded":      response.Recorded,
		"deterministic": response.Recorded,
	}, nil
}

func requestedEnvironment(requested string) (domain.Environment, error) {
	name := strings.TrimSpace(requested)
	if name == "" {
		name = strings.TrimSpace(os.Getenv("WAREHOUSE_ENVIRONMENT"))
	}
	if name == "" {
		name = string(domain.EnvironmentSandbox)
	}
	return domain.ParseEnvironment(name)
}

func resolveCortex(environment domain.Environment) (ports.CortexInference, error) {
	if environment == domain.EnvironmentSandbox {
		return snowflake.LoadRecordedCortex(
			strings.TrimSpace(os.Getenv("WAREHOUSE_SANDBOX_CORTEX_RECORDINGS")),
		)
	}
	settings, err := snowflake.LoadSettings(environment)
	if err != nil {
		return nil, err
	}
	cortex, err := snowflake.NewCortex(settings, snowflake.EnvironmentSecrets{})
	if err != nil {
		return nil, fmt.Errorf("configure Cortex %s: %w", environment, err)
	}
	return cortex, nil
}

func resolveCortexAgent(environment domain.Environment) (ports.CortexAgent, error) {
	if environment == domain.EnvironmentSandbox {
		return snowflake.LoadRecordedAgent(
			strings.TrimSpace(os.Getenv("WAREHOUSE_SANDBOX_CORTEX_AGENT_RECORDINGS")),
		)
	}
	settings, err := snowflake.LoadSettings(environment)
	if err != nil {
		return nil, err
	}
	agent, err := snowflake.NewAgent(settings, snowflake.EnvironmentSecrets{})
	if err != nil {
		return nil, fmt.Errorf("configure Cortex Agent %s: %w", environment, err)
	}
	return agent, nil
}
