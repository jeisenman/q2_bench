// Package codexcli executes leaf agents through the Codex command line.
package codexcli

import (
	"bytes"
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/jeisenman/q2_bench/domain"
)

// Runtime executes tool-free leaf agent definitions.
type Runtime struct {
	Executable string
	CodexHome  string
}

// Run executes one model-backed request.
func (r Runtime) Run(
	ctx context.Context,
	definition domain.AgentDefinition,
	request domain.AgentRequest,
) (domain.AgentResult, error) {
	if err := validateDefinition(definition); err != nil {
		return domain.AgentResult{}, err
	}
	if err := request.Validate(); err != nil {
		return domain.AgentResult{}, err
	}
	home := r.CodexHome
	if home == "" {
		home = os.Getenv("CODEX_HOME")
	}
	if info, err := os.Stat(home); err != nil || !info.IsDir() {
		return domain.AgentResult{}, fmt.Errorf(
			"CODEX_HOME must reference an initialized Codex directory",
		)
	}
	configPath := filepath.Join(home, "config.toml")
	if info, err := os.Stat(configPath); err != nil || info.IsDir() {
		return domain.AgentResult{}, fmt.Errorf("Codex configuration is missing: %s", configPath)
	}
	temporary, err := os.MkdirTemp("", "q2-bench-codex-*")
	if err != nil {
		return domain.AgentResult{}, err
	}
	defer os.RemoveAll(temporary)
	outputPath := filepath.Join(temporary, "output.txt")
	executable := r.Executable
	if executable == "" {
		executable = "codex"
	}
	command := exec.CommandContext(
		ctx,
		executable,
		"--model",
		definition.Model,
		"--sandbox",
		"read-only",
		"--ask-for-approval",
		"never",
		"exec",
		"--skip-git-repo-check",
		"--ephemeral",
		"--output-last-message",
		outputPath,
		"-",
	)
	command.Stdin = strings.NewReader(prompt(definition, request))
	var stderr bytes.Buffer
	command.Stderr = &stderr
	if err := command.Run(); err != nil {
		return domain.AgentResult{}, fmt.Errorf(
			"Codex exited: %w: %s",
			err,
			strings.TrimSpace(stderr.String()),
		)
	}
	output, err := os.ReadFile(outputPath)
	if os.IsNotExist(err) {
		return domain.AgentResult{}, fmt.Errorf("Codex did not write its final output")
	}
	if err != nil {
		return domain.AgentResult{}, err
	}
	text := strings.TrimSpace(string(output))
	if text == "" {
		return domain.AgentResult{}, fmt.Errorf("agent %q returned no text", definition.Name)
	}
	return domain.AgentResult{
		Output: text, CorrelationID: request.CorrelationID,
		Attributes: domain.Attributes{
			{Name: "model", Value: definition.Model},
			{Name: "runtime", Value: "codex-cli"},
		},
	}, nil
}

func validateDefinition(definition domain.AgentDefinition) error {
	if err := definition.Validate(); err != nil {
		return err
	}
	if definition.CanDelegate {
		return fmt.Errorf("agent %q permits delegation; leaf agents are required", definition.Name)
	}
	if definition.Model == "" {
		return fmt.Errorf("agent %q does not declare a model", definition.Name)
	}
	if len(definition.Tools) > 0 {
		return fmt.Errorf("agent %q declares unsupported tools", definition.Name)
	}
	return nil
}

func prompt(definition domain.AgentDefinition, request domain.AgentRequest) string {
	sections := []string{
		definition.Instructions,
		"Delegation is disabled. Complete this task directly without invoking tools, " +
			"spawning agents, or changing files.",
	}
	if definition.OutputTemplate != "" {
		sections = append(
			sections,
			"Follow this output template and replace every placeholder.",
			definition.OutputTemplate,
		)
	}
	sections = append(sections, "Input evidence:", request.Prompt)
	return strings.Join(sections, "\n\n")
}
