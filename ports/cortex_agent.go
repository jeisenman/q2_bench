package ports

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/jeisenman/q2_bench/domain"
)

const (
	// MaxCortexAgentNameBytes bounds the fully qualified agent identifier.
	MaxCortexAgentNameBytes = 512
	// MaxCortexAgentVersionBytes bounds a version or alias selector.
	MaxCortexAgentVersionBytes = 256
	// MaxCortexAgentRequestBytes bounds one agent request body.
	MaxCortexAgentRequestBytes = 100_000
)

// CortexAgentRequest identifies a Snowflake Cortex Agent version and request.
type CortexAgentRequest struct {
	AgentName                string
	Version                  string
	RequestBody              string
	CreateThreadIfNotPresent bool
}

// QualifiedName returns the Snowflake agent name with its optional version.
func (r CortexAgentRequest) QualifiedName() string {
	name := strings.TrimSpace(r.AgentName)
	version := strings.TrimSpace(r.Version)
	if version == "" {
		return name
	}
	return name + "!" + version
}

// Validate checks the request before any provider call.
func (r CortexAgentRequest) Validate() error {
	agentName := strings.TrimSpace(r.AgentName)
	if agentName == "" {
		return fmt.Errorf("agent_name must not be empty")
	}
	if len(agentName) > MaxCortexAgentNameBytes {
		return fmt.Errorf(
			"agent_name must not exceed %d bytes; got %d",
			MaxCortexAgentNameBytes,
			len(agentName),
		)
	}
	if strings.ContainsAny(agentName, "\r\n\t") {
		return fmt.Errorf("agent_name must not contain control whitespace")
	}
	if version := strings.TrimSpace(r.Version); version != "" {
		if len(version) > MaxCortexAgentVersionBytes {
			return fmt.Errorf(
				"version must not exceed %d bytes; got %d",
				MaxCortexAgentVersionBytes,
				len(version),
			)
		}
		if strings.ContainsAny(version, "! \r\n\t") {
			return fmt.Errorf("version must not contain ! or whitespace")
		}
	}
	body := strings.TrimSpace(r.RequestBody)
	if body == "" {
		return fmt.Errorf("request_body must not be empty")
	}
	if len(body) > MaxCortexAgentRequestBytes {
		return fmt.Errorf(
			"request_body must not exceed %d bytes; got %d",
			MaxCortexAgentRequestBytes,
			len(body),
		)
	}
	var decoded map[string]json.RawMessage
	if err := json.Unmarshal([]byte(body), &decoded); err != nil {
		return fmt.Errorf("request_body must be a JSON object: %w", err)
	}
	if decoded == nil {
		return fmt.Errorf("request_body must be a JSON object")
	}
	if value, exists := decoded["stream"]; exists {
		var stream bool
		if err := json.Unmarshal(value, &stream); err != nil {
			return fmt.Errorf("request_body stream must be a boolean: %w", err)
		}
		if stream {
			return fmt.Errorf("request_body stream must be false for DATA_AGENT_RUN")
		}
	}
	return nil
}

// CortexAgentResponse is one non-streaming Snowflake Cortex Agent response.
type CortexAgentResponse struct {
	AgentName   string
	Version     string
	Response    string
	Environment domain.Environment
	Recorded    bool
}

// CortexAgent runs versioned Snowflake Cortex Agents.
type CortexAgent interface {
	Environment() domain.Environment
	Run(context.Context, CortexAgentRequest) (CortexAgentResponse, error)
}
