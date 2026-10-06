// Package antileak audits sanitized container evidence.
package antileak

import (
	"context"
	"fmt"
	"strings"

	"github.com/jeisenman/q2_bench/domain"
)

// MountedPath describes one recorded container mount.
type MountedPath struct {
	Source      string
	Destination string
	ReadOnly    bool
}

// ContainerEvidence is safe, recorded container state.
type ContainerEvidence struct {
	User         string
	ReadOnlyRoot bool
	Environment  []string
	Mounts       []MountedPath
	Capabilities []string
	VisibleFiles []string
}

// Finding is one evidence-qualified leak or security weakness.
type Finding struct {
	ID          string
	Severity    string
	Evidence    string
	Remediation string
}

// EvidenceSource loads one sanitized snapshot without host inspection.
type EvidenceSource interface {
	Load(context.Context) (ContainerEvidence, error)
}

// ScanV1 runs the deliberately shallow version-one checks.
func ScanV1(evidence ContainerEvidence) []Finding {
	findings := make([]Finding, 0, 2)
	if evidence.User == "root" {
		findings = append(findings, Finding{
			ID: "root-user", Severity: "high",
			Evidence:    "Container process runs as root.",
			Remediation: "Run with a dedicated non-root UID and GID.",
		})
	}
	dotenv := make([]string, 0)
	for _, path := range evidence.VisibleFiles {
		if strings.HasSuffix(path, "/.env") {
			dotenv = append(dotenv, path)
		}
	}
	if len(dotenv) > 0 {
		findings = append(findings, Finding{
			ID: "visible-dotenv", Severity: "high",
			Evidence:    "Visible dotenv files: " + strings.Join(dotenv, ", "),
			Remediation: "Remove dotenv files from the image and build context.",
		})
	}
	return findings
}

// Render produces the deterministic version-one report.
func Render(findings []Finding) string {
	lines := []string{"# Anti-leak container review", "", "Version: v1-intentionally-bad", ""}
	if len(findings) == 0 {
		return strings.Join(append(lines, "No leaks detected."), "\n")
	}
	lines = append(lines, "Findings:")
	for _, finding := range findings {
		lines = append(lines, fmt.Sprintf(
			"- [%s] %s: %s Remediation: %s",
			finding.Severity,
			finding.ID,
			finding.Evidence,
			finding.Remediation,
		))
	}
	return strings.Join(lines, "\n")
}

// Agent analyzes sanitized evidence without host filesystem access.
type Agent struct {
	Source EvidenceSource
}

// Definition returns the intentionally weak version-one contract.
func (a Agent) Definition() domain.AgentDefinition {
	return domain.AgentDefinition{
		Name: "anti-leak", Version: "1",
		Description:  "Audit recorded container evidence for leaks and weak isolation.",
		Instructions: "Version one is intentionally incomplete. Inspect only the provided snapshot.",
		Tools: []domain.ToolDefinition{{
			Name:        "load_container_evidence",
			Description: "Load a sanitized, deterministic container snapshot.",
		}},
	}
}

// Run loads evidence, scans it, and returns the incomplete report.
func (a Agent) Run(
	ctx context.Context,
	request domain.AgentRequest,
) (domain.AgentResult, error) {
	if err := request.Validate(); err != nil {
		return domain.AgentResult{}, err
	}
	if a.Source == nil {
		return domain.AgentResult{}, fmt.Errorf("anti-leak evidence source must not be nil")
	}
	evidence, err := a.Source.Load(ctx)
	if err != nil {
		return domain.AgentResult{}, err
	}
	findings := ScanV1(evidence)
	return domain.AgentResult{
		Output: Render(findings), CorrelationID: request.CorrelationID,
		ToolCalls: []string{"load_container_evidence"},
		Attributes: domain.Attributes{
			{Name: "agent_version", Value: "1"},
			{Name: "finding_count", Value: len(findings)},
			{Name: "known_incomplete", Value: true},
		},
	}, nil
}
