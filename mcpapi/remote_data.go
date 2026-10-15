package mcpapi

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os/exec"
	"sort"
	"strconv"
	"strings"
	"time"

	omsadapter "github.com/jeisenman/q2_bench/adapters/oms"
	"github.com/jeisenman/q2_bench/adapters/outbound"
	omsagent "github.com/jeisenman/q2_bench/agents/oms"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

type notebookInput struct {
	Platform string `json:"platform"`
	Code     string `json:"code"`
}

type adlsNotebookInput struct {
	Environment string `json:"environment"`
	Container   string `json:"container"`
	Path        string `json:"path"`
	FileFormat  string `json:"file_format,omitempty"`
	Limit       int    `json:"limit,omitempty"`
}

type snowflakeNotebookInput struct {
	Environment string `json:"environment,omitempty"`
	Statement   string `json:"statement"`
	Limit       int    `json:"limit,omitempty"`
}

type runDatabricksInput struct {
	Platform          string         `json:"platform"`
	Source            string         `json:"source"`
	SourceSHA256      string         `json:"source_sha256"`
	ExistingClusterID string         `json:"existing_cluster_id"`
	Options           map[string]any `json:"options,omitempty"`
}

type uploadBranchInput struct {
	Branch string `json:"branch"`
}

type jobEvidenceInput struct {
	Parameters jobEvidenceParameters `json:"parameters"`
}

type jobEvidenceParameters struct {
	Region    string `json:"region"`
	ClientID  string `json:"client_id_g"`
	RunID     string `json:"run_id_s"`
	TaskID    string `json:"task_id_s"`
	TryNumber int    `json:"try_number_d"`
	StartAt   string `json:"start_at"`
	Table     string `json:"table,omitempty"`
}

func registerRemoteData(server *mcp.Server) {
	mcp.AddTool(server, &mcp.Tool{
		Name:        "list_remote_data_targets",
		Description: "List the non-secret Databricks and data target allowlists.",
	}, listRemoteDataTargets)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "make_databricks_notebook",
		Description: "Build Databricks source boilerplate for Data Engineering or RA.",
	}, makeDatabricksNotebook)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "make_adls_notebook",
		Description: "Build a bounded read-only Spark notebook for an ADLS location.",
	}, makeADLSNotebook)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "make_snowflake_notebook",
		Description: "Build a bounded Snowflake connector notebook.",
	}, makeSnowflakeNotebook)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "run_databricks_notebook",
		Description: "Submit an exact reviewed Databricks SOURCE notebook.",
	}, runDatabricksNotebook)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "upload_databricks_integration_branch",
		Description: "Upload master, main, or one RA-#### branch through dsint.",
	}, uploadDatabricksBranch)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "query_job_evidence",
		Description: "Read exact bounded production OMS evidence for one workload attempt.",
	}, queryJobEvidence)
	registerOMS(server)
}

func listRemoteDataTargets(
	_ context.Context,
	_ *mcp.CallToolRequest,
	_ struct{},
) (*mcp.CallToolResult, map[string]any, error) {
	names := make([]string, 0, len(outbound.DatabricksTargets))
	for name := range outbound.DatabricksTargets {
		names = append(names, name)
	}
	sort.Strings(names)
	databricks := make(map[string]any, len(names))
	for _, name := range names {
		target := outbound.DatabricksTargets[name]
		databricks[name] = map[string]any{
			"name": target.Name, "workspace_id": target.WorkspaceID,
			"sql_warehouse_id": target.SQLWarehouseID,
		}
	}
	return nil, map[string]any{
		"databricks": databricks, "adls": outbound.ADLSTargets,
		"snowflake": outbound.SnowflakeTargets, "oms": outbound.OMSTargets,
	}, nil
}

