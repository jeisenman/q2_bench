package mcpapi

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/jeisenman/q2_bench/workflows/prodsupport"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

type prodSupportAPI struct {
	airflow       *airflowAPI
	cluster       *clusterHealthAPI
	updatesPath   string
	omissionsPath string
}

type runProdSupportInput struct {
	Prompt                string   `json:"prompt"`
	CorrelationID         string   `json:"correlation_id,omitempty"`
	DataInternalOmissions []string `json:"data_internal_omissions,omitempty"`
}

func registerProdSupport(server *mcp.Server, config Config) error {
	airflowAPI, err := newAirflowAPI(config.ConfigurationPath)
	if err != nil {
		return err
	}
	clusterAPI := newClusterHealthAPI(airflowAPI)
	api := &prodSupportAPI{
		airflow: airflowAPI, updatesPath: config.UpdatesPath,
		omissionsPath: config.OmissionsPath, cluster: clusterAPI,
	}
	if api.updatesPath == "" {
		api.updatesPath = os.Getenv("PROD_SUPPORT_UPDATES_PATH")
	}
	if api.omissionsPath == "" {
		api.omissionsPath = filepath.Join(".agentsdk", "prod-support-omissions.json")
	}
	addAirflowTools(server, airflowAPI)
	addClusterHealthTool(server, clusterAPI)
	if err := registerLineage(server); err != nil {
		return err
	}
	if err := registerKPOSizing(server); err != nil {
		return err
	}
	mcp.AddTool(server, &mcp.Tool{
		Name:        "run_prod_support",
		Description: "Investigate production Airflow failures and return an evidence-based report.",
	}, api.run)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "setup_prod_support",
		Description: "Create the private production-support omission settings file.",
	}, api.setup)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "get_prod_support_omissions",
		Description: "Read configured Data Internal omission groups.",
	}, api.getOmissions)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "set_prod_support_omissions",
		Description: "Replace configured Data Internal omission groups.",
	}, api.setOmissions)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "update_prod_support_omissions",
		Description: "Add or remove named omission groups from private settings.",
	}, api.updateOmissions)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "execute_prod_support_follow_up",
		Description: "Execute exact eligible Airflow retries after explicit approval.",
	}, api.executeFollowUp)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "list_prod_support_updates",
		Description: "Read genuine production-support updates.",
	}, api.listUpdates)
	registerProdSupportResources(server, api)
	return nil
}

func (a *prodSupportAPI) setup(
	_ context.Context,
	_ *mcp.CallToolRequest,
	_ struct{},
) (*mcp.CallToolResult, map[string]any, error) {
	values, err := a.readOmissions()
	if err != nil {
		return nil, nil, err
	}
	if _, statErr := os.Stat(a.omissionsPath); os.IsNotExist(statErr) {
		if err := a.writeOmissions(values); err != nil {
			return nil, nil, err
		}
	}
	return nil, map[string]any{
		"path": a.omissionsPath, "data_internal_omissions": values,
	}, nil
}

