package kposizing

import (
	"math"
	"strings"
	"testing"
	"unicode/utf8"
)

func TestStorageAPICopyAlwaysIncludesLargestFileAndOptionalBuffer(t *testing.T) {
	t.Parallel()
	workload := baseWorkload(FamilyStorageAPICopy, Profile{
		LargestFileBytes: uint64Pointer(7),
		DatasetBytes:     uint64Pointer(20),
	})
	withoutBuffer, err := testEstimator(t).Estimate(workload)
	if err != nil {
		t.Fatalf("Estimate() without buffer error = %v", err)
	}
	if componentBytes(withoutBuffer.Components, "sdk_file_buffer") != 14 {
		t.Fatalf("components = %v, want 14-byte SDK buffer", withoutBuffer.Components)
	}
	if componentBytes(withoutBuffer.Components, "explicit_api_buffer") != 0 {
		t.Fatalf("components = %v, want no explicit buffer component", withoutBuffer.Components)
	}
	if !containsSubstring(withoutBuffer.Warnings, "hybrid implementation") {
		t.Fatalf("warnings = %v, want hybrid implementation warning", withoutBuffer.Warnings)
	}

	workload.Profile.APIBufferBytes = uint64Pointer(3)
	withBuffer, err := testEstimator(t).Estimate(workload)
	if err != nil {
		t.Fatalf("Estimate() with buffer error = %v", err)
	}
	if componentBytes(withBuffer.Components, "sdk_file_buffer") != 14 ||
		componentBytes(withBuffer.Components, "explicit_api_buffer") != 3 {
		t.Fatalf("components = %v, want largest-file and API buffers", withBuffer.Components)
	}
}

func TestThreadedCopyRejectsIncompleteTopConcurrentEvidence(t *testing.T) {
	t.Parallel()
	tests := []Profile{
		{
			TopConcurrentFileBytes: []uint64{10},
			CopyConcurrency:        intPointer(2),
		},
		{
			FileBytes:              []uint64{10, 8, 4},
			TopConcurrentFileBytes: []uint64{10},
			CopyConcurrency:        intPointer(2),
		},
	}
	for _, profile := range tests {
		_, err := testEstimator(t).Estimate(baseWorkload(FamilyThreadedByteCopy, profile))
		if err == nil || !strings.Contains(err.Error(), "expected exactly 2") {
			t.Fatalf("Estimate() error = %v, want incomplete top-file evidence error", err)
		}
	}

	result, err := testEstimator(t).Estimate(baseWorkload(
		FamilyThreadedByteCopy,
		Profile{
			FileBytes:       []uint64{10},
			CopyConcurrency: intPointer(2),
		},
	))
	if err != nil {
		t.Fatalf("Estimate() with complete file list error = %v", err)
	}
	if componentBytes(result.Components, "concurrent_sdk_buffers") != 20 {
		t.Fatalf("components = %v, want one provable active file", result.Components)
	}
}

func TestChunkedPandasUsesShortFinalChunk(t *testing.T) {
	t.Parallel()
	profile := mergeProfile(uploadProfile(), Profile{
		ChangedSourceBytes:    uint64Pointer(50),
		UnchangedSourceBytes:  uint64Pointer(25),
		ChunkRows:             uint64Pointer(10),
		RowCount:              uint64Pointer(3),
		InMemoryRowWidthBytes: uint64Pointer(2),
	})
	result, err := testEstimator(t).Estimate(baseWorkload(FamilyChunkedPandas, profile))
	if err != nil {
		t.Fatalf("Estimate() error = %v", err)
	}
	if componentBytes(result.Components, "chunk_frame_copies") != 12 {
		t.Fatalf("components = %v, want frame copies based on three effective rows", result.Components)
	}
	if !containsSubstring(result.Evidence, "effective_chunk_rows=3") {
		t.Fatalf("evidence = %v, want effective chunk rows", result.Evidence)
	}
	if !containsSubstring(result.Assumptions, "min(row_count,chunk_rows)") {
		t.Fatalf("assumptions = %v, want effective-row formula", result.Assumptions)
	}
}