func makeDatabricksNotebook(
	_ context.Context,
	_ *mcp.CallToolRequest,
	input notebookInput,
) (*mcp.CallToolResult, map[string]any, error) {
	target, exists := outbound.DatabricksTargets[strings.ToLower(strings.TrimSpace(input.Platform))]
	if !exists {
		return nil, nil, fmt.Errorf("platform must be data_engineering or ra")
	}
	if strings.TrimSpace(input.Code) == "" {
		return nil, nil, fmt.Errorf("code must not be empty")
	}
	source := strings.Join([]string{
		"# Databricks notebook source", "# MAGIC %md",
		"# MAGIC # Remote data query: " + target.Name,
		"# MAGIC Generated query boilerplate. Review before running.",
		"", "# COMMAND ----------", "", strings.TrimSpace(input.Code), "",
	}, "\n")
	digest := sha256.Sum256([]byte(source))
	return nil, map[string]any{
		"target": target.Name, "format": "SOURCE", "source": source,
		"source_sha256": hex.EncodeToString(digest[:]),
	}, nil
}

func makeADLSNotebook(
	_ context.Context,
	_ *mcp.CallToolRequest,
	input adlsNotebookInput,
) (*mcp.CallToolResult, map[string]any, error) {
	target, exists := outbound.ADLSTargets[input.Environment]
	if !exists {
		return nil, nil, fmt.Errorf("unsupported ADLS environment %q", input.Environment)
	}
	format := strings.ToLower(strings.TrimSpace(input.FileFormat))
	if format == "" {
		format = "parquet"
	}
	if !containsString([]string{"csv", "delta", "json", "parquet"}, format) {
		return nil, nil, fmt.Errorf("file_format must be csv, delta, json, or parquet")
	}
	limit, err := previewLimit(input.Limit)
	if err != nil {
		return nil, nil, err
	}
	if strings.TrimSpace(input.Container) == "" || strings.TrimSpace(input.Path) == "" {
		return nil, nil, fmt.Errorf("container and path must not be empty")
	}
	uri := fmt.Sprintf(
		"abfss://%s@%s.dfs.core.windows.net/%s",
		strings.TrimSpace(input.Container), target.AccountName,
		strings.TrimLeft(strings.TrimSpace(input.Path), "/"),
	)
	source := strings.Join([]string{
		"# Databricks notebook source", "# MAGIC %md",
		"# MAGIC # ADLS query: " + input.Environment,
		"# MAGIC Read-only bounded preview.", "", "# COMMAND ----------", "",
		"adls_uri = " + strconv.Quote(uri),
		"data = spark.read.format(" + strconv.Quote(format) + ").load(adls_uri)",
		fmt.Sprintf("display(data.limit(%d))", limit), "",
	}, "\n")
	return nil, map[string]any{
		"target": target.AccountName, "format": "SOURCE", "source": source,
	}, nil
}

func makeSnowflakeNotebook(
	_ context.Context,
	_ *mcp.CallToolRequest,
	input snowflakeNotebookInput,
) (*mcp.CallToolResult, map[string]any, error) {
	environment := input.Environment
	if environment == "" {
		environment = "prod_us"
	}
	if !containsString([]string{"alpha", "staging", "prod_us"}, environment) {
		return nil, nil, fmt.Errorf("unsupported Snowflake environment %q", environment)
	}
	statement := strings.TrimSpace(input.Statement)
	if !readOnlySQL(statement) {
		return nil, nil, fmt.Errorf("statement must be a read-only SELECT, WITH, SHOW, or DESCRIBE query")
	}
	limit, err := previewLimit(input.Limit)
	if err != nil {
		return nil, nil, err
	}
	prefix := "SNOWFLAKE_" + strings.ToUpper(environment)
	source := fmt.Sprintf(`# Databricks notebook source
# MAGIC %%md
# MAGIC # Snowflake query: %s
# MAGIC Credentials are read from environment variables at runtime.

# COMMAND ----------

import os
import snowflake.connector

connection = snowflake.connector.connect(
    account=os.environ[%s],
    user=os.environ[%s],
    password=os.environ[%s],
)
try:
    with connection.cursor() as cursor:
        cursor.execute(%s)
        rows = cursor.fetchmany(%d)
        display(rows)
finally:
    connection.close()
`, environment, strconv.Quote(prefix+"_ACCOUNT"), strconv.Quote(prefix+"_USER"),
		strconv.Quote(prefix+"_PASSWORD"), strconv.Quote(statement), limit)
	return nil, map[string]any{
		"target": environment, "format": "SOURCE", "source": source,
	}, nil
}

