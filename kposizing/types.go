package kposizing

import (
	"fmt"
	"strings"
	"unicode/utf8"
)

const (
	// MaxJobNameLength is the maximum job name length in Unicode code points.
	MaxJobNameLength = 256
	// MaxCPURationaleLength is the maximum CPU rationale length in Unicode code points.
	MaxCPURationaleLength = 1024
)

// Runner identifies the execution environment being sized.
type Runner string

const (
	// RunnerBatch identifies a non-Kubernetes batch runner.
	RunnerBatch Runner = "batch"
	// RunnerK8sPod identifies a Kubernetes pod runner.
	RunnerK8sPod Runner = "k8s_pod"
	// RunnerSpark identifies a Spark executor-based runner.
	RunnerSpark Runner = "spark"
)

// Validate rejects an unknown runner.
func (r Runner) Validate() error {
	switch r {
	case RunnerBatch, RunnerK8sPod, RunnerSpark:
		return nil
	default:
		return fmt.Errorf("runner %q is unsupported; use batch, k8s_pod, or spark", r)
	}
}

// ParseRunner validates and returns a runner.
func ParseRunner(value string) (Runner, error) {
	runner := Runner(value)
	if err := runner.Validate(); err != nil {
		return "", err
	}
	return runner, nil
}

// TransformationFamily identifies one supported working-set model.
type TransformationFamily string

const (
	// FamilyStorageAPICopy models storage or API copy operations.
	FamilyStorageAPICopy TransformationFamily = "storage_api_copy"
	// FamilyThreadedByteCopy models concurrent whole-byte file copies.
	FamilyThreadedByteCopy TransformationFamily = "threaded_byte_copy"
	// FamilyChunkedPandas models chunked pandas processing with source caching.
	FamilyChunkedPandas TransformationFamily = "chunked_pandas"
	// FamilyWholeFilePandas models whole-file pandas transforms.
	FamilyWholeFilePandas TransformationFamily = "whole_file_pandas"
	// FamilyChangeDetectionConcat models changed/unchanged frame concatenation.
	FamilyChangeDetectionConcat TransformationFamily = "change_detection_concat"
	// FamilyCompressedBase64JSON models compressed, base64-encoded JSON transforms.
	FamilyCompressedBase64JSON TransformationFamily = "compressed_base64_json"
	// FamilyParquetToCSV models sequential parquet partition conversion.
	FamilyParquetToCSV TransformationFamily = "parquet_to_csv"
	// FamilySparkCSVIngestion models per-executor Spark CSV ingestion.
	FamilySparkCSVIngestion TransformationFamily = "spark_csv_ingestion"
)

// Validate rejects an unknown transformation family.
func (f TransformationFamily) Validate() error {
	switch f {
	case FamilyStorageAPICopy,
		FamilyThreadedByteCopy,
		FamilyChunkedPandas,
		FamilyWholeFilePandas,
		FamilyChangeDetectionConcat,
		FamilyCompressedBase64JSON,
		FamilyParquetToCSV,
		FamilySparkCSVIngestion:
		return nil
	default:
		return fmt.Errorf("transformation family %q is unsupported", f)
	}
}

// ParseTransformationFamily validates and returns a transformation family.
func ParseTransformationFamily(value string) (TransformationFamily, error) {
	family := TransformationFamily(value)
	if err := family.Validate(); err != nil {
		return "", err
	}
	return family, nil
}

// Ratio is an exact non-negative rational coefficient.
type Ratio struct {
	Numerator   uint64 `json:"numerator"`
	Denominator uint64 `json:"denominator"`
}

// String returns the stable numerator/denominator representation.
func (r Ratio) String() string {
	return fmt.Sprintf("%d/%d", r.Numerator, r.Denominator)
}

// CPUEvidence is an explicit CPU recommendation independent of memory sizing.
type CPUEvidence struct {
	RecommendedMilli int64  `json:"recommended_milli"`
	Rationale        string `json:"rationale"`
}

// Workload identifies a job and its pre-run sizing evidence.
type Workload struct {
	Job             string               `json:"job"`
	Runner          Runner               `json:"runner"`
	Family          TransformationFamily `json:"family"`
	CurrentCPUMilli int64                `json:"current_cpu_milli"`
	CPUEvidence     *CPUEvidence         `json:"cpu_evidence,omitempty"`
	Profile         Profile              `json:"profile"`
}

