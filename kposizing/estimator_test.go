package kposizing

import (
	"encoding/json"
	"errors"
	"math"
	"reflect"
	"strings"
	"testing"
)

func testConfig() Config {
	return Config{
		BaselineBytes:          100,
		SparkJVMBaselineBytes:  200,
		APIMetadataBytes:       10,
		SDKDuplication:         Ratio{Numerator: 2, Denominator: 1},
		FrameCopies:            Ratio{Numerator: 2, Denominator: 1},
		SerializationFactor:    Ratio{Numerator: 2, Denominator: 1},
		ConcatFactor:           Ratio{Numerator: 2, Denominator: 1},
		SparkCSVWorkingFactor:  Ratio{Numerator: 3, Denominator: 1},
		Headroom:               Ratio{Numerator: 1, Denominator: 4},
		SupportedTiersBytes:    []uint64{200, 400, 600, 1_000},
		DefaultCopyConcurrency: 2,
		MaxFileEvidence:        20,
		MaxConcurrency:         10,
		MaxTasksPerExecutor:    10,
		MaxSupportedTiers:      10,
		MaxExpansionRatio:      Ratio{Numerator: 100, Denominator: 1},
	}
}

func testEstimator(t *testing.T) *Estimator {
	t.Helper()
	estimator, err := NewEstimator(testConfig())
	if err != nil {
		t.Fatalf("NewEstimator() error = %v", err)
	}
	return estimator
}

func baseWorkload(family TransformationFamily, profile Profile) Workload {
	runner := RunnerK8sPod
	if family == FamilySparkCSVIngestion {
		runner = RunnerSpark
	}
	return Workload{
		Job:             "example_job",
		Runner:          runner,
		Family:          family,
		CurrentCPUMilli: 2_000,
		Profile:         profile,
	}
}

func uploadProfile() Profile {
	return Profile{
		UploadConcurrency:   intPointer(2),
		OutputChunkRows:     uint64Pointer(5),
		OutputRowWidthBytes: uint64Pointer(3),
	}
}