func runDatabricksNotebook(
	ctx context.Context,
	_ *mcp.CallToolRequest,
	input runDatabricksInput,
) (*mcp.CallToolResult, map[string]any, error) {
	return databricksBridge(ctx, "run", input)
}

func uploadDatabricksBranch(
	ctx context.Context,
	_ *mcp.CallToolRequest,
	input uploadBranchInput,
) (*mcp.CallToolResult, map[string]any, error) {
	return databricksBridge(ctx, "upload", input)
}

func queryJobEvidence(
	ctx context.Context,
	_ *mcp.CallToolRequest,
	input jobEvidenceInput,
) (*mcp.CallToolResult, map[string]any, error) {
	startAt, err := time.Parse(time.RFC3339Nano, input.Parameters.StartAt)
	if err != nil {
		return nil, nil, fmt.Errorf("start_at must be RFC3339 with a timezone: %w", err)
	}
	query, err := omsagent.BuildJobQuery(omsagent.JobQueryParameters{
		Region: omsagent.Region(input.Parameters.Region), ClientID: input.Parameters.ClientID,
		RunID: input.Parameters.RunID, TaskID: input.Parameters.TaskID,
		TryNumber: input.Parameters.TryNumber, StartAt: startAt, Table: input.Parameters.Table,
	})
	if err != nil {
		return nil, nil, err
	}
	workspace, err := omsagent.ResolveWorkspace(
		omsagent.Production,
		omsagent.Region(input.Parameters.Region),
	)
	if err != nil {
		return nil, nil, err
	}
	result, err := (omsadapter.LogAnalyticsSource{
		TokenSource: omsadapter.AzureCLITokenSource{},
	}).Query(ctx, workspace, omsagent.Query{
		KQL: query.KQL,
		Timespan: query.WindowStart.Format(time.RFC3339) + "/" +
			query.WindowEnd.Format(time.RFC3339),
	})
	if err != nil {
		return nil, nil, err
	}
	evidence, err := omsadapter.RenderRows(result)
	if err != nil {
		return nil, nil, err
	}
	return nil, map[string]any{"evidence": evidence}, nil
}

func databricksBridge(
	ctx context.Context,
	operation string,
	input any,
) (*mcp.CallToolResult, map[string]any, error) {
	payload, err := json.Marshal(input)
	if err != nil {
		return nil, nil, err
	}
	command := exec.CommandContext(
		ctx, "uv", "run", "python", "-m", "databricks_runtime.cli", operation,
	)
	command.Stdin = bytes.NewReader(payload)
	var stderr bytes.Buffer
	command.Stderr = &stderr
	output, err := command.Output()
	if err != nil {
		detail := strings.TrimSpace(stderr.String())
		if len(detail) > 4_000 {
			detail = detail[len(detail)-4_000:]
		}
		if detail == "" {
			return nil, nil, fmt.Errorf("Databricks runtime failed: %w", err)
		}
		return nil, nil, fmt.Errorf("Databricks runtime failed: %w: %s", err, detail)
	}
	var result map[string]any
	if err := json.Unmarshal(output, &result); err != nil {
		return nil, nil, fmt.Errorf("Databricks runtime returned invalid JSON: %w", err)
	}
	return nil, result, nil
}

func previewLimit(value int) (int, error) {
	if value == 0 {
		return 100, nil
	}
	if value < 1 || value > 10_000 {
		return 0, fmt.Errorf("limit must be between 1 and 10000")
	}
	return value, nil
}

func readOnlySQL(value string) bool {
	fields := strings.Fields(strings.ToLower(value))
	return len(fields) > 0 && containsString(
		[]string{"select", "with", "show", "describe"}, fields[0],
	)
}

func containsString(values []string, value string) bool {
	for _, item := range values {
		if item == value {
			return true
		}
	}
	return false
}
