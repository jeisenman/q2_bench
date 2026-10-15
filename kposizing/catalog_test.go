package kposizing

import (
	"reflect"
	"strings"
	"testing"
)

func TestListJobTemplatesHasCanonicalCoverageAndOrder(t *testing.T) {
	t.Parallel()
	want := []string{
		"relationship_signals_time_series_agg_cp_to_snowflake",
		"get_core_loan_amortization_tables",
		"get_assumption_sets",
		"assumption_sets_to_internal_adls",
		"assumption_sets_to_client_datamart_adls",
		"get_other_financial_statement_breakdown",
		"get_loan_financial_statement_breakdown",
		"get_core_deposit_accounts",
		"get_data_eng_core_deposit_account_metadata",
		"high_quality_core_deposit_accounts_copy_client",
		"monthly_core_deposit_accounts_copy_client",
		"get_treasury_financial_statement_breakdown",
		"get_core_other_accounts",
		"get_data_eng_core_other_account_metadata",
		"get_commercial_loan_products",
		"treasury_assumptions_to_internal_adls",
		"get_treasury_assumptions",
		"get_deposit_financial_statement_breakdown",
	}
	first := ListJobTemplates()
	second := ListJobTemplates()
	firstNames := make([]string, len(first))
	secondNames := make([]string, len(second))
	for index := range first {
		firstNames[index] = first[index].Job
		secondNames[index] = second[index].Job
	}
	if !reflect.DeepEqual(firstNames, want) {
		t.Fatalf("canonical jobs = %v, want %v", firstNames, want)
	}
	if !reflect.DeepEqual(firstNames, secondNames) {
		t.Fatalf("catalog order changed between calls: %v != %v", firstNames, secondNames)
	}
}

func TestLookupJobTemplateNormalizesAliases(t *testing.T) {
	t.Parallel()
	tests := []struct {
		alias string
		job   string
	}{
		{"core_loan_amortization_tables", "get_core_loan_amortization_tables"},
		{"high_quality_core_deposit_accounts_cp_to_client", "high_quality_core_deposit_accounts_copy_client"},
		{"treasury_assumptions", "get_treasury_assumptions"},
	}
	for _, test := range tests {
		template, err := LookupJobTemplate("  " + test.alias + "  ")
		if err != nil {
			t.Fatalf("LookupJobTemplate(%q) error = %v", test.alias, err)
		}
		if template.Job != test.job {
			t.Errorf("LookupJobTemplate(%q).Job = %q, want %q", test.alias, template.Job, test.job)
		}
	}
}

func TestCatalogReturnsDefensiveCopies(t *testing.T) {
	t.Parallel()
	listed := ListJobTemplates()
	listed[0].Job = "mutated"
	listed[0].Aliases[0] = "mutated"
	listed[0].RunnerChoices[0].Runner = Runner("mutated")
	listed[0].RunnerChoices[0].Provenance[0].File = "mutated"
	listed[0].Provenance[0].File = "mutated"

	template, err := LookupJobTemplate("relationship_signals_time_series_agg_to_snowflake")
	if err != nil {
		t.Fatalf("LookupJobTemplate() error = %v", err)
	}
	if template.Job != "relationship_signals_time_series_agg_cp_to_snowflake" ||
		template.Aliases[0] != "relationship_signals_time_series_agg_to_snowflake" ||
		template.RunnerChoices[0].Runner != RunnerBatch ||
		template.RunnerChoices[0].Provenance[0].File == "mutated" ||
		template.Provenance[0].File == "mutated" {
		t.Fatalf("catalog data was mutated through returned value: %#v", template)
	}

	template.Aliases[0] = "changed again"
	second, err := LookupJobTemplate("relationship_signals_time_series_agg_cp_to_snowflake")
	if err != nil {
		t.Fatalf("second LookupJobTemplate() error = %v", err)
	}
	if second.Aliases[0] != "relationship_signals_time_series_agg_to_snowflake" {
		t.Fatalf("lookup returned aliased data: %#v", second.Aliases)
	}
}