func TestEncodedRatioValidatesRedundantExplicitEvidence(t *testing.T) {
	t.Parallel()
	profile := mergeProfile(uploadProfile(), Profile{
		EncodedBytes:   uint64Pointer(10),
		DecodedBytes:   uint64Pointer(30),
		OutputBytes:    uint64Pointer(35),
		ExpansionRatio: &Ratio{Numerator: 4, Denominator: 1},
	})
	result, err := testEstimator(t).Estimate(baseWorkload(FamilyCompressedBase64JSON, profile))
	if err != nil {
		t.Fatalf("Estimate() error = %v", err)
	}
	if !containsSubstring(result.Evidence, "expansion_ratio=4/1") ||
		!containsSubstring(result.Assumptions, "upper bound") {
		t.Fatalf(
			"evidence/assumptions = %v / %v, want ratio disclosure",
			result.Evidence,
			result.Assumptions,
		)
	}

	profile.OutputBytes = uint64Pointer(41)
	_, err = testEstimator(t).Estimate(baseWorkload(FamilyCompressedBase64JSON, profile))
	if err == nil || !strings.Contains(err.Error(), "output_bytes 41 exceeds expansion_ratio bound 40") {
		t.Fatalf("Estimate() error = %v, want redundant evidence contradiction", err)
	}
}

func TestFileEvidenceCrossChecks(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name    string
		profile Profile
		want    string
	}{
		{
			name: "largest exceeds dataset",
			profile: Profile{
				LargestFileBytes: uint64Pointer(11),
				DatasetBytes:     uint64Pointer(10),
			},
			want: "largest_file_bytes 11 cannot exceed dataset_bytes 10",
		},
		{
			name: "top total exceeds dataset",
			profile: Profile{
				TopConcurrentFileBytes: []uint64{7, 5},
				DatasetBytes:           uint64Pointer(10),
				CopyConcurrency:        intPointer(2),
			},
			want: "top_concurrent_file_bytes total 12 cannot exceed dataset_bytes 10",
		},
		{
			name: "top largest mismatch",
			profile: Profile{
				TopConcurrentFileBytes: []uint64{7, 5},
				LargestFileBytes:       uint64Pointer(8),
				DatasetBytes:           uint64Pointer(20),
				CopyConcurrency:        intPointer(2),
			},
			want: "top_concurrent_file_bytes[0] 7 contradicts largest_file_bytes 8",
		},
		{
			name: "top total overflow",
			profile: Profile{
				TopConcurrentFileBytes: []uint64{math.MaxUint64, 1},
				CopyConcurrency:        intPointer(2),
			},
			want: "top_concurrent_file_bytes total exceeds the uint64 byte range",
		},
	}
	for _, test := range tests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			_, err := testEstimator(t).Estimate(baseWorkload(FamilyThreadedByteCopy, test.profile))
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("Estimate() error = %v, want substring %q", err, test.want)
			}
		})
	}
}

func TestRuntimeTextBoundsUseUnicodeCodePoints(t *testing.T) {
	t.Parallel()
	if utf8.RuneCountInString(strings.Repeat("界", MaxJobNameLength)) != MaxJobNameLength {
		t.Fatal("test setup did not create the expected Unicode job length")
	}
	valid := baseWorkload(
		FamilyStorageAPICopy,
		Profile{LargestFileBytes: uint64Pointer(1)},
	)
	valid.Job = strings.Repeat("界", MaxJobNameLength)
	valid.CPUEvidence = &CPUEvidence{
		RecommendedMilli: 2_000,
		Rationale:        strings.Repeat("界", MaxCPURationaleLength),
	}
	if _, err := testEstimator(t).Estimate(valid); err != nil {
		t.Fatalf("Estimate() at text bounds error = %v", err)
	}

	tooLongJob := valid
	tooLongJob.Job += "界"
	if _, err := testEstimator(t).Estimate(tooLongJob); err == nil ||
		!strings.Contains(err.Error(), "job exceeds maximum length 256 Unicode code points") {
		t.Fatalf("Estimate() job error = %v", err)
	}

	tooLongRationale := valid
	tooLongRationale.CPUEvidence = &CPUEvidence{
		RecommendedMilli: 2_000,
		Rationale:        strings.Repeat("界", MaxCPURationaleLength+1),
	}
	if _, err := testEstimator(t).Estimate(tooLongRationale); err == nil ||
		!strings.Contains(err.Error(), "maximum length 1024 Unicode code points") {
		t.Fatalf("Estimate() rationale error = %v", err)
	}
}
