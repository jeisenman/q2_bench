package mcpapi

import (
	"context"
	"crypto/sha256"
	"fmt"
	"os"
	"sort"
	"strings"

	"github.com/jeisenman/q2_bench/workflows/prodsupport"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

type dependencyRerunPlanInput struct {
	RerunCandidates []prodsupport.RetryCandidate `json:"rerun_candidates"`
}

type dependencyRerunInput struct {
	Direction       string                       `json:"direction"`
	RerunCandidates []prodsupport.RetryCandidate `json:"rerun_candidates"`
	ValidationURLs  []string                     `json:"validation_urls"`
	CorrelationID   string                       `json:"correlation_id,omitempty"`
	ApprovalID      string                       `json:"approval_id"`
	ApprovedPlanID  string                       `json:"approved_plan_id"`
}

func (a *prodSupportAPI) executeDependencyMode(
	ctx context.Context,
	input followUpInput,
	batches []prodsupport.RetryBatch,
) (*mcp.CallToolResult, map[string]any, error) {
	if strings.TrimSpace(input.ApprovalID) == "" {
		return nil, nil, fmt.Errorf("dependency re-run requires an approval ID")
	}
	states := make([]prodsupport.RetryTaskReference, 0)
	for _, batch := range batches {
		cleared, clearErr := a.airflow.source.ExecuteDependencyRerun(
			ctx,
			batch,
			input.ApprovalID,
		)
		if clearErr != nil {
			return nil, nil, clearErr
		}
		states = append(states, cleared...)
	}
	return nil, map[string]any{
		"task_instances":  states,
		"links":           input.ValidationURLs,
		"validation_urls": input.ValidationURLs,
		"correlation_id":  correlation(input.CorrelationID),
		"approval_id":     input.ApprovalID,
		"plan_id":         dependencyPlanID(states),
		"mode":            "dependency_rerun",
	}, nil
}

func dependencyRerunRequested(direction string) bool {
	normalized := strings.ToLower(strings.ReplaceAll(direction, "-", ""))
	return strings.Contains(normalized, "rerun") &&
		strings.Contains(normalized, "depend")
}

func (a *prodSupportAPI) planDependencyRerun(
	ctx context.Context,
	_ *mcp.CallToolRequest,
	input dependencyRerunPlanInput,
) (*mcp.CallToolResult, map[string]any, error) {
	if err := validateRerunCandidates(input.RerunCandidates); err != nil {
		return nil, nil, err
	}
	batches := prodsupport.RetryBatches(input.RerunCandidates)
	if err := a.preflightFollowUp(ctx, batches); err != nil {
		return nil, nil, err
	}
	planned, err := a.planDependencyBatches(ctx, batches)
	if err != nil {
		return nil, nil, err
	}
	return nil, map[string]any{
		"plan_id":             dependencyPlanID(planned),
		"rerun_candidates":    input.RerunCandidates,
		"task_instances":      planned,
		"task_instance_count": len(planned),
	}, nil
}

func (a *prodSupportAPI) executeDependencyRerun(
	ctx context.Context,
	_ *mcp.CallToolRequest,
	input dependencyRerunInput,
) (*mcp.CallToolResult, map[string]any, error) {
	if strings.TrimSpace(input.ApprovalID) == "" {
		return nil, nil, fmt.Errorf("dependency re-run requires an approval ID")
	}
	if strings.TrimSpace(input.ApprovedPlanID) == "" {
		return nil, nil, fmt.Errorf("dependency re-run requires an approved plan ID")
	}
	if err := requireProductionFollowUp(); err != nil {
		return nil, nil, err
	}
	if err := validateValidationURLs(input.ValidationURLs); err != nil {
		return nil, nil, err
	}
	if err := validateRerunCandidates(input.RerunCandidates); err != nil {
		return nil, nil, err
	}
	selected, err := prodsupport.SelectRetryCandidates(
		input.Direction,
		input.RerunCandidates,
	)
	if err != nil {
		return nil, nil, err
	}
	batches := prodsupport.RetryBatches(selected)
	if err := a.preflightFollowUp(ctx, batches); err != nil {
		return nil, nil, err
	}
	replanned, err := a.planDependencyBatches(ctx, batches)
	if err != nil {
		return nil, nil, err
	}
	replannedID := dependencyPlanID(replanned)
	if replannedID != input.ApprovedPlanID {
		return nil, nil, fmt.Errorf(
			"dependency re-run plan changed: approved %s, current %s",
			input.ApprovedPlanID,
			replannedID,
		)
	}
	states := make([]prodsupport.RetryTaskReference, 0, len(replanned))
	for _, batch := range batches {
		cleared, clearErr := a.airflow.source.ExecuteDependencyRerun(
			ctx,
			batch,
			input.ApprovalID,
		)
		if clearErr != nil {
			return nil, nil, clearErr
		}
		states = append(states, cleared...)
	}
	return nil, map[string]any{
		"task_instances":  states,
		"links":           input.ValidationURLs,
		"validation_urls": input.ValidationURLs,
		"correlation_id":  correlation(input.CorrelationID),
		"approval_id":     input.ApprovalID,
		"plan_id":         replannedID,
	}, nil
}

func (a *prodSupportAPI) planDependencyBatches(
	ctx context.Context,
	batches []prodsupport.RetryBatch,
) ([]prodsupport.RetryTaskReference, error) {
	planned := make([]prodsupport.RetryTaskReference, 0)
	for _, batch := range batches {
		references, err := a.airflow.source.PlanDependencyRerun(ctx, batch)
		if err != nil {
			return nil, err
		}
		planned = append(planned, references...)
	}
	return planned, nil
}

func validateRerunCandidates(candidates []prodsupport.RetryCandidate) error {
	if len(candidates) == 0 {
		return fmt.Errorf("dependency re-run requires at least one candidate")
	}
	numbers := make(map[int]struct{}, len(candidates))
	identities := make(map[string]struct{}, len(candidates))
	for index, candidate := range candidates {
		if candidate.Number < 1 || strings.TrimSpace(candidate.DAGID) == "" ||
			strings.TrimSpace(candidate.RunID) == "" ||
			strings.TrimSpace(candidate.TaskID) == "" ||
			strings.TrimSpace(candidate.Label) == "" ||
			(candidate.Region != prodsupport.US01 &&
				candidate.Region != prodsupport.CA02) {
			return fmt.Errorf("invalid dependency re-run candidate at index %d", index)
		}
		if _, exists := numbers[candidate.Number]; exists {
			return fmt.Errorf("duplicate dependency re-run candidate number %d", candidate.Number)
		}
		numbers[candidate.Number] = struct{}{}
		if _, exists := identities[candidate.Identity()]; exists {
			return fmt.Errorf(
				"duplicate dependency re-run candidate %s",
				candidate.Identity(),
			)
		}
		identities[candidate.Identity()] = struct{}{}
	}
	return nil
}

func requireProductionFollowUp() error {
	if strings.TrimSpace(os.Getenv("PROD_SUPPORT_SOURCE")) != "production" {
		return fmt.Errorf(
			"prod-support dependency re-runs require PROD_SUPPORT_SOURCE=production",
		)
	}
	return nil
}

func validateValidationURLs(values []string) error {
	if len(values) != 2 ||
		!containsURL(values, "airflow-us01") ||
		!containsURL(values, "airflow-ca02") {
		return fmt.Errorf(
			"dependency re-run requires the original US and CA validation URLs",
		)
	}
	return nil
}

func dependencyPlanID(references []prodsupport.RetryTaskReference) string {
	identities := make([]string, len(references))
	for index, reference := range references {
		identities[index] = strings.Join([]string{
			string(reference.Region),
			reference.DAGID,
			reference.RunID,
			reference.TaskID,
		}, "\x00")
	}
	sort.Strings(identities)
	sum := sha256.Sum256([]byte(strings.Join(identities, "\n")))
	return fmt.Sprintf("sha256:%x", sum)
}
