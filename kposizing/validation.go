package kposizing

import (
	"fmt"
	"strings"
	"unicode/utf8"
)

func validateWorkload(workload Workload, config Config) error {
	if strings.TrimSpace(workload.Job) == "" {
		return fmt.Errorf("job must not be empty")
	}
	if !utf8.ValidString(workload.Job) {
		return fmt.Errorf("job must contain valid UTF-8")
	}
	if utf8.RuneCountInString(workload.Job) > MaxJobNameLength {
		return fmt.Errorf(
			"job exceeds maximum length %d Unicode code points",
			MaxJobNameLength,
		)
	}
	if err := workload.Runner.Validate(); err != nil {
		return err
	}
	if err := workload.Family.Validate(); err != nil {
		return err
	}
	if workload.Family == FamilySparkCSVIngestion && workload.Runner != RunnerSpark {
		return fmt.Errorf("spark_csv_ingestion requires runner spark")
	}
	if workload.Family != FamilySparkCSVIngestion && workload.Runner == RunnerSpark {
		return fmt.Errorf("runner spark is only supported for spark_csv_ingestion")
	}
	if _, _, err := validateCPU(workload); err != nil {
		return err
	}
	return validateProfile(workload.Profile, config)
}

func validateProfile(profile Profile, config Config) error {
	if len(profile.FileBytes) > config.MaxFileEvidence {
		return fmt.Errorf(
			"file_bytes contains %d values; maximum is %d",
			len(profile.FileBytes),
			config.MaxFileEvidence,
		)
	}
	if len(profile.TopConcurrentFileBytes) > config.MaxFileEvidence {
		return fmt.Errorf(
			"top_concurrent_file_bytes contains %d values; maximum is %d",
			len(profile.TopConcurrentFileBytes),
			config.MaxFileEvidence,
		)
	}
	if err := validateDescendingPositive(profile.FileBytes, "file_bytes"); err != nil {
		return err
	}
	if err := validateDescendingPositive(
		profile.TopConcurrentFileBytes,
		"top_concurrent_file_bytes",
	); err != nil {
		return err
	}
	for _, item := range []struct {
		name  string
		value *int
		max   int
	}{
		{"copy_concurrency", profile.CopyConcurrency, config.MaxConcurrency},
		{"upload_concurrency", profile.UploadConcurrency, config.MaxConcurrency},
		{"spark_executor_count", profile.SparkExecutorCount, config.MaxConcurrency},
		{"spark_tasks_per_executor", profile.SparkTasksPerExecutor, config.MaxTasksPerExecutor},
	} {
		if item.value == nil {
			continue
		}
		if *item.value <= 0 {
			return fmt.Errorf("%s must be greater than zero", item.name)
		}
		if *item.value > item.max {
			return fmt.Errorf("%s %d exceeds configured maximum %d", item.name, *item.value, item.max)
		}
	}
	if profile.ExpansionRatio != nil {
		if err := validatePositiveRatio(*profile.ExpansionRatio, "expansion_ratio"); err != nil {
			return err
		}
		if ratioGreater(*profile.ExpansionRatio, config.MaxExpansionRatio) {
			return fmt.Errorf(
				"expansion_ratio %s exceeds configured maximum %s",
				profile.ExpansionRatio,
				config.MaxExpansionRatio,
			)
		}
	}
	return validateConsistentFileEvidence(profile)
}

func validateDescendingPositive(values []uint64, name string) error {
	for index, value := range values {
		if value == 0 {
			return fmt.Errorf("%s[%d] must be greater than zero", name, index)
		}
		if index > 0 && value > values[index-1] {
			return fmt.Errorf("%s must be sorted in descending order", name)
		}
	}
	return nil
}

func validateConsistentFileEvidence(profile Profile) error {
	if profile.LargestFileBytes != nil && profile.DatasetBytes != nil &&
		*profile.LargestFileBytes > *profile.DatasetBytes {
		return fmt.Errorf(
			"largest_file_bytes %d cannot exceed dataset_bytes %d",
			*profile.LargestFileBytes,
			*profile.DatasetBytes,
		)
	}
	if len(profile.TopConcurrentFileBytes) > 0 {
		topTotal, err := sumBytes(
			"top_concurrent_file_bytes total",
			profile.TopConcurrentFileBytes,
		)
		if err != nil {
			return err
		}
		if profile.DatasetBytes != nil && topTotal > *profile.DatasetBytes {
			return fmt.Errorf(
				"top_concurrent_file_bytes total %d cannot exceed dataset_bytes %d",
				topTotal,
				*profile.DatasetBytes,
			)
		}
		if profile.LargestFileBytes != nil &&
			profile.TopConcurrentFileBytes[0] != *profile.LargestFileBytes {
			return fmt.Errorf(
				"top_concurrent_file_bytes[0] %d contradicts largest_file_bytes %d",
				profile.TopConcurrentFileBytes[0],
				*profile.LargestFileBytes,
			)
		}
	}
	if len(profile.FileBytes) > 0 {
		total, err := sumBytes("file_bytes total", profile.FileBytes)
		if err != nil {
			return err
		}
		if profile.DatasetBytes != nil && total != *profile.DatasetBytes {
			return fmt.Errorf(
				"dataset_bytes %d contradicts file_bytes total %d",
				*profile.DatasetBytes,
				total,
			)
		}
		if profile.LargestFileBytes != nil && profile.FileBytes[0] != *profile.LargestFileBytes {
			return fmt.Errorf(
				"largest_file_bytes %d contradicts file_bytes[0] %d",
				*profile.LargestFileBytes,
				profile.FileBytes[0],
			)
		}
	}
	if len(profile.TopConcurrentFileBytes) > 0 && len(profile.FileBytes) > 0 {
		if len(profile.TopConcurrentFileBytes) > len(profile.FileBytes) {
			return fmt.Errorf("top_concurrent_file_bytes cannot contain more values than file_bytes")
		}
		for index, value := range profile.TopConcurrentFileBytes {
			if value != profile.FileBytes[index] {
				return fmt.Errorf(
					"top_concurrent_file_bytes[%d] contradicts file_bytes[%d]",
					index,
					index,
				)
			}
		}
	}
	return nil
}

func requiredPositive(value *uint64, name string) (uint64, error) {
	if value == nil {
		return 0, fmt.Errorf("%s evidence is required", name)
	}
	if *value == 0 {
		return 0, fmt.Errorf("%s must be greater than zero", name)
	}
	return *value, nil
}

func requiredPresent(value *uint64, name string) (uint64, error) {
	if value == nil {
		return 0, fmt.Errorf("%s evidence is required", name)
	}
	return *value, nil
}

func requiredConcurrency(value *int, name string) (int, error) {
	if value == nil {
		return 0, fmt.Errorf("%s evidence is required", name)
	}
	if *value <= 0 {
		return 0, fmt.Errorf("%s must be greater than zero", name)
	}
	return *value, nil
}
