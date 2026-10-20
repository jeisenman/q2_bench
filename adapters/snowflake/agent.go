package snowflake

import (
	"context"
	"database/sql"
	"fmt"

	"github.com/jeisenman/q2_bench/domain"
	"github.com/jeisenman/q2_bench/ports"
)

const agentRunSQL = "SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(?, ?, ?) AS response"

// Agent runs versioned Snowflake Cortex Agents through DATA_AGENT_RUN.
type Agent struct {
	settings Settings
	secrets  ports.SecretProvider
	open     databaseOpener
}

// NewAgent constructs a live Cortex Agent adapter with call-time secrets.
func NewAgent(settings Settings, secrets ports.SecretProvider) (*Agent, error) {
	if err := validateSettings(settings); err != nil {
		return nil, err
	}
	if secrets == nil {
		return nil, fmt.Errorf("Snowflake Cortex Agent requires a secret provider")
	}
	return &Agent{settings: settings, secrets: secrets, open: openDatabase}, nil
}

// Environment returns the Snowflake environment served by this adapter.
func (a *Agent) Environment() domain.Environment {
	return a.settings.Environment
}

// Run executes the requested immutable or live agent version.
func (a *Agent) Run(
	ctx context.Context,
	request ports.CortexAgentRequest,
) (ports.CortexAgentResponse, error) {
	if err := request.Validate(); err != nil {
		return ports.CortexAgentResponse{}, err
	}
	var response sql.NullString
	row := queryRow(
		ctx, a.settings, a.secrets, a.open, agentRunSQL,
		request.QualifiedName(), request.RequestBody, request.CreateThreadIfNotPresent,
	)
	if err := row.Scan(&response); err != nil {
		return ports.CortexAgentResponse{}, fmt.Errorf(
			"Cortex Agent %s run failed: %w",
			a.Environment(),
			err,
		)
	}
	if !response.Valid || response.String == "" {
		return ports.CortexAgentResponse{}, fmt.Errorf(
			"Cortex Agent %q returned no response",
			request.QualifiedName(),
		)
	}
	return ports.CortexAgentResponse{
		AgentName: request.AgentName, Version: request.Version,
		Response: response.String, Environment: a.Environment(), Recorded: false,
	}, nil
}

var _ ports.CortexAgent = (*Agent)(nil)
