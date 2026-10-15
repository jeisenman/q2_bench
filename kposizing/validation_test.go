package kposizing

import (
	"reflect"
	"strings"
	"testing"
)

func TestEveryFamilyRejectsMissingRequiredEvidence(t *testing.T) {
	t.Parallel()
	upload := uploadProfile()
	tests := []struct {
		family  TransformationFamily
		profile Profile
		want    string
	}{
		{
			family:  FamilyStorageAPICopy,
			profile: Profile{APIBufferBytes: uint64Pointer(1)},
			want:    "largest file evidence is required",
		},
		{
			family:  FamilyThreadedByteCopy,
			profile: Profile{},
			want:    "top_concurrent_file_bytes or descending file_bytes is required",
		},
		{
			family: FamilyChunkedPandas,
			profile: mergeProfile(upload, Profile{
				ChangedSourceBytes:   uint64Pointer(1),
				UnchangedSourceBytes: uint64Pointer(1),
			}),
			want: "in_memory_row_width_bytes evidence is required",
		},
		{
			family: FamilyWholeFilePandas,
			profile: mergeProfile(upload, Profile{
				LargestFileBytes: uint64Pointer(1),
			}),
			want: "expanded_bytes evidence is required",
		},
		{
			family: FamilyChangeDetectionConcat,
			profile: mergeProfile(upload, Profile{
				ChangedSourceBytes:   uint64Pointer(1),
				UnchangedSourceBytes: uint64Pointer(1),
			}),
			want: "changed_expanded_bytes evidence is required",
		},
		{
			family: FamilyCompressedBase64JSON,
			profile: mergeProfile(upload, Profile{
				EncodedBytes: uint64Pointer(1),
			}),
			want: "decoded_bytes and output_bytes are required",
		},
		{
			family: FamilyParquetToCSV,
			profile: mergeProfile(upload, Profile{
				LargestPartitionBytes: uint64Pointer(1),
			}),
			want: "expanded_partition_bytes evidence is required",
		},
		{
			family: FamilySparkCSVIngestion,
			profile: Profile{
				SparkExecutorCount:    intPointer(1),
				SparkTasksPerExecutor: intPointer(1),
			},
			want: "spark_partition_bytes evidence is required",
		},
	}
	for _, test := range tests {
		test := test
		t.Run(string(test.family), func(t *testing.T) {
			t.Parallel()
			_, err := testEstimator(t).Estimate(baseWorkload(test.family, test.profile))
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("Estimate() error = %v, want substring %q", err, test.want)
			}
		})
	}
}

func TestThreadedCopyUsesVisibleDefaultButRejectsExplicitZero(t *testing.T) {
	t.Parallel()
	workload := baseWorkload(
		FamilyThreadedByteCopy,
		Profile{FileBytes: []uint64{10, 8, 3}},
	)
	result, err := testEstimator(t).Estimate(workload)
	if err != nil {
		t.Fatalf("Estimate() error = %v", err)
	}
	if result.PeakBytes != 136 {
		t.Fatalf("PeakBytes = %d, want 136 from default concurrency 2", result.PeakBytes)
	}
	if !containsSubstring(result.Assumptions, "copy_concurrency=2 from configured default") {
		t.Fatalf("Assumptions = %v, want visible default concurrency", result.Assumptions)
	}

	workload.Profile.CopyConcurrency = intPointer(0)
	_, err = testEstimator(t).Estimate(workload)
	if err == nil || !strings.Contains(err.Error(), "copy_concurrency must be greater than zero") {
		t.Fatalf("Estimate() error = %v, want zero concurrency error", err)
	}
	workload.Profile.CopyConcurrency = intPointer(-1)
	_, err = testEstimator(t).Estimate(workload)
	if err == nil || !strings.Contains(err.Error(), "copy_concurrency must be greater than zero") {
		t.Fatalf("Estimate() error = %v, want negative concurrency error", err)
	}
}

func TestCompressedExpansionRatioBoundsMissingEvidence(t *testing.T) {
	t.Parallel()
	profile := mergeProfile(uploadProfile(), Profile{
		EncodedBytes:   uint64Pointer(10),
		DecodedBytes:   uint64Pointer(30),
		ExpansionRatio: &Ratio{Numerator: 4, Denominator: 1},
	})
	result, err := testEstimator(t).Estimate(baseWorkload(FamilyCompressedBase64JSON, profile))
	if err != nil {
		t.Fatalf("Estimate() error = %v", err)
	}
	if componentBytes(result.Components, "decoded_object") != 30 {
		t.Fatalf("decoded component = %v, want explicit 30", result.Components)
	}
	if componentBytes(result.Components, "output_object") != 40 {
		t.Fatalf("output component = %v, want derived bound 40", result.Components)
	}

	profile.DecodedBytes = uint64Pointer(41)
	_, err = testEstimator(t).Estimate(baseWorkload(FamilyCompressedBase64JSON, profile))
	if err == nil || !strings.Contains(err.Error(), "exceeds expansion_ratio bound 40") {
		t.Fatalf("Estimate() error = %v, want contradictory expansion error", err)
	}
}

