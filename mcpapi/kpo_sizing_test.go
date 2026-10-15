package mcpapi

import (
	"context"
	"encoding/json"
	"reflect"
	"slices"
	"sort"
	"strings"
	"testing"

	"github.com/jeisenman/q2_bench/kposizing"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func TestKPOSizingToolRegistration(t *testing.T) {
	t.Parallel()
	session := newKPOSizingSession(t)
	result, err := session.ListTools(context.Background(), nil)
	if err != nil {
		t.Fatal(err)
	}
	names := make([]string, len(result.Tools))
	tools := make(map[string]*mcp.Tool, len(result.Tools))
	for index, tool := range result.Tools {
		names[index] = tool.Name
		tools[tool.Name] = tool
		annotations := tool.Annotations
		if annotations == nil || !annotations.ReadOnlyHint || !annotations.IdempotentHint {
			t.Fatalf("%s annotations = %#v", tool.Name, annotations)
		}
		if annotations.OpenWorldHint == nil || *annotations.OpenWorldHint {
			t.Fatalf("%s open-world annotation = %#v, want false", tool.Name, annotations.OpenWorldHint)
		}
	}
	sort.Strings(names)
	if want := []string{"estimate_kpo_resources", "get_kpo_job_templates"}; !reflect.DeepEqual(names, want) {
		t.Fatalf("tools = %v, want %v", names, want)
	}
	config := kposizing.DefaultConfig()
	for _, constraint := range []struct {
		tool string
		want int
		path []string
	}{
		{"estimate_kpo_resources", kposizing.MaxJobNameLength, []string{"properties", "job_template", "maxLength"}},
		{"estimate_kpo_resources", kposizing.MaxJobNameLength, []string{"properties", "workload", "properties", "job", "maxLength"}},
		{"estimate_kpo_resources", kposizing.MaxCPURationaleLength, []string{"properties", "workload", "properties", "cpu_evidence", "properties", "rationale", "maxLength"}},
		{"estimate_kpo_resources", config.MaxFileEvidence, []string{"properties", "workload", "properties", "profile", "properties", "file_bytes", "maxItems"}},
		{"estimate_kpo_resources", config.MaxFileEvidence, []string{"properties", "workload", "properties", "profile", "properties", "top_concurrent_file_bytes", "maxItems"}},
		{"get_kpo_job_templates", kposizing.MaxJobNameLength, []string{"properties", "job", "maxLength"}},
	} {
		got := kpoSchemaInt(t, tools[constraint.tool].InputSchema, constraint.path...)
		if got != constraint.want {
			t.Errorf("%s schema %v = %d, want %d", constraint.tool, constraint.path, got, constraint.want)
		}
	}
	rejected := callKPOSizingArguments(t, session, kpoSizingInput{
		Workload: kposizing.Workload{CurrentCPUMilli: 1, CPUEvidence: &kposizing.CPUEvidence{
			RecommendedMilli: 1,
			Rationale:        strings.Repeat("界", kposizing.MaxCPURationaleLength+1),
		}},
	})
	if !rejected.IsError {
		t.Fatal("overlong CPU rationale passed MCP schema validation")
	}
}

func TestKPOJobNameRuntimeBounds(t *testing.T) {
	t.Parallel()
	exact := strings.Repeat("界", kposizing.MaxJobNameLength)
	tooLong := exact + "界"
	for _, field := range []string{"job", "job_template"} {
		if got, err := boundedKPOJobName(exact, field); err != nil || got != exact {
			t.Errorf("%s exact boundary = %q, %v", field, got, err)
		}
		_, err := boundedKPOJobName(tooLong, field)
		if err == nil || !strings.Contains(err.Error(), field+" must not exceed") {
			t.Errorf("%s too-long error = %v", field, err)
		}
		if strings.Contains(err.Error(), tooLong) {
			t.Errorf("%s error echoed overlong input", field)
		}
	}
}

func TestKPOJobTemplatesToolListsAndResolvesAlias(t *testing.T) {
	t.Parallel()
	session := newKPOSizingSession(t)
	listed := callKPOJobTemplates(t, session, kpoJobTemplatesInput{})
	listOutput := decodeKPOStructured[kpoJobTemplatesOutput](t, listed)
	if len(listOutput.Templates) != maxKPOJobTemplates {
		t.Fatalf("template count = %d, want %d", len(listOutput.Templates), maxKPOJobTemplates)
	}
	if listOutput.Templates[0].Job != "relationship_signals_time_series_agg_cp_to_snowflake" {
		t.Fatalf("first template = %#v", listOutput.Templates[0])
	}
	lookup := callKPOJobTemplates(t, session, kpoJobTemplatesInput{
		Job: "core_loan_amortization_tables",
	})
	lookupOutput := decodeKPOStructured[kpoJobTemplatesOutput](t, lookup)
	if lookupOutput.Template == nil ||
		lookupOutput.Template.Job != "get_core_loan_amortization_tables" {
		t.Fatalf("lookup output = %#v", lookupOutput)
	}
}

func TestKPOSizingToolReturnsAuditableFamilyEstimate(t *testing.T) {
	t.Parallel()
	session := newKPOSizingSession(t)
	result := callKPOSizingArguments(t, session, kpoSizingInput{
		Workload: kposizing.Workload{
			Job:             "copy_job",
			Runner:          kposizing.RunnerK8sPod,
			Family:          kposizing.FamilyStorageAPICopy,
			CurrentCPUMilli: 2_000,
			Profile: kposizing.Profile{
				APIBufferBytes:   kpoUint64Pointer(bytesPerGiB),
				LargestFileBytes: kpoUint64Pointer(bytesPerGiB / 2),
			},
		},
	})
	output := decodeKPOStructured[kpoSizingOutput](t, result)
	if output.Estimate.PeakBytes != 3*bytesPerGiB+64*1024*1024 {
		t.Fatalf("peak bytes = %d", output.Estimate.PeakBytes)
	}
	if output.Estimate.RecommendedTierBytes != 4*bytesPerGiB {
		t.Fatalf("recommended tier = %d", output.Estimate.RecommendedTierBytes)
	}
	if output.Estimate.RecommendedCPUMilli != 2_000 {
		t.Fatalf("recommended CPU = %d", output.Estimate.RecommendedCPUMilli)
	}
	if !reflect.DeepEqual(output.EffectiveConfig, kposizing.DefaultConfig()) {
		t.Fatalf("effective config = %#v", output.EffectiveConfig)
	}
	if output.HumanReadableGiB.RecommendedTier != "4.000 GiB" {
		t.Fatalf("human-readable tier = %q", output.HumanReadableGiB.RecommendedTier)
	}
	if output.JobTemplate != nil {
		t.Fatalf("unexpected applied template = %#v", output.JobTemplate)
	}
}

func TestKPOSizingToolAppliesJobTemplateDefaults(t *testing.T) {
	t.Parallel()
	session := newKPOSizingSession(t)
	result := callKPOSizingArguments(t, session, map[string]any{
		"job_template": "core_loan_amortization_tables",
		"workload": map[string]any{
			"current_cpu_milli": 2_000,
			"profile": map[string]any{
				"changed_source_bytes":      512 * 1024 * 1024,
				"unchanged_source_bytes":    256 * 1024 * 1024,
				"in_memory_row_width_bytes": 100,
				"output_row_width_bytes":    50,
			},
		},
	})
	output := decodeKPOStructured[kpoSizingOutput](t, result)
	if output.JobTemplate == nil ||
		output.JobTemplate.Job != "get_core_loan_amortization_tables" {
		t.Fatalf("applied template = %#v", output.JobTemplate)
	}
	if output.Estimate.Job != "get_core_loan_amortization_tables" ||
		output.Estimate.Runner != kposizing.RunnerK8sPod ||
		output.Estimate.Family != kposizing.FamilyChunkedPandas {
		t.Fatalf("resolved estimate identity = %#v", output.Estimate)
	}
	for _, want := range []string{
		"chunk_rows=400000",
		"output_chunk_rows=400000",
		"upload_concurrency=10",
	} {
		if !slices.Contains(output.Estimate.Evidence, want) {
			t.Fatalf("evidence = %v, want %q", output.Estimate.Evidence, want)
		}
	}
}

func TestKPOSizingToolRejectsTemplateContradiction(t *testing.T) {
	t.Parallel()
	session := newKPOSizingSession(t)
	result := callKPOSizingArguments(t, session, map[string]any{
		"job_template": "core_loan_amortization_tables",
		"workload": map[string]any{
			"current_cpu_milli": 2_000,
			"profile":           map[string]any{"chunk_rows": 399_999},
		},
	})
	assertKPOSizingError(
		t,
		result,
		"chunk_rows 399999 contradicts known template value 400000",
	)
}

func TestKPOSizingToolIsDeterministic(t *testing.T) {
	t.Parallel()
	session := newKPOSizingSession(t)
	input := kpoSizingInput{Workload: kposizing.Workload{
		Job:             "threaded_copy",
		Runner:          kposizing.RunnerK8sPod,
		Family:          kposizing.FamilyThreadedByteCopy,
		CurrentCPUMilli: 1_000,
		Profile: kposizing.Profile{
			CopyConcurrency:        kpoIntPointer(2),
			TopConcurrentFileBytes: []uint64{bytesPerGiB, bytesPerGiB / 2},
		},
	}}
	first := callKPOSizingArguments(t, session, input)
	second := callKPOSizingArguments(t, session, input)
	firstJSON, err := json.Marshal(first.StructuredContent)
	if err != nil {
		t.Fatal(err)
	}
	secondJSON, err := json.Marshal(second.StructuredContent)
	if err != nil {
		t.Fatal(err)
	}
	if string(firstJSON) != string(secondJSON) {
		t.Fatalf("deterministic output mismatch:\n%s\n%s", firstJSON, secondJSON)
	}
}

func TestKPOSizingToolRejectsMissingEvidence(t *testing.T) {
	t.Parallel()
	session := newKPOSizingSession(t)
	result := callKPOSizingArguments(t, session, kpoSizingInput{Workload: kposizing.Workload{
		Job:             "unknown_copy",
		Runner:          kposizing.RunnerK8sPod,
		Family:          kposizing.FamilyThreadedByteCopy,
		CurrentCPUMilli: 1_000,
	}})
	assertKPOSizingError(
		t,
		result,
		"top_concurrent_file_bytes or descending file_bytes is required",
	)
}

func TestKPOSizingToolRejectsAboveTierEstimate(t *testing.T) {
	t.Parallel()
	session := newKPOSizingSession(t)
	result := callKPOSizingArguments(t, session, kpoSizingInput{Workload: kposizing.Workload{
		Job:             "oversized_copy",
		Runner:          kposizing.RunnerK8sPod,
		Family:          kposizing.FamilyStorageAPICopy,
		CurrentCPUMilli: 1_000,
		Profile: kposizing.Profile{
			APIBufferBytes:   kpoUint64Pointer(56 * bytesPerGiB),
			LargestFileBytes: kpoUint64Pointer(1),
		},
	}})
	assertKPOSizingError(t, result, "exceeds largest supported tier")
}

func TestKPOSizingToolReportsSparkExecutorAndClusterUnits(t *testing.T) {
	t.Parallel()
	session := newKPOSizingSession(t)
	result := callKPOSizingArguments(t, session, kpoSizingInput{Workload: kposizing.Workload{
		Job:             "spark_ingest",
		Runner:          kposizing.RunnerSpark,
		Family:          kposizing.FamilySparkCSVIngestion,
		CurrentCPUMilli: 4_000,
		Profile: kposizing.Profile{
			SparkExecutorCount:           kpoIntPointer(3),
			SparkTasksPerExecutor:        kpoIntPointer(2),
			SparkPartitionBytes:          kpoUint64Pointer(512 * 1024 * 1024),
			SparkCastBufferBytesPerTask:  kpoUint64Pointer(64 * 1024 * 1024),
			SparkWriteBufferBytesPerTask: kpoUint64Pointer(64 * 1024 * 1024),
			SparkShuffleBytesPerExecutor: kpoUint64Pointer(256 * 1024 * 1024),
			SparkCacheBytesPerExecutor:   kpoUint64Pointer(256 * 1024 * 1024),
		},
	}})
	output := decodeKPOStructured[kpoSizingOutput](t, result)
	if output.Estimate.RequestedUnit != kposizing.RequestedUnitExecutor {
		t.Fatalf("requested unit = %q", output.Estimate.RequestedUnit)
	}
	if output.Estimate.Cluster == nil || output.Estimate.Cluster.ExecutorCount != 3 {
		t.Fatalf("cluster = %#v", output.Estimate.Cluster)
	}
	if output.Estimate.Cluster.EstimatedClusterPeakBytes != 3*output.Estimate.PeakBytes {
		t.Fatalf("cluster peak = %d, executor peak = %d",
			output.Estimate.Cluster.EstimatedClusterPeakBytes,
			output.Estimate.PeakBytes,
		)
	}
	if output.HumanReadableGiB.EstimatedSparkClusterPeak != "17.250 GiB" {
		t.Fatalf(
			"human-readable cluster peak = %q",
			output.HumanReadableGiB.EstimatedSparkClusterPeak,
		)
	}
}

func newKPOSizingSession(t *testing.T) *mcp.ClientSession {
	t.Helper()
	server := mcp.NewServer(&mcp.Implementation{Name: "test", Version: "1"}, nil)
	if err := registerKPOSizing(server); err != nil {
		t.Fatal(err)
	}
	serverTransport, clientTransport := mcp.NewInMemoryTransports()
	if _, err := server.Connect(context.Background(), serverTransport, nil); err != nil {
		t.Fatal(err)
	}
	client := mcp.NewClient(&mcp.Implementation{Name: "test-client", Version: "1"}, nil)
	session, err := client.Connect(context.Background(), clientTransport, nil)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = session.Close() })
	return session
}

