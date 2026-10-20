package snowflake

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"

	"github.com/jeisenman/q2_bench/domain"
	"github.com/jeisenman/q2_bench/ports"
)

type agentRecording struct {
	AgentName                string `json:"agent_name"`
	Version                  string `json:"version"`
	RequestBody              string `json:"request_body"`
	CreateThreadIfNotPresent bool   `json:"create_thread_if_not_present"`
	Response                 string `json:"response"`
}

// RecordedAgent deterministically replays captured Cortex Agent responses.
type RecordedAgent struct {
	recordings map[string]agentRecording
}

// LoadRecordedAgent loads every JSON recording in a directory.
func LoadRecordedAgent(root string) (*RecordedAgent, error) {
	if root == "" {
		return nil, fmt.Errorf(
			"sandbox Cortex Agents require WAREHOUSE_SANDBOX_CORTEX_AGENT_RECORDINGS",
		)
	}
	entries, err := os.ReadDir(root)
	if err != nil {
		return nil, fmt.Errorf("read Cortex Agent recording directory %q: %w", root, err)
	}
	names := make([]string, 0, len(entries))
	for _, entry := range entries {
		if !entry.IsDir() && filepath.Ext(entry.Name()) == ".json" {
			names = append(names, entry.Name())
		}
	}
	sort.Strings(names)
	recordings := make(map[string]agentRecording, len(names))
	for _, name := range names {
		path := filepath.Join(root, name)
		item, err := readAgentRecording(path)
		if err != nil {
			return nil, err
		}
		key, err := agentRecordingKey(agentRequest(item))
		if err != nil {
			return nil, fmt.Errorf("%s: %w", path, err)
		}
		if _, exists := recordings[key]; exists {
			return nil, fmt.Errorf("%s: duplicate request identity %s", path, key)
		}
		recordings[key] = item
	}
	return &RecordedAgent{recordings: recordings}, nil
}

// Environment returns the deterministic sandbox environment.
func (*RecordedAgent) Environment() domain.Environment {
	return domain.EnvironmentSandbox
}

// Run returns a captured response or fails when the request was not recorded.
func (a *RecordedAgent) Run(
	_ context.Context,
	request ports.CortexAgentRequest,
) (ports.CortexAgentResponse, error) {
	key, err := agentRecordingKey(request)
	if err != nil {
		return ports.CortexAgentResponse{}, err
	}
	item, exists := a.recordings[key]
	if !exists {
		return ports.CortexAgentResponse{}, fmt.Errorf(
			"no recorded Cortex Agent response for %q (key %s)",
			request.QualifiedName(),
			key,
		)
	}
	return ports.CortexAgentResponse{
		AgentName: request.AgentName, Version: request.Version,
		Response: item.Response, Environment: domain.EnvironmentSandbox, Recorded: true,
	}, nil
}

func agentRequest(item agentRecording) ports.CortexAgentRequest {
	return ports.CortexAgentRequest{
		AgentName: item.AgentName, Version: item.Version,
		RequestBody:              item.RequestBody,
		CreateThreadIfNotPresent: item.CreateThreadIfNotPresent,
	}
}

func agentRecordingKey(request ports.CortexAgentRequest) (string, error) {
	if err := request.Validate(); err != nil {
		return "", err
	}
	payload, err := json.Marshal(struct {
		AgentName                string `json:"agent_name"`
		Version                  string `json:"version"`
		RequestBody              string `json:"request_body"`
		CreateThreadIfNotPresent bool   `json:"create_thread_if_not_present"`
	}{
		AgentName: request.AgentName, Version: request.Version,
		RequestBody:              request.RequestBody,
		CreateThreadIfNotPresent: request.CreateThreadIfNotPresent,
	})
	if err != nil {
		return "", fmt.Errorf("encode Cortex Agent recording identity: %w", err)
	}
	digest := sha256.Sum256(payload)
	return hex.EncodeToString(digest[:8]), nil
}

func readAgentRecording(path string) (agentRecording, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return agentRecording{}, fmt.Errorf("read Cortex Agent recording %q: %w", path, err)
	}
	var item agentRecording
	if err := json.Unmarshal(content, &item); err != nil {
		return agentRecording{}, fmt.Errorf("decode Cortex Agent recording %q: %w", path, err)
	}
	if err := agentRequest(item).Validate(); err != nil {
		return agentRecording{}, fmt.Errorf("%s: %w", path, err)
	}
	if item.Response == "" || !json.Valid([]byte(item.Response)) {
		return agentRecording{}, fmt.Errorf("%s: response must be valid JSON", path)
	}
	return item, nil
}

var _ ports.CortexAgent = (*RecordedAgent)(nil)