func TestValidationRejectsUnknownEnumsAndRunnerFamilyContradictions(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name     string
		workload Workload
		want     string
	}{
		{
			name: "unknown runner",
			workload: Workload{
				Job: "job", Runner: Runner("other"), Family: FamilyStorageAPICopy,
				CurrentCPUMilli: 2_000, Profile: Profile{APIBufferBytes: uint64Pointer(1)},
			},
			want: "runner \"other\" is unsupported",
		},
		{
			name: "unknown family",
			workload: Workload{
				Job: "job", Runner: RunnerK8sPod, Family: TransformationFamily("other"),
				CurrentCPUMilli: 2_000,
			},
			want: "transformation family \"other\" is unsupported",
		},
		{
			name: "spark family on pod",
			workload: Workload{
				Job: "job", Runner: RunnerK8sPod, Family: FamilySparkCSVIngestion,
				CurrentCPUMilli: 2_000,
			},
			want: "spark_csv_ingestion requires runner spark",
		},
		{
			name: "pod family on spark",
			workload: Workload{
				Job: "job", Runner: RunnerSpark, Family: FamilyWholeFilePandas,
				CurrentCPUMilli: 2_000,
			},
			want: "runner spark is only supported",
		},
	}
	for _, test := range tests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			_, err := testEstimator(t).Estimate(test.workload)
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("Estimate() error = %v, want substring %q", err, test.want)
			}
		})
	}
}

func TestValidationRejectsContradictoryFileAndRowEvidence(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name     string
		workload Workload
		want     string
	}{
		{
			name: "dataset total",
			workload: baseWorkload(FamilyThreadedByteCopy, Profile{
				FileBytes:    []uint64{10, 5},
				DatasetBytes: uint64Pointer(14),
			}),
			want: "dataset_bytes 14 contradicts file_bytes total 15",
		},
		{
			name: "unsorted files",
			workload: baseWorkload(FamilyThreadedByteCopy, Profile{
				FileBytes: []uint64{5, 10},
			}),
			want: "file_bytes must be sorted in descending order",
		},
		{
			name: "expanded rows",
			workload: baseWorkload(FamilyWholeFilePandas, mergeProfile(uploadProfile(), Profile{
				LargestFileBytes:      uint64Pointer(10),
				ExpandedBytes:         uint64Pointer(99),
				RowCount:              uint64Pointer(20),
				InMemoryRowWidthBytes: uint64Pointer(5),
			})),
			want: "expanded_bytes 99 contradicts",
		},
	}
	for _, test := range tests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			_, err := testEstimator(t).Estimate(test.workload)
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("Estimate() error = %v, want substring %q", err, test.want)
			}
		})
	}
}

func TestConfigValidationAndDefensiveCopy(t *testing.T) {
	t.Parallel()
	config := testConfig()
	config.SupportedTiersBytes = []uint64{200, 200}
	if _, err := NewEstimator(config); err == nil ||
		!strings.Contains(err.Error(), "strictly increasing") {
		t.Fatalf("NewEstimator() error = %v, want invalid tier error", err)
	}

	config = testConfig()
	estimator, err := NewEstimator(config)
	if err != nil {
		t.Fatalf("NewEstimator() error = %v", err)
	}
	config.SupportedTiersBytes[0] = 1
	returned := estimator.Config()
	returned.SupportedTiersBytes[0] = 2
	if estimator.Config().SupportedTiersBytes[0] != 200 {
		t.Fatal("estimator configuration aliases caller-owned tier slices")
	}
}

func TestDefaultConfigHasReviewedDefensiveTierSequence(t *testing.T) {
	t.Parallel()
	want := []uint64{
		4 * gibibyte,
		6 * gibibyte,
		8 * gibibyte,
		16 * gibibyte,
		30 * gibibyte,
		40 * gibibyte,
		56 * gibibyte,
	}
	first := DefaultConfig()
	if !reflect.DeepEqual(first.SupportedTiersBytes, want) {
		t.Fatalf("default tiers = %v, want %v", first.SupportedTiersBytes, want)
	}
	first.SupportedTiersBytes[0] = gibibyte
	second := DefaultConfig()
	if !reflect.DeepEqual(second.SupportedTiersBytes, want) {
		t.Fatalf("DefaultConfig() returned aliased tiers: %v", second.SupportedTiersBytes)
	}
}

func TestValidationRejectsUnboundedExpansionAndCPUClaims(t *testing.T) {
	t.Parallel()
	profile := mergeProfile(uploadProfile(), Profile{
		EncodedBytes:   uint64Pointer(1),
		ExpansionRatio: &Ratio{Numerator: 101, Denominator: 1},
	})
	_, err := testEstimator(t).Estimate(baseWorkload(FamilyCompressedBase64JSON, profile))
	if err == nil || !strings.Contains(err.Error(), "exceeds configured maximum") {
		t.Fatalf("Estimate() error = %v, want expansion bound error", err)
	}

	workload := baseWorkload(
		FamilyStorageAPICopy,
		Profile{
			APIBufferBytes:   uint64Pointer(1),
			LargestFileBytes: uint64Pointer(1),
		},
	)
	workload.CPUEvidence = &CPUEvidence{RecommendedMilli: 3_000}
	_, err = testEstimator(t).Estimate(workload)
	if err == nil || !strings.Contains(err.Error(), "cpu_evidence.rationale must not be empty") {
		t.Fatalf("Estimate() error = %v, want CPU evidence error", err)
	}
}

func containsSubstring(values []string, substring string) bool {
	for _, value := range values {
		if strings.Contains(value, substring) {
			return true
		}
	}
	return false
}

func componentBytes(components []Component, name string) uint64 {
	for _, component := range components {
		if component.Name == name {
			return component.Bytes
		}
	}
	return 0
}