// Profile contains only bounded, pre-run features used by supported models.
//
// Pointer fields distinguish absent evidence from an explicitly observed zero.
type Profile struct {
	DatasetBytes                 *uint64  `json:"dataset_bytes,omitempty"`
	APIBufferBytes               *uint64  `json:"api_buffer_bytes,omitempty"`
	LargestFileBytes             *uint64  `json:"largest_file_bytes,omitempty"`
	FileBytes                    []uint64 `json:"file_bytes,omitempty"`
	TopConcurrentFileBytes       []uint64 `json:"top_concurrent_file_bytes,omitempty"`
	ChangedSourceBytes           *uint64  `json:"changed_source_bytes,omitempty"`
	UnchangedSourceBytes         *uint64  `json:"unchanged_source_bytes,omitempty"`
	ExpandedBytes                *uint64  `json:"expanded_bytes,omitempty"`
	ChangedExpandedBytes         *uint64  `json:"changed_expanded_bytes,omitempty"`
	UnchangedExpandedBytes       *uint64  `json:"unchanged_expanded_bytes,omitempty"`
	RowCount                     *uint64  `json:"row_count,omitempty"`
	InMemoryRowWidthBytes        *uint64  `json:"in_memory_row_width_bytes,omitempty"`
	ChunkRows                    *uint64  `json:"chunk_rows,omitempty"`
	OutputBytes                  *uint64  `json:"output_bytes,omitempty"`
	OutputRowWidthBytes          *uint64  `json:"output_row_width_bytes,omitempty"`
	OutputChunkRows              *uint64  `json:"output_chunk_rows,omitempty"`
	UploadConcurrency            *int     `json:"upload_concurrency,omitempty"`
	CopyConcurrency              *int     `json:"copy_concurrency,omitempty"`
	EncodedBytes                 *uint64  `json:"encoded_bytes,omitempty"`
	DecodedBytes                 *uint64  `json:"decoded_bytes,omitempty"`
	MaxRowDecodeTransientBytes   *uint64  `json:"max_row_decode_transient_bytes,omitempty"`
	ExpansionRatio               *Ratio   `json:"expansion_ratio,omitempty"`
	LargestPartitionBytes        *uint64  `json:"largest_partition_bytes,omitempty"`
	ExpandedPartitionBytes       *uint64  `json:"expanded_partition_bytes,omitempty"`
	PartitionCount               *uint64  `json:"partition_count,omitempty"`
	SparkExecutorCount           *int     `json:"spark_executor_count,omitempty"`
	SparkTasksPerExecutor        *int     `json:"spark_tasks_per_executor,omitempty"`
	SparkPartitionBytes          *uint64  `json:"spark_partition_bytes,omitempty"`
	SparkCastBufferBytesPerTask  *uint64  `json:"spark_cast_buffer_bytes_per_task,omitempty"`
	SparkWriteBufferBytesPerTask *uint64  `json:"spark_write_buffer_bytes_per_task,omitempty"`
	SparkShuffleBytesPerExecutor *uint64  `json:"spark_shuffle_bytes_per_executor,omitempty"`
	SparkCacheBytesPerExecutor   *uint64  `json:"spark_cache_bytes_per_executor,omitempty"`
}

// Component is one deterministic contribution to estimated peak memory.
type Component struct {
	Name  string `json:"name"`
	Bytes uint64 `json:"bytes"`
}

// RequestedUnit identifies what one recommended tier applies to.
type RequestedUnit string

const (
	// RequestedUnitRunner means the tier applies to one batch process or pod.
	RequestedUnitRunner RequestedUnit = "runner"
	// RequestedUnitExecutor means the tier applies to each Spark executor.
	RequestedUnitExecutor RequestedUnit = "executor"
)

// ClusterContext reports Spark cluster context without changing tier scope.
type ClusterContext struct {
	ExecutorCount             int    `json:"executor_count"`
	EstimatedClusterPeakBytes uint64 `json:"estimated_cluster_peak_bytes"`
}

// Estimate is a deterministic, componentized sizing recommendation.
type Estimate struct {
	Job                  string               `json:"job"`
	Runner               Runner               `json:"runner"`
	Family               TransformationFamily `json:"family"`
	RequestedUnit        RequestedUnit        `json:"requested_unit"`
	Components           []Component          `json:"components"`
	PeakBytes            uint64               `json:"peak_bytes"`
	HeadroomBytes        uint64               `json:"headroom_bytes"`
	RequestedBytes       uint64               `json:"requested_bytes"`
	RecommendedTierBytes uint64               `json:"recommended_tier_bytes"`
	CurrentCPUMilli      int64                `json:"current_cpu_milli"`
	RecommendedCPUMilli  int64                `json:"recommended_cpu_milli"`
	CPURationale         string               `json:"cpu_rationale"`
	Cluster              *ClusterContext      `json:"cluster,omitempty"`
	Evidence             []string             `json:"evidence"`
	Assumptions          []string             `json:"assumptions"`
	Warnings             []string             `json:"warnings"`
}

// TierExceededError reports a request above the largest configured tier.
type TierExceededError struct {
	RequestedBytes   uint64
	LargestTierBytes uint64
}

// Error returns an actionable tier failure.
func (e *TierExceededError) Error() string {
	return fmt.Sprintf(
		"requested memory %d bytes exceeds largest supported tier %d bytes; "+
			"add a reviewed tier or reduce the workload before retrying",
		e.RequestedBytes,
		e.LargestTierBytes,
	)
}

func validateCPU(workload Workload) (int64, string, error) {
	if workload.CurrentCPUMilli <= 0 {
		return 0, "", fmt.Errorf("current_cpu_milli must be greater than zero")
	}
	if workload.CPUEvidence == nil {
		return workload.CurrentCPUMilli,
			"preserved current CPU because memory sizing is not CPU evidence", nil
	}
	if workload.CPUEvidence.RecommendedMilli <= 0 {
		return 0, "", fmt.Errorf("cpu_evidence.recommended_milli must be greater than zero")
	}
	rawRationale := workload.CPUEvidence.Rationale
	if !utf8.ValidString(rawRationale) {
		return 0, "", fmt.Errorf("cpu_evidence.rationale must contain valid UTF-8")
	}
	if utf8.RuneCountInString(rawRationale) > MaxCPURationaleLength {
		return 0, "", fmt.Errorf(
			"cpu_evidence.rationale exceeds maximum length %d Unicode code points",
			MaxCPURationaleLength,
		)
	}
	rationale := strings.TrimSpace(rawRationale)
	if rationale == "" {
		return 0, "", fmt.Errorf("cpu_evidence.rationale must not be empty")
	}
	return workload.CPUEvidence.RecommendedMilli, rationale, nil
}
