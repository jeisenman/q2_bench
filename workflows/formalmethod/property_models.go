package formalmethod

import "fmt"

const propertyGenerator = "q2-seeded-relations/v1"

// PropertyConfig bounds reproducible differential property instances.
// Samples are additional rows per table; exact boundary rows are retained.
type PropertyConfig struct {
	Seeds           []uint64 `json:"seeds"`
	SamplesPerTable int      `json:"samples_per_table"`
}

// PropertyGeneration records how to reproduce one generated input instance.
type PropertyGeneration struct {
	Generator       string `json:"generator"`
	Seed            uint64 `json:"seed"`
	SamplesPerTable int    `json:"samples_per_table"`
	BaseCaseID      string `json:"base_case_id"`
	Property        string `json:"property"`
}

func (c PropertyConfig) validate() error {
	if len(c.Seeds) < 1 || len(c.Seeds) > 16 || c.SamplesPerTable < 1 || c.SamplesPerTable > 256 {
		return fmt.Errorf("property generation requires 1..16 seeds and 1..256 additional sample rows per input table")
	}
	seen := map[uint64]bool{}
	for _, seed := range c.Seeds {
		if seen[seed] {
			return fmt.Errorf("property seed %d is duplicated", seed)
		}
		seen[seed] = true
	}
	return nil
}