func TestApplyJobTemplateDefaultsPreservesMeasuredEvidence(t *testing.T) {
	t.Parallel()
	datasetBytes := uint64(987)
	rowWidth := uint64(42)
	workload := Workload{
		CurrentCPUMilli: 2_000,
		Profile: Profile{
			DatasetBytes:           &datasetBytes,
			InMemoryRowWidthBytes:  &rowWidth,
			FileBytes:              []uint64{600, 387},
			TopConcurrentFileBytes: []uint64{600},
		},
	}
	result, err := ApplyJobTemplateDefaults("core_loan_amortization_tables", workload)
	if err != nil {
		t.Fatalf("ApplyJobTemplateDefaults() error = %v", err)
	}
	if result.Job != "get_core_loan_amortization_tables" ||
		result.Runner != RunnerK8sPod ||
		result.Family != FamilyChunkedPandas {
		t.Fatalf("identity defaults = %#v", result)
	}
	if result.Profile.ChunkRows == nil || *result.Profile.ChunkRows != 400_000 ||
		result.Profile.OutputChunkRows == nil || *result.Profile.OutputChunkRows != 400_000 ||
		result.Profile.UploadConcurrency == nil || *result.Profile.UploadConcurrency != 10 {
		t.Fatalf("known profile defaults = %#v", result.Profile)
	}
	if result.Profile.DatasetBytes != &datasetBytes ||
		result.Profile.InMemoryRowWidthBytes != &rowWidth ||
		!reflect.DeepEqual(result.Profile.FileBytes, workload.Profile.FileBytes) {
		t.Fatalf("measured evidence was not preserved: %#v", result.Profile)
	}
	if result.Profile.ExpandedBytes != nil ||
		result.Profile.OutputRowWidthBytes != nil ||
		result.Profile.DecodedBytes != nil ||
		result.Profile.ExpansionRatio != nil {
		t.Fatalf("template manufactured runtime evidence: %#v", result.Profile)
	}
	result.Profile.FileBytes[0] = 1
	if workload.Profile.FileBytes[0] != 600 {
		t.Fatal("ApplyJobTemplateDefaults() aliases caller-owned slices")
	}
}

func TestApplyJobTemplateDefaultsSelectsSparkAlternative(t *testing.T) {
	t.Parallel()
	result, err := ApplyJobTemplateDefaults(
		"get_core_deposit_accounts",
		Workload{Runner: RunnerSpark, CurrentCPUMilli: 2_000},
	)
	if err != nil {
		t.Fatalf("ApplyJobTemplateDefaults() error = %v", err)
	}
	if result.Runner != RunnerSpark || result.Family != FamilySparkCSVIngestion {
		t.Fatalf("Spark route = %q/%q", result.Runner, result.Family)
	}
	if result.Profile.OutputChunkRows != nil || result.Profile.UploadConcurrency != nil {
		t.Fatalf("Spark route received pandas defaults: %#v", result.Profile)
	}
	template, err := LookupJobTemplate("get_core_deposit_accounts")
	if err != nil {
		t.Fatalf("LookupJobTemplate() error = %v", err)
	}
	if template.DefaultFamily != FamilyChangeDetectionConcat {
		t.Fatalf("default family = %q, want change detection", template.DefaultFamily)
	}
	if !strings.Contains(template.RunnerChoices[2].Condition, "backfill") {
		t.Fatalf("Spark route condition = %q, want visible backfill condition", template.RunnerChoices[2].Condition)
	}
}