func TestEstimatorFamilyFormulas(t *testing.T) {
	t.Parallel()
	upload := uploadProfile()
	tests := []struct {
		name       string
		workload   Workload
		peak       uint64
		requested  uint64
		tier       uint64
		components []string
	}{
		{
			name: "storage API explicit buffer",
			workload: baseWorkload(FamilyStorageAPICopy, Profile{
				APIBufferBytes:   uint64Pointer(20),
				LargestFileBytes: uint64Pointer(5),
				DatasetBytes:     uint64Pointer(1_000),
			}),
			peak:      140,
			requested: 175,
			tier:      200,
			components: []string{
				"baseline", "api_request_metadata", "sdk_file_buffer", "explicit_api_buffer",
			},
		},
		{
			name: "threaded byte copy",
			workload: baseWorkload(FamilyThreadedByteCopy, Profile{
				FileBytes:       []uint64{10, 8, 3},
				DatasetBytes:    uint64Pointer(21),
				CopyConcurrency: intPointer(2),
			}),
			peak:       136,
			requested:  170,
			tier:       200,
			components: []string{"baseline", "concurrent_sdk_buffers"},
		},
		{
			name: "chunked pandas",
			workload: baseWorkload(FamilyChunkedPandas, mergeProfile(upload, Profile{
				ChangedSourceBytes:    uint64Pointer(50),
				UnchangedSourceBytes:  uint64Pointer(25),
				ChunkRows:             uint64Pointer(10),
				InMemoryRowWidthBytes: uint64Pointer(2),
				RowCount:              uint64Pointer(100),
			})),
			peak:      275,
			requested: 344,
			tier:      400,
			components: []string{
				"baseline", "changed_source_cache", "unchanged_source_cache",
				"chunk_frame_copies", "upload_serialization",
			},
		},
		{
			name: "whole-file pandas",
			workload: baseWorkload(FamilyWholeFilePandas, mergeProfile(upload, Profile{
				LargestFileBytes:      uint64Pointer(30),
				ExpandedBytes:         uint64Pointer(100),
				RowCount:              uint64Pointer(20),
				InMemoryRowWidthBytes: uint64Pointer(5),
			})),
			peak:      390,
			requested: 488,
			tier:      600,
			components: []string{
				"baseline", "source_cache", "expanded_concat_frames", "upload_serialization",
			},
		},
		{
			name: "change detection concat",
			workload: baseWorkload(FamilyChangeDetectionConcat, mergeProfile(upload, Profile{
				ChangedSourceBytes:     uint64Pointer(30),
				UnchangedSourceBytes:   uint64Pointer(20),
				ChangedExpandedBytes:   uint64Pointer(60),
				UnchangedExpandedBytes: uint64Pointer(40),
			})),
			peak:      410,
			requested: 513,
			tier:      600,
			components: []string{
				"baseline", "changed_source_cache", "unchanged_source_cache",
				"expanded_concat_frames", "upload_serialization",
			},
		},
		{
			name: "compressed base64 JSON",
			workload: baseWorkload(FamilyCompressedBase64JSON, mergeProfile(upload, Profile{
				EncodedBytes:               uint64Pointer(20),
				DecodedBytes:               uint64Pointer(50),
				OutputBytes:                uint64Pointer(40),
				MaxRowDecodeTransientBytes: uint64Pointer(5),
			})),
			peak:      275,
			requested: 344,
			tier:      400,
			components: []string{
				"baseline", "encoded_source_frame", "decoded_object", "output_object",
				"max_row_decode_transient", "upload_serialization",
			},
		},
		{
			name: "parquet to CSV",
			workload: baseWorkload(FamilyParquetToCSV, mergeProfile(upload, Profile{
				LargestPartitionBytes:  uint64Pointer(30),
				ExpandedPartitionBytes: uint64Pointer(100),
				PartitionCount:         uint64Pointer(4),
				DatasetBytes:           uint64Pointer(120),
			})),
			peak:      390,
			requested: 488,
			tier:      600,
			components: []string{
				"baseline", "largest_parquet_partition",
				"expanded_partition_concat", "upload_serialization",
			},
		},
		{
			name: "Spark CSV per executor",
			workload: baseWorkload(FamilySparkCSVIngestion, Profile{
				SparkExecutorCount:           intPointer(3),
				SparkTasksPerExecutor:        intPointer(2),
				SparkPartitionBytes:          uint64Pointer(10),
				SparkCastBufferBytesPerTask:  uint64Pointer(2),
				SparkWriteBufferBytesPerTask: uint64Pointer(3),
				SparkShuffleBytesPerExecutor: uint64Pointer(5),
				SparkCacheBytesPerExecutor:   uint64Pointer(7),
			}),
			peak:      282,
			requested: 353,
			tier:      400,
			components: []string{
				"baseline", "concurrent_task_working_sets", "executor_shuffle", "executor_cache",
			},
		},
	}

	for _, test := range tests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			result, err := testEstimator(t).Estimate(test.workload)
			if err != nil {
				t.Fatalf("Estimate() error = %v", err)
			}
			if result.PeakBytes != test.peak {
				t.Errorf("PeakBytes = %d, want %d", result.PeakBytes, test.peak)
			}
			if result.RequestedBytes != test.requested {
				t.Errorf("RequestedBytes = %d, want %d", result.RequestedBytes, test.requested)
			}
			if result.RecommendedTierBytes != test.tier {
				t.Errorf("RecommendedTierBytes = %d, want %d", result.RecommendedTierBytes, test.tier)
			}
			names := make([]string, len(result.Components))
			for index, component := range result.Components {
				names[index] = component.Name
			}
			if !reflect.DeepEqual(names, test.components) {
				t.Errorf("component names = %v, want %v", names, test.components)
			}
			if result.RecommendedCPUMilli != test.workload.CurrentCPUMilli {
				t.Errorf(
					"RecommendedCPUMilli = %d, want preserved %d",
					result.RecommendedCPUMilli,
					test.workload.CurrentCPUMilli,
				)
			}
			if len(result.Evidence) == 0 || len(result.Assumptions) == 0 || len(result.Warnings) == 0 {
				t.Error("evidence, assumptions, and warnings must all be populated")
			}
			if test.workload.Family == FamilySparkCSVIngestion {
				if result.RequestedUnit != RequestedUnitExecutor {
					t.Errorf("RequestedUnit = %q, want executor", result.RequestedUnit)
				}
				if result.Cluster == nil || result.Cluster.EstimatedClusterPeakBytes != 846 {
					t.Errorf("Cluster = %#v, want peak 846", result.Cluster)
				}
			}
		})
	}
}

