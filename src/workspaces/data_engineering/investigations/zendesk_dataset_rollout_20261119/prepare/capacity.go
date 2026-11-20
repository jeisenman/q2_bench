package main

import (
	"encoding/hex"
	"encoding/json"
	"fmt"
	"time"
)

const maximumInputBytes = 524288
const maximumEstimatedTokens = 128000
const expectedCapacityRecord = "6bc44bf809b3a4e4d5808b89bb89c8ac8d5cf50f5ba6d9c5bf29228580e7052c"

type capabilityFacts struct {
	Slug      string `json:"slug"`
	Context   int    `json:"context_window"`
	Supported bool   `json:"supported_in_api"`
}
type capacityObservation struct {
	OriginalCatalogSHA string          `json:"original_catalog_sha256"`
	OriginalFetchedAt  string          `json:"original_fetched_at"`
	CurrentCatalogSHA  string          `json:"current_catalog_sha256"`
	CurrentFetchedAt   string          `json:"current_fetched_at"`
	CacheDrift         bool            `json:"catalog_cache_drift"`
	ExactFactsEqual    bool            `json:"exact_capability_facts_equal"`
	Facts              capabilityFacts `json:"capability_facts"`
	FactSHA            string          `json:"capability_facts_sha256"`
	FactHashContract   string          `json:"fact_hash_contract"`
}

type capacityRecord struct {
	Model            string              `json:"model"`
	Source           string              `json:"source"`
	CatalogPath      string              `json:"catalog_path"`
	CatalogSHA       string              `json:"catalog_sha256"`
	FetchedAt        string              `json:"fetched_at"`
	ContextWindow    int                 `json:"advertised_context_window"`
	Supported        bool                `json:"supported_in_api"`
	MaximumBytes     int                 `json:"maximum_input_bytes"`
	MaximumTokens    int                 `json:"maximum_estimated_input_tokens"`
	HarnessReserve   int                 `json:"estimated_harness_and_policy_reserve_tokens"`
	OutputReserve    int                 `json:"output_reserve_tokens"`
	Margin           int                 `json:"capacity_margin_tokens"`
	EstimateContract string              `json:"estimate_contract"`
	Observation      capacityObservation `json:"-"`
}

func loadCapacity(b []byte) (capacityRecord, error) {
	var c capacityRecord
	if err := decode(b, &c); err != nil {
		return c, err
	}
	if c.Model != "gpt-6-luna" || c.ContextWindow != 272000 || !c.Supported || c.MaximumBytes != maximumInputBytes || c.MaximumTokens != maximumEstimatedTokens || c.HarnessReserve != 32000 || c.OutputReserve != 16000 || c.Margin != 96000 || c.MaximumTokens+c.HarnessReserve+c.OutputReserve+c.Margin != c.ContextWindow {
		return c, fmt.Errorf("model capacity or selected operational budget differs from approved gpt-6-luna plan")
	}
	if c.CatalogPath == "" || c.CatalogSHA == "" || c.Source != "local Codex model capability catalog" || c.EstimateContract == "" {
		return c, fmt.Errorf("model capacity record lacks source provenance")
	}
	if decoded, err := hex.DecodeString(c.CatalogSHA); err != nil || len(decoded) != 32 {
		return c, fmt.Errorf("model capacity catalog provenance digest is invalid")
	}
	if _, err := time.Parse(time.RFC3339Nano, c.FetchedAt); err != nil {
		return c, fmt.Errorf("invalid model capacity fetched_at: %w", err)
	}
	catalog, err := read(c.CatalogPath)
	if err != nil {
		return c, err
	}
	var metadata struct {
		FetchedAt string            `json:"fetched_at"`
		Models    []capabilityFacts `json:"models"`
	}
	if err := decode(catalog, &metadata); err != nil {
		return c, err
	}
	matches := 0
	for _, m := range metadata.Models {
		if m.Slug == c.Model {
			matches++
			if m.Context != c.ContextWindow || m.Supported != c.Supported {
				return c, fmt.Errorf("model catalog capability differs from capacity record")
			}
		}
	}
	if matches != 1 {
		return c, fmt.Errorf("model catalog must contain exactly one gpt-6-luna capability")
	}
	facts := capabilityFacts{Slug: c.Model, Context: c.ContextWindow, Supported: c.Supported}
	factBytes, err := json.Marshal(facts)
	if err != nil {
		return c, err
	}
	c.Observation = capacityObservation{OriginalCatalogSHA: c.CatalogSHA, OriginalFetchedAt: c.FetchedAt, CurrentCatalogSHA: digest(catalog), CurrentFetchedAt: metadata.FetchedAt, CacheDrift: digest(catalog) != c.CatalogSHA || metadata.FetchedAt != c.FetchedAt, ExactFactsEqual: true, Facts: facts, FactSHA: digest(factBytes), FactHashContract: "compact JSON in field order slug,context_window,supported_in_api"}
	return c, nil
}