func TestDepositMetadataExposesRouteSpecificAuxiliaryInput(t *testing.T) {
	t.Parallel()
	template, err := LookupJobTemplate("get_data_eng_core_deposit_account_metadata")
	if err != nil {
		t.Fatalf("LookupJobTemplate() error = %v", err)
	}
	if template.AuxiliaryInput != AuxiliaryInputNone {
		t.Fatalf("default auxiliary input = %q, want none", template.AuxiliaryInput)
	}
	for _, route := range template.RunnerChoices {
		want := AuxiliaryInputNone
		if route.Runner == RunnerSpark {
			want = AuxiliaryInputUnchanged
			if !containsProvenanceFile(route.Provenance, "ds-jobs/src/datascience_jobs/runner/spark_ra_csv_ingestion.py") {
				t.Fatalf("Spark provenance = %#v, want SparkRaCsvIngestionRunner", route.Provenance)
			}
		}
		if route.AuxiliaryInput != want {
			t.Errorf("%s auxiliary input = %q, want %q", route.Runner, route.AuxiliaryInput, want)
		}
	}
}

func TestApplyJobTemplateDefaultsRejectsContradictions(t *testing.T) {
	t.Parallel()
	wrongChunk := uint64(399_999)
	tests := []struct {
		name     string
		workload Workload
		want     string
	}{
		{
			name:     "job",
			workload: Workload{Job: "get_assumption_sets"},
			want:     "contradicts template",
		},
		{
			name: "runner family",
			workload: Workload{
				Runner: RunnerSpark,
				Family: FamilyChunkedPandas,
			},
			want: "allowed routes",
		},
		{
			name: "known chunk",
			workload: Workload{
				Profile: Profile{ChunkRows: &wrongChunk},
			},
			want: "chunk_rows 399999 contradicts known template value 400000",
		},
	}
	for _, test := range tests {
		_, err := ApplyJobTemplateDefaults("get_core_loan_amortization_tables", test.workload)
		if err == nil || !strings.Contains(err.Error(), test.want) {
			t.Errorf("%s error = %v, want substring %q", test.name, err, test.want)
		}
	}
}

func TestLookupJobTemplateRejectsBlankAndUnknownJobs(t *testing.T) {
	t.Parallel()
	for _, name := range []string{" ", "not_a_job"} {
		_, err := LookupJobTemplate(name)
		if err == nil ||
			!strings.Contains(err.Error(), "available canonical jobs") ||
			!strings.Contains(err.Error(), "get_core_loan_amortization_tables") ||
			!strings.Contains(err.Error(), "get_deposit_financial_statement_breakdown") {
			t.Errorf("LookupJobTemplate(%q) error = %v", name, err)
		}
	}
}

func TestLookupJobTemplateRejectsOverlongNameWithoutEchoingIt(t *testing.T) {
	t.Parallel()
	name := strings.Repeat("界", MaxJobNameLength+1)
	_, err := LookupJobTemplate(name)
	if err == nil ||
		!strings.Contains(err.Error(), "exceeds maximum") ||
		strings.Contains(err.Error(), name) {
		t.Fatalf("LookupJobTemplate(overlong) error = %v", err)
	}
}

func TestHistoricalLatestRequiresFullVersionRootEvidence(t *testing.T) {
	t.Parallel()
	template, err := LookupJobTemplate("relationship_signals_time_series_agg_cp_to_snowflake")
	if err != nil {
		t.Fatalf("LookupJobTemplate() error = %v", err)
	}
	for _, required := range []string{
		"full VersionPartition root",
		"no DatePartition",
		"recursive file_bytes",
		"largest_file_bytes",
		"never latest-DatePartition",
	} {
		if !strings.Contains(template.InputNote, required) {
			t.Errorf("InputNote = %q, want %q", template.InputNote, required)
		}
	}
}