func (a *prodSupportAPI) run(
	ctx context.Context,
	_ *mcp.CallToolRequest,
	input runProdSupportInput,
) (*mcp.CallToolResult, map[string]any, error) {
	if strings.TrimSpace(input.Prompt) == "" {
		return nil, nil, fmt.Errorf("prompt must not be empty")
	}
	now := time.Now().UTC()
	window, err := prodsupport.ResolveQueryWindow(input.Prompt, now)
	if err != nil {
		return nil, nil, err
	}
	since := window.FailedSince
	failures, err := a.airflow.source.DiscoverFailures(ctx, since)
	if err != nil {
		return nil, nil, err
	}
	diagnoses := make([]prodsupport.FailureDiagnosis, len(failures))
	candidates := make([]prodsupport.RetryCandidate, 0)
	lines := []string{"URLs to validate", "- US-01 and CA-02 Airflow", "", "Message for developer"}
	for index := range failures {
		log, logErr := a.airflow.source.FetchLog(ctx, failures[index])
		if logErr != nil {
			diagnoses[index] = prodsupport.FailureDiagnosis{
				FailureID: failures[index].FailureID(), Kind: prodsupport.Unknown,
				Confidence: "unknown", Status: prodsupport.EvidenceUnavailable,
			}
		} else {
			failures[index].Log = log
			diagnoses[index] = prodsupport.ClassifyLog(
				failures[index], log, prodsupport.AirflowExactTaskAttempt,
			)
		}
		lines = append(lines, fmt.Sprintf(
			"- %s %s/%s: %s (%s)",
			failures[index].Region, failures[index].DAGID, failures[index].TaskID,
			diagnoses[index].Kind, diagnoses[index].Confidence,
		))
		candidates = append(candidates, prodsupport.RetryCandidate{
			Number: index + 1, Region: failures[index].Region,
			DAGID: failures[index].DAGID, RunID: failures[index].RunID,
			TaskID: failures[index].TaskID, Label: prodsupport.JobLabel(failures[index].TaskID),
		})
	}
	if len(failures) == 0 {
		lines = append(lines, "- No failed tasks found.")
	}
	lines = append(lines, "", "Message for Data Internal Channel",
		fmt.Sprintf("- %d production task failure(s) require review.", len(failures)),
		"", "Follow Up", "- Retry only after explicit developer authorization.")
	report := strings.Join(lines, "\n")
	return nil, map[string]any{
		"output": report, "full_report": report, "message_for_developer": report,
		"failure_count": len(failures), "failures": failures, "diagnoses": diagnoses,
		"retry_candidates": candidates, "correlation_id": correlation(input.CorrelationID),
		"source": "production", "regions": []string{"US-01", "CA-02"},
	}, nil
}

func (a *prodSupportAPI) getOmissions(
	_ context.Context,
	_ *mcp.CallToolRequest,
	_ struct{},
) (*mcp.CallToolResult, map[string]any, error) {
	values, err := a.readOmissions()
	return nil, map[string]any{
		"path": a.omissionsPath, "data_internal_omissions": values,
	}, err
}

type omissionsInput struct {
	DataInternalOmissions []string `json:"data_internal_omissions"`
}

func (a *prodSupportAPI) setOmissions(
	_ context.Context,
	_ *mcp.CallToolRequest,
	input omissionsInput,
) (*mcp.CallToolResult, map[string]any, error) {
	config, err := prodsupport.NewReportConfig(input.DataInternalOmissions)
	if err != nil {
		return nil, nil, err
	}
	values := make([]string, len(config.DataInternalOmissions))
	for index, value := range config.DataInternalOmissions {
		values[index] = string(value)
	}
	if err := a.writeOmissions(values); err != nil {
		return nil, nil, err
	}
	return nil, map[string]any{
		"path": a.omissionsPath, "data_internal_omissions": values,
	}, nil
}

type omissionUpdateInput struct {
	Direction string `json:"direction"`
}

func (a *prodSupportAPI) updateOmissions(
	_ context.Context,
	_ *mcp.CallToolRequest,
	input omissionUpdateInput,
) (*mcp.CallToolResult, map[string]any, error) {
	current, err := a.readOmissions()
	if err != nil {
		return nil, nil, err
	}
	values, err := prodsupport.UpdateOmissionValues(current, input.Direction)
	if err != nil {
		return nil, nil, err
	}
	if err := a.writeOmissions(values); err != nil {
		return nil, nil, err
	}
	return nil, map[string]any{
		"path": a.omissionsPath, "data_internal_omissions": values,
	}, nil
}

func (a *prodSupportAPI) writeOmissions(values []string) error {
	if err := os.MkdirAll(filepath.Dir(a.omissionsPath), 0o700); err != nil {
		return err
	}
	content, _ := json.MarshalIndent(map[string]any{"data_internal_omissions": values}, "", "  ")
	if err := os.WriteFile(a.omissionsPath, append(content, '\n'), 0o600); err != nil {
		return err
	}
	return nil
}

func (a *prodSupportAPI) readOmissions() ([]string, error) {
	content, err := os.ReadFile(a.omissionsPath)
	if os.IsNotExist(err) {
		defaults := prodsupport.DefaultOmissions()
		values := make([]string, len(defaults))
		for index, value := range defaults {
			values[index] = string(value)
		}
		return values, nil
	}
	if err != nil {
		return nil, err
	}
	var payload omissionsInput
	if err := json.Unmarshal(content, &payload); err != nil {
		return nil, err
	}
	_, err = prodsupport.NewReportConfig(payload.DataInternalOmissions)
	return payload.DataInternalOmissions, err
}