func TestEstimateIsDeterministicJSON(t *testing.T) {
	t.Parallel()
	workload := baseWorkload(FamilyThreadedByteCopy, Profile{
		TopConcurrentFileBytes: []uint64{20, 10},
		CopyConcurrency:        intPointer(2),
	})
	first, err := testEstimator(t).Estimate(workload)
	if err != nil {
		t.Fatalf("first Estimate() error = %v", err)
	}
	second, err := testEstimator(t).Estimate(workload)
	if err != nil {
		t.Fatalf("second Estimate() error = %v", err)
	}
	firstJSON, err := json.Marshal(first)
	if err != nil {
		t.Fatalf("json.Marshal(first) error = %v", err)
	}
	secondJSON, err := json.Marshal(second)
	if err != nil {
		t.Fatalf("json.Marshal(second) error = %v", err)
	}
	if string(firstJSON) != string(secondJSON) {
		t.Fatalf("deterministic JSON mismatch:\n%s\n%s", firstJSON, secondJSON)
	}
}

func TestEstimateRoundsUpAndReturnsTypedOverTierError(t *testing.T) {
	t.Parallel()
	config := testConfig()
	config.BaselineBytes = 110
	config.APIMetadataBytes = 10
	config.Headroom = Ratio{Numerator: 1, Denominator: 4}
	config.SupportedTiersBytes = []uint64{180, 181}
	estimator, err := NewEstimator(config)
	if err != nil {
		t.Fatalf("NewEstimator() error = %v", err)
	}
	workload := baseWorkload(
		FamilyStorageAPICopy,
		Profile{
			APIBufferBytes:   uint64Pointer(0),
			LargestFileBytes: uint64Pointer(12),
		},
	)
	result, err := estimator.Estimate(workload)
	if err != nil {
		t.Fatalf("Estimate() error = %v", err)
	}
	if result.PeakBytes != 144 || result.HeadroomBytes != 36 ||
		result.RequestedBytes != 180 || result.RecommendedTierBytes != 180 {
		t.Fatalf("unexpected exact-tier estimate: %#v", result)
	}

	workload.Profile.APIBufferBytes = uint64Pointer(1)
	_, err = estimator.Estimate(workload)
	var tierError *TierExceededError
	if !errors.As(err, &tierError) {
		t.Fatalf("Estimate() error = %v, want TierExceededError", err)
	}
	if tierError.RequestedBytes != 182 || tierError.LargestTierBytes != 181 {
		t.Fatalf("TierExceededError = %#v", tierError)
	}
}

func TestEstimateRejectsArithmeticOverflow(t *testing.T) {
	t.Parallel()
	profile := mergeProfile(uploadProfile(), Profile{
		LargestFileBytes: uint64Pointer(1),
		ExpandedBytes:    uint64Pointer(math.MaxUint64),
	})
	_, err := testEstimator(t).Estimate(baseWorkload(FamilyWholeFilePandas, profile))
	if err == nil || !strings.Contains(err.Error(), "uint64 byte range") {
		t.Fatalf("Estimate() error = %v, want overflow error", err)
	}
}

func TestEstimateUsesExplicitCPUEvidence(t *testing.T) {
	t.Parallel()
	workload := baseWorkload(
		FamilyStorageAPICopy,
		Profile{
			APIBufferBytes:   uint64Pointer(1),
			LargestFileBytes: uint64Pointer(1),
		},
	)
	workload.CPUEvidence = &CPUEvidence{
		RecommendedMilli: 3_000,
		Rationale:        "measured CPU saturation in an equivalent bounded run",
	}
	result, err := testEstimator(t).Estimate(workload)
	if err != nil {
		t.Fatalf("Estimate() error = %v", err)
	}
	if result.RecommendedCPUMilli != 3_000 || result.CPURationale != workload.CPUEvidence.Rationale {
		t.Fatalf("CPU recommendation = %#v", result)
	}
}

func uint64Pointer(value uint64) *uint64 {
	return &value
}

func intPointer(value int) *int {
	return &value
}

func mergeProfile(base, override Profile) Profile {
	if override.UploadConcurrency == nil {
		override.UploadConcurrency = base.UploadConcurrency
	}
	if override.OutputChunkRows == nil {
		override.OutputChunkRows = base.OutputChunkRows
	}
	if override.OutputRowWidthBytes == nil {
		override.OutputRowWidthBytes = base.OutputRowWidthBytes
	}
	return override
}
