package domain

import (
	"fmt"
	"strings"
)

// Scalar is a bounded attribute value shared by SDK contracts.
type Scalar interface {
	~string | ~int | ~int64 | ~float64 | ~bool
}

// Attribute is one ordered metadata value.
type Attribute struct {
	Name  string
	Value any
}

// Attributes preserves metadata order for deterministic serialization.
type Attributes []Attribute

// BenchmarkIdentity identifies a benchmark in a hierarchical group.
type BenchmarkIdentity struct {
	Group   string
	Name    string
	Version string
	Tags    []string
}

// NewBenchmarkIdentity validates and constructs a benchmark identity.
func NewBenchmarkIdentity(group, name, version string, tags []string) (BenchmarkIdentity, error) {
	if err := requireText(group, "group"); err != nil {
		return BenchmarkIdentity{}, err
	}
	if err := requireText(name, "name"); err != nil {
		return BenchmarkIdentity{}, err
	}
	if version == "" {
		version = "1"
	}
	if err := requireText(version, "version"); err != nil {
		return BenchmarkIdentity{}, err
	}
	return BenchmarkIdentity{
		Group: group, Name: name, Version: version, Tags: append([]string(nil), tags...),
	}, nil
}

// QualifiedName returns the stable group/name identifier.
func (b BenchmarkIdentity) QualifiedName() string {
	return b.Group + "/" + b.Name
}

// ToolDefinition describes an agent capability independently of a tool framework.
type ToolDefinition struct {
	Name        string
	Description string
	InputSchema Attributes
}

// Validate checks required tool metadata.
func (t ToolDefinition) Validate() error {
	if err := requireText(t.Name, "name"); err != nil {
		return err
	}
	return requireText(t.Description, "description")
}

// AgentDefinition describes an agent and the tools a runtime may expose.
type AgentDefinition struct {
	Name           string
	Description    string
	Instructions   string
	Tools          []ToolDefinition
	Version        string
	Model          string
	OutputTemplate string
	CanDelegate    bool
}

// Validate checks required metadata and unique tool names.
func (d AgentDefinition) Validate() error {
	for _, value := range []struct {
		text string
		name string
	}{
		{d.Name, "name"},
		{d.Description, "description"},
		{d.Instructions, "instructions"},
	} {
		if err := requireText(value.text, value.name); err != nil {
			return err
		}
	}
	if d.Version != "" {
		if err := requireText(d.Version, "version"); err != nil {
			return err
		}
	}
	if d.Model != "" && strings.TrimSpace(d.Model) == "" {
		return fmt.Errorf("model must not be empty")
	}
	if d.OutputTemplate != "" && strings.TrimSpace(d.OutputTemplate) == "" {
		return fmt.Errorf("output_template must not be empty")
	}
	names := make(map[string]struct{}, len(d.Tools))
	for _, tool := range d.Tools {
		if err := tool.Validate(); err != nil {
			return fmt.Errorf("tool %q: %w", tool.Name, err)
		}
		if _, exists := names[tool.Name]; exists {
			return fmt.Errorf("agent %q contains duplicate tool names", d.Name)
		}
		names[tool.Name] = struct{}{}
	}
	return nil
}

// AgentRequest represents one framework-neutral request.
type AgentRequest struct {
	Prompt        string
	CorrelationID string
	Attributes    Attributes
}

// Validate checks required request values.
func (r AgentRequest) Validate() error {
	if err := requireText(r.Prompt, "prompt"); err != nil {
		return err
	}
	return requireText(r.CorrelationID, "correlation_id")
}

// AgentResult contains deterministic output metadata returned by a runtime.
type AgentResult struct {
	Output        string
	CorrelationID string
	ToolCalls     []string
	Attributes    Attributes
}

// Validate checks result correlation.
func (r AgentResult) Validate() error {
	return requireText(r.CorrelationID, "correlation_id")
}

func requireText(value, fieldName string) error {
	if strings.TrimSpace(value) == "" {
		return fmt.Errorf("%s must not be empty", fieldName)
	}
	return nil
}