type followUpInput struct {
	Direction       string                       `json:"direction"`
	RetryCandidates []prodsupport.RetryCandidate `json:"retry_candidates"`
	ValidationURLs  []string                     `json:"validation_urls"`
	CorrelationID   string                       `json:"correlation_id,omitempty"`
	ApprovalID      string                       `json:"approval_id"`
}

func (a *prodSupportAPI) executeFollowUp(
	ctx context.Context,
	_ *mcp.CallToolRequest,
	input followUpInput,
) (*mcp.CallToolResult, map[string]any, error) {
	if os.Getenv("PROD_SUPPORT_SOURCE") != "production" {
		return nil, nil, fmt.Errorf(
			"prod-support follow-up retries require PROD_SUPPORT_SOURCE=production",
		)
	}
	if len(input.ValidationURLs) != 2 ||
		!containsURL(input.ValidationURLs, "airflow-us01") ||
		!containsURL(input.ValidationURLs, "airflow-ca02") {
		return nil, nil, fmt.Errorf(
			"follow-up requires the original US and CA validation URLs",
		)
	}
	for index, candidate := range input.RetryCandidates {
		if candidate.Number < 1 || strings.TrimSpace(candidate.DAGID) == "" ||
			strings.TrimSpace(candidate.RunID) == "" ||
			strings.TrimSpace(candidate.TaskID) == "" ||
			(candidate.Region != prodsupport.US01 && candidate.Region != prodsupport.CA02) {
			return nil, nil, fmt.Errorf("invalid retry candidate at index %d", index)
		}
	}
	selected, err := prodsupport.SelectRetryCandidates(
		input.Direction,
		input.RetryCandidates,
	)
	if err != nil {
		return nil, nil, err
	}
	batches := prodsupport.RetryBatches(selected)
	if err := a.preflightFollowUp(ctx, batches); err != nil {
		return nil, nil, err
	}
	states := make([]prodsupport.RetryTaskReference, 0, len(selected))
	for _, batch := range batches {
		retried, retryErr := a.airflow.source.ExecuteRetry(ctx, batch, input.ApprovalID)
		if retryErr != nil {
			return nil, nil, retryErr
		}
		states = append(states, retried...)
	}
	return nil, map[string]any{
		"task_instances": states, "links": input.ValidationURLs,
		"validation_urls": input.ValidationURLs,
		"correlation_id":  correlation(input.CorrelationID),
		"approval_id":     input.ApprovalID,
	}, nil
}

func containsURL(values []string, marker string) bool {
	for _, value := range values {
		if strings.Contains(strings.ToLower(value), marker) {
			return true
		}
	}
	return false
}

type updatesInput struct {
	Client      string `json:"client,omitempty"`
	Status      string `json:"status,omitempty"`
	Environment string `json:"environment,omitempty"`
}

func (a *prodSupportAPI) listUpdates(
	_ context.Context,
	_ *mcp.CallToolRequest,
	input updatesInput,
) (*mcp.CallToolResult, map[string]any, error) {
	content, err := os.ReadFile(a.updatesPath)
	if err != nil {
		return nil, nil, err
	}
	var updates []map[string]any
	if err := json.Unmarshal(content, &updates); err != nil {
		return nil, nil, err
	}
	filtered := make([]map[string]any, 0, len(updates))
	for _, update := range updates {
		if matches(update, "client", input.Client) &&
			matches(update, "status", input.Status) &&
			matches(update, "environment", input.Environment) {
			filtered = append(filtered, update)
		}
	}
	return nil, map[string]any{
		"source": "pl-data-plugins/product_support_updates.json",
		"count":  len(filtered), "updates": filtered,
	}, nil
}

func matches(value map[string]any, field, expected string) bool {
	return expected == "" || strings.EqualFold(fmt.Sprint(value[field]), expected)
}

func correlation(value string) string {
	if strings.TrimSpace(value) != "" {
		return value
	}
	return fmt.Sprintf("%d", time.Now().UnixNano())
}
