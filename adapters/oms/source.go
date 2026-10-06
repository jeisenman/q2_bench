// Package oms implements Azure Log Analytics and Data Collector adapters.
package oms

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os/exec"
	"strings"
	"time"

	agent "github.com/jeisenman/q2_bench/agents/oms"
)

const logAnalyticsScope = "https://api.loganalytics.io"

// TokenSource acquires a Log Analytics bearer token.
type TokenSource interface {
	AccessToken(context.Context, string) (string, error)
}

// AzureCLITokenSource uses the active Azure CLI session.
type AzureCLITokenSource struct {
	Executable string
}

// AccessToken returns a token scoped to one subscription.
func (s AzureCLITokenSource) AccessToken(
	ctx context.Context,
	subscriptionID string,
) (string, error) {
	executable := s.Executable
	if executable == "" {
		executable = "az"
	}
	output, err := exec.CommandContext(
		ctx,
		executable,
		"account",
		"get-access-token",
		"--subscription",
		subscriptionID,
		"--resource",
		logAnalyticsScope,
		"--query",
		"accessToken",
		"--output",
		"tsv",
	).Output()
	if err != nil {
		return "", fmt.Errorf("acquire Azure Log Analytics token: %w", err)
	}
	token := strings.TrimSpace(string(output))
	if token == "" {
		return "", fmt.Errorf("Azure CLI returned an empty access token")
	}
	return token, nil
}

// LogAnalyticsSource executes bounded Azure Log Analytics queries.
type LogAnalyticsSource struct {
	TokenSource TokenSource
	Client      *http.Client
}

// Query executes one bounded query.
func (s LogAnalyticsSource) Query(
	ctx context.Context,
	workspace agent.Workspace,
	query agent.Query,
) (agent.QueryResult, error) {
	if err := query.Validate(); err != nil {
		return agent.QueryResult{}, err
	}
	if s.TokenSource == nil {
		return agent.QueryResult{}, fmt.Errorf("OMS token source must not be nil")
	}
	token, err := s.TokenSource.AccessToken(ctx, workspace.SubscriptionID)
	if err != nil {
		return agent.QueryResult{}, err
	}
	body, err := json.Marshal(map[string]string{
		"query": query.KQL, "timespan": query.Timespan,
	})
	if err != nil {
		return agent.QueryResult{}, err
	}
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		fmt.Sprintf(
			"https://api.loganalytics.io/v1/workspaces/%s/query",
			workspace.WorkspaceID,
		),
		bytes.NewReader(body),
	)
	if err != nil {
		return agent.QueryResult{}, err
	}
	request.Header.Set("Authorization", "Bearer "+token)
	request.Header.Set("Content-Type", "application/json")
	response, err := httpClient(s.Client).Do(request)
	if err != nil {
		return agent.QueryResult{}, err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return agent.QueryResult{}, fmt.Errorf("OMS query failed with HTTP %d", response.StatusCode)
	}
	payload, err := io.ReadAll(io.LimitReader(response.Body, 8<<20))
	if err != nil {
		return agent.QueryResult{}, err
	}
	return decodeQueryResult(payload)
}

// DataCollectorSink appends signed custom OMS records.
type DataCollectorSink struct {
	SharedKey string
	Client    *http.Client
	Now       func() time.Time
}

// Write appends one custom log record.
func (s DataCollectorSink) Write(
	ctx context.Context,
	workspace agent.Workspace,
	record agent.LogRecord,
) error {
	if err := record.Validate(); err != nil {
		return err
	}
	body, err := json.Marshal([]map[string]any{record.Fields})
	if err != nil {
		return err
	}
	now := s.Now
	if now == nil {
		now = time.Now
	}
	date := now().UTC().Format(http.TimeFormat)
	signature, err := Signature(workspace.WorkspaceID, s.SharedKey, date, body)
	if err != nil {
		return err
	}
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		fmt.Sprintf(
			"https://%s.ods.opinsights.azure.com/api/logs?api-version=2016-04-01",
			workspace.WorkspaceID,
		),
		bytes.NewReader(body),
	)
	if err != nil {
		return err
	}
	request.Header.Set("Authorization", signature)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Log-Type", record.LogType)
	request.Header.Set("x-ms-date", date)
	response, err := httpClient(s.Client).Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK && response.StatusCode != http.StatusAccepted {
		return fmt.Errorf("OMS log write failed with HTTP %d", response.StatusCode)
	}
	return nil
}

// Signature builds the OMS Data Collector authorization header.
func Signature(workspaceID, sharedKey, date string, body []byte) (string, error) {
	key, err := base64.StdEncoding.Strict().DecodeString(sharedKey)
	if err != nil {
		return "", fmt.Errorf("OMS shared key must be valid base64")
	}
	contentHash := fmt.Sprintf(
		"POST\n%d\napplication/json\nx-ms-date:%s\n/api/logs",
		len(body),
		date,
	)
	mac := hmac.New(sha256.New, key)
	_, _ = mac.Write([]byte(contentHash))
	encoded := base64.StdEncoding.EncodeToString(mac.Sum(nil))
	return fmt.Sprintf("SharedKey %s:%s", workspaceID, encoded), nil
}

// RenderRows renders tabular evidence as deterministic JSON lines.
func RenderRows(result agent.QueryResult) (string, error) {
	lines := make([]string, len(result.Rows))
	for rowIndex, row := range result.Rows {
		if len(row) != len(result.Columns) {
			return "", fmt.Errorf(
				"OMS row %d contains %d values for %d columns",
				rowIndex,
				len(row),
				len(result.Columns),
			)
		}
		record := make(map[string]any, len(row))
		for columnIndex, column := range result.Columns {
			record[column] = row[columnIndex]
		}
		encoded, err := json.Marshal(record)
		if err != nil {
			return "", err
		}
		lines[rowIndex] = string(encoded)
	}
	return strings.Join(lines, "\n"), nil
}

func decodeQueryResult(payload []byte) (agent.QueryResult, error) {
	var response struct {
		Tables []struct {
			Columns []struct {
				Name string `json:"name"`
			} `json:"columns"`
			Rows [][]any `json:"rows"`
		} `json:"tables"`
	}
	if err := json.Unmarshal(payload, &response); err != nil ||
		len(response.Tables) == 0 {
		return agent.QueryResult{}, fmt.Errorf("OMS query response has an invalid shape")
	}
	table := response.Tables[0]
	columns := make([]string, len(table.Columns))
	for index, column := range table.Columns {
		columns[index] = column.Name
	}
	return agent.QueryResult{Columns: columns, Rows: table.Rows}, nil
}

func httpClient(client *http.Client) *http.Client {
	if client == nil {
		return &http.Client{Timeout: 30 * time.Second}
	}
	return client
}
