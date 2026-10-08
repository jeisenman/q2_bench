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

type recording struct {
	Model       string  `json:"model"`
	Prompt      string  `json:"prompt"`
	Temperature float64 `json:"temperature"`
	Text        string  `json:"text"`
	TokenCount  int     `json:"token_count"`
}

type recordingIdentity struct {
	Model       string  `json:"model"`
	Prompt      string  `json:"prompt"`
	Temperature float64 `json:"temperature"`
}

// RecordedCortex deterministically replays previously captured responses.
type RecordedCortex struct {
	recordings map[string]recording
}

// LoadRecordedCortex loads every JSON recording in a directory.
func LoadRecordedCortex(root string) (*RecordedCortex, error) {
	if root == "" {
		return nil, fmt.Errorf(
			"sandbox Cortex requires WAREHOUSE_SANDBOX_CORTEX_RECORDINGS",
		)
	}
	entries, err := os.ReadDir(root)
	if err != nil {
		return nil, fmt.Errorf("read Cortex recording directory %q: %w", root, err)
	}
	names := make([]string, 0, len(entries))
	for _, entry := range entries {
		if !entry.IsDir() && filepath.Ext(entry.Name()) == ".json" {
			names = append(names, entry.Name())
		}
	}
	sort.Strings(names)
	recordings := make(map[string]recording, len(names))
	for _, name := range names {
		path := filepath.Join(root, name)
		item, err := readRecording(path)
		if err != nil {
			return nil, err
		}
		key, err := recordingKey(ports.CortexRequest{
			Model: item.Model, Prompt: item.Prompt, Temperature: item.Temperature,
		})
		if err != nil {
			return nil, fmt.Errorf("%s: %w", path, err)
		}
		recordings[key] = item
	}
	return &RecordedCortex{recordings: recordings}, nil
}

// Environment returns the deterministic sandbox environment.
func (*RecordedCortex) Environment() domain.Environment {
	return domain.EnvironmentSandbox
}

// Complete returns a captured response or fails when the request was not recorded.
func (c *RecordedCortex) Complete(
	_ context.Context,
	request ports.CortexRequest,
) (ports.CortexResponse, error) {
	key, err := recordingKey(request)
	if err != nil {
		return ports.CortexResponse{}, err
	}
	item, exists := c.recordings[key]
	if !exists {
		return ports.CortexResponse{}, fmt.Errorf(
			"no recorded Cortex response for %q (key %s)",
			request.Model,
			key,
		)
	}
	return ports.CortexResponse{
		Text: item.Text, Model: item.Model,
		Environment: domain.EnvironmentSandbox, Recorded: true,
	}, nil
}

// CountTokens returns the token count captured for the same model and text.
func (c *RecordedCortex) CountTokens(
	ctx context.Context,
	model string,
	text string,
) (int, error) {
	key, err := recordingKey(ports.CortexRequest{Model: model, Prompt: text})
	if err != nil {
		return 0, err
	}
	item, exists := c.recordings[key]
	if !exists {
		return 0, fmt.Errorf("no recorded token count for %q (key %s)", model, key)
	}
	return item.TokenCount, nil
}

func recordingKey(request ports.CortexRequest) (string, error) {
	if err := request.Validate(); err != nil {
		return "", err
	}
	payload, err := json.Marshal(recordingIdentity{
		Model: request.Model, Prompt: request.Prompt, Temperature: request.Temperature,
	})
	if err != nil {
		return "", fmt.Errorf("encode Cortex recording identity: %w", err)
	}
	digest := sha256.Sum256(payload)
	return hex.EncodeToString(digest[:8]), nil
}

func readRecording(path string) (recording, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return recording{}, fmt.Errorf("read Cortex recording %q: %w", path, err)
	}
	var item recording
	if err := json.Unmarshal(content, &item); err != nil {
		return recording{}, fmt.Errorf("decode Cortex recording %q: %w", path, err)
	}
	if err := (ports.CortexRequest{
		Model: item.Model, Prompt: item.Prompt, Temperature: item.Temperature,
	}).Validate(); err != nil {
		return recording{}, fmt.Errorf("%s: %w", path, err)
	}
	if item.Text == "" {
		return recording{}, fmt.Errorf("%s: text must not be empty", path)
	}
	if item.TokenCount < 0 {
		return recording{}, fmt.Errorf("%s: token_count must not be negative", path)
	}
	return item, nil
}

var _ ports.CortexInference = (*RecordedCortex)(nil)
