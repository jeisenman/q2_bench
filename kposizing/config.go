package kposizing

import "fmt"

const gibibyte = uint64(1024 * 1024 * 1024)

// Config defines all coefficients, tiers, defaults, and input safety bounds.
//
// Duplication, frame, serialization, concat, and Spark coefficients are
// multiplicative. Headroom is additive: 1/4 means 25 percent.
type Config struct {
	BaselineBytes          uint64   `json:"baseline_bytes"`
	SparkJVMBaselineBytes  uint64   `json:"spark_jvm_baseline_bytes"`
	APIMetadataBytes       uint64   `json:"api_metadata_bytes"`
	SDKDuplication         Ratio    `json:"sdk_duplication"`
	FrameCopies            Ratio    `json:"frame_copies"`
	SerializationFactor    Ratio    `json:"serialization_factor"`
	ConcatFactor           Ratio    `json:"concat_factor"`
	SparkCSVWorkingFactor  Ratio    `json:"spark_csv_working_factor"`
	Headroom               Ratio    `json:"headroom"`
	SupportedTiersBytes    []uint64 `json:"supported_tiers_bytes"`
	DefaultCopyConcurrency int      `json:"default_copy_concurrency"`
	MaxFileEvidence        int      `json:"max_file_evidence"`
	MaxConcurrency         int      `json:"max_concurrency"`
	MaxTasksPerExecutor    int      `json:"max_tasks_per_executor"`
	MaxSupportedTiers      int      `json:"max_supported_tiers"`
	MaxExpansionRatio      Ratio    `json:"max_expansion_ratio"`
}

// DefaultConfig returns visible, conservative planning assumptions.
//
// The baseline assumptions are 1 GiB for Python and 2 GiB for a Spark JVM.
// Data duplication, frame copies, serialization, and concat are each 2x;
// Spark CSV working memory is 3x per partition; headroom is 25 percent.
// Supported KPO tiers reflect the reviewed explicit 4, 6, 8, 16, 30, 40,
// and 56 GiB resource allocations.
func DefaultConfig() Config {
	return Config{
		BaselineBytes:         gibibyte,
		SparkJVMBaselineBytes: 2 * gibibyte,
		APIMetadataBytes:      64 * 1024 * 1024,
		SDKDuplication:        Ratio{Numerator: 2, Denominator: 1},
		FrameCopies:           Ratio{Numerator: 2, Denominator: 1},
		SerializationFactor:   Ratio{Numerator: 2, Denominator: 1},
		ConcatFactor:          Ratio{Numerator: 2, Denominator: 1},
		SparkCSVWorkingFactor: Ratio{Numerator: 3, Denominator: 1},
		Headroom:              Ratio{Numerator: 1, Denominator: 4},
		SupportedTiersBytes: []uint64{
			4 * gibibyte,
			6 * gibibyte,
			8 * gibibyte,
			16 * gibibyte,
			30 * gibibyte,
			40 * gibibyte,
			56 * gibibyte,
		},
		DefaultCopyConcurrency: 10,
		MaxFileEvidence:        10_000,
		MaxConcurrency:         1_000,
		MaxTasksPerExecutor:    1_024,
		MaxSupportedTiers:      64,
		MaxExpansionRatio:      Ratio{Numerator: 1_000, Denominator: 1},
	}
}

// Validate checks coefficients, tiers, defaults, and safety bounds.
func (c Config) Validate() error {
	if c.BaselineBytes == 0 {
		return fmt.Errorf("baseline_bytes must be greater than zero")
	}
	if c.SparkJVMBaselineBytes == 0 {
		return fmt.Errorf("spark_jvm_baseline_bytes must be greater than zero")
	}
	if c.APIMetadataBytes == 0 {
		return fmt.Errorf("api_metadata_bytes must be greater than zero")
	}
	for _, item := range []struct {
		name  string
		ratio Ratio
	}{
		{"sdk_duplication", c.SDKDuplication},
		{"frame_copies", c.FrameCopies},
		{"serialization_factor", c.SerializationFactor},
		{"concat_factor", c.ConcatFactor},
		{"spark_csv_working_factor", c.SparkCSVWorkingFactor},
		{"max_expansion_ratio", c.MaxExpansionRatio},
	} {
		if err := validatePositiveRatio(item.ratio, item.name); err != nil {
			return err
		}
	}
	if c.Headroom.Denominator == 0 {
		return fmt.Errorf("headroom.denominator must be greater than zero")
	}
	if c.DefaultCopyConcurrency <= 0 {
		return fmt.Errorf("default_copy_concurrency must be greater than zero")
	}
	if c.MaxFileEvidence <= 0 {
		return fmt.Errorf("max_file_evidence must be greater than zero")
	}
	if c.MaxConcurrency <= 0 {
		return fmt.Errorf("max_concurrency must be greater than zero")
	}
	if c.DefaultCopyConcurrency > c.MaxConcurrency {
		return fmt.Errorf(
			"default_copy_concurrency %d exceeds max_concurrency %d",
			c.DefaultCopyConcurrency,
			c.MaxConcurrency,
		)
	}
	if c.MaxTasksPerExecutor <= 0 {
		return fmt.Errorf("max_tasks_per_executor must be greater than zero")
	}
	if c.MaxSupportedTiers <= 0 {
		return fmt.Errorf("max_supported_tiers must be greater than zero")
	}
	if len(c.SupportedTiersBytes) == 0 {
		return fmt.Errorf("supported_tiers_bytes must not be empty")
	}
	if len(c.SupportedTiersBytes) > c.MaxSupportedTiers {
		return fmt.Errorf(
			"supported_tiers_bytes contains %d tiers; maximum is %d",
			len(c.SupportedTiersBytes),
			c.MaxSupportedTiers,
		)
	}
	var previous uint64
	for index, tier := range c.SupportedTiersBytes {
		if tier == 0 {
			return fmt.Errorf("supported_tiers_bytes[%d] must be greater than zero", index)
		}
		if index > 0 && tier <= previous {
			return fmt.Errorf("supported_tiers_bytes must be strictly increasing")
		}
		previous = tier
	}
	return nil
}

// Estimator applies one immutable validated configuration.
type Estimator struct {
	config Config
}

// NewEstimator validates and copies a configuration.
func NewEstimator(config Config) (*Estimator, error) {
	if err := config.Validate(); err != nil {
		return nil, fmt.Errorf("invalid sizing config: %w", err)
	}
	config.SupportedTiersBytes = append([]uint64(nil), config.SupportedTiersBytes...)
	return &Estimator{config: config}, nil
}

// Config returns a defensive copy of the estimator configuration.
func (e *Estimator) Config() Config {
	config := e.config
	config.SupportedTiersBytes = append([]uint64(nil), e.config.SupportedTiersBytes...)
	return config
}

func validatePositiveRatio(ratio Ratio, name string) error {
	if ratio.Numerator == 0 {
		return fmt.Errorf("%s.numerator must be greater than zero", name)
	}
	if ratio.Denominator == 0 {
		return fmt.Errorf("%s.denominator must be greater than zero", name)
	}
	return nil
}