func callKPOSizingArguments(
	t *testing.T,
	session *mcp.ClientSession,
	arguments any,
) *mcp.CallToolResult {
	t.Helper()
	result, err := session.CallTool(context.Background(), &mcp.CallToolParams{
		Name:      "estimate_kpo_resources",
		Arguments: arguments,
	})
	if err != nil {
		t.Fatal(err)
	}
	return result
}

func callKPOJobTemplates(
	t *testing.T,
	session *mcp.ClientSession,
	input kpoJobTemplatesInput,
) *mcp.CallToolResult {
	t.Helper()
	result, err := session.CallTool(context.Background(), &mcp.CallToolParams{
		Name:      "get_kpo_job_templates",
		Arguments: input,
	})
	if err != nil {
		t.Fatal(err)
	}
	return result
}

func decodeKPOStructured[T any](t *testing.T, result *mcp.CallToolResult) T {
	t.Helper()
	var output T
	if result.IsError {
		t.Fatalf("tool returned error: %#v", result.Content)
	}
	payload, err := json.Marshal(result.StructuredContent)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(payload, &output); err != nil {
		t.Fatal(err)
	}
	return output
}

func assertKPOSizingError(t *testing.T, result *mcp.CallToolResult, want string) {
	t.Helper()
	if !result.IsError || len(result.Content) == 0 {
		t.Fatalf("result = %#v, want tool error", result)
	}
	text, ok := result.Content[0].(*mcp.TextContent)
	if !ok || !strings.Contains(text.Text, want) {
		t.Fatalf("error content = %#v, want substring %q", result.Content, want)
	}
}

func kpoUint64Pointer(value uint64) *uint64 { return &value }
func kpoIntPointer(value int) *int          { return &value }

func kpoSchemaInt(t *testing.T, schema any, path ...string) int {
	t.Helper()
	payload, err := json.Marshal(schema)
	if err != nil {
		t.Fatal(err)
	}
	var value any
	if err := json.Unmarshal(payload, &value); err != nil {
		t.Fatal(err)
	}
	for _, key := range path {
		object, ok := value.(map[string]any)
		if !ok {
			t.Fatalf("schema path %v reached %T before %q", path, value, key)
		}
		value = object[key]
	}
	number, ok := value.(float64)
	if !ok {
		t.Fatalf("schema path %v = %#v, want number", path, value)
	}
	return int(number)
}