func TestCatalogEncodesFamiliesInputsAndKnownConcurrency(t *testing.T) {
	t.Parallel()
	threaded, err := LookupJobTemplate("assumption_sets_to_internal_adls")
	if err != nil {
		t.Fatalf("LookupJobTemplate(threaded) error = %v", err)
	}
	if threaded.DefaultFamily != FamilyThreadedByteCopy ||
		threaded.InputMode != InputModeDatedHDM ||
		threaded.CopyConcurrency != 10 {
		t.Fatalf("threaded copy template = %#v", threaded)
	}
	parquet, err := LookupJobTemplate("monthly_core_deposit_accounts_copy_client")
	if err != nil {
		t.Fatalf("LookupJobTemplate(parquet) error = %v", err)
	}
	if parquet.DefaultFamily != FamilyParquetToCSV ||
		parquet.InputMode != InputModeAuditSelected ||
		parquet.OutputChunkRows != 500_000 ||
		parquet.UploadConcurrency != 10 {
		t.Fatalf("parquet template = %#v", parquet)
	}
	encoded, err := LookupJobTemplate("get_assumption_sets")
	if err != nil {
		t.Fatalf("LookupJobTemplate(encoded) error = %v", err)
	}
	if encoded.UploadConcurrency != 10 {
		t.Fatalf("encoded upload concurrency = %d, want 10", encoded.UploadConcurrency)
	}
	for _, template := range ListJobTemplates() {
		switch template.DefaultFamily {
		case FamilyChunkedPandas,
			FamilyWholeFilePandas,
			FamilyChangeDetectionConcat,
			FamilyCompressedBase64JSON,
			FamilyParquetToCSV:
			if template.UploadConcurrency != 10 {
				t.Errorf("%s upload concurrency = %d, want 10", template.Job, template.UploadConcurrency)
			}
		}
	}
	coreOther, err := LookupJobTemplate("get_core_other_accounts")
	if err != nil {
		t.Fatalf("LookupJobTemplate(core other) error = %v", err)
	}
	if !strings.Contains(coreOther.RunnerChoices[1].Condition, "resource_tags.size") {
		t.Fatalf("core other pod condition = %q", coreOther.RunnerChoices[1].Condition)
	}
	for _, provenance := range parquet.Provenance {
		if strings.HasPrefix(provenance.File, "/") || strings.Contains(provenance.File, "..") {
			t.Fatalf("provenance is not repo-relative: %#v", provenance)
		}
	}
}

func TestCatalogValidationRejectsInvalidRouteAuxiliaryPolicy(t *testing.T) {
	t.Parallel()
	template := ListJobTemplates()[0]
	template.RunnerChoices[0].AuxiliaryInput = AuxiliaryInputPolicy("invalid")
	err := validateJobTemplate(template)
	if err == nil || !strings.Contains(err.Error(), "auxiliary input policy") {
		t.Fatalf("validateJobTemplate() error = %v", err)
	}

	template = ListJobTemplates()[0]
	template.RunnerChoices[0].AuxiliaryInput = AuxiliaryInputUnchanged
	if template.AuxiliaryInput == AuxiliaryInputUnchanged {
		template.RunnerChoices[0].AuxiliaryInput = AuxiliaryInputNone
	}
	err = validateJobTemplate(template)
	if err == nil || !strings.Contains(err.Error(), "contradicts template default") {
		t.Fatalf("validateJobTemplate(default route auxiliary mismatch) error = %v", err)
	}
}

func TestCatalogProvenanceUsesConcreteImplementations(t *testing.T) {
	t.Parallel()
	tests := []struct {
		job  string
		file string
	}{
		{"assumption_sets_to_internal_adls", "di_pyjobs/action/move.py"},
		{"get_core_other_accounts", "di_pyjobs/job/standard/batch.py"},
		{"get_assumption_sets", "de-jobs/src/datamart/transformations/aggregations.py"},
		{"get_core_deposit_accounts", "ds-jobs/src/datascience_jobs/runner/spark_ra_csv_ingestion.py"},
	}
	for _, test := range tests {
		template, err := LookupJobTemplate(test.job)
		if err != nil {
			t.Fatalf("LookupJobTemplate(%q) error = %v", test.job, err)
		}
		found := containsProvenanceFile(template.Provenance, test.file)
		for _, route := range template.RunnerChoices {
			found = found || containsProvenanceFile(route.Provenance, test.file)
		}
		if !found {
			t.Errorf("%s provenance does not contain %q", test.job, test.file)
		}
	}
}

func containsProvenanceFile(references []ProvenanceRef, file string) bool {
	for _, reference := range references {
		if reference.File == file {
			return true
		}
	}
	return false
}
