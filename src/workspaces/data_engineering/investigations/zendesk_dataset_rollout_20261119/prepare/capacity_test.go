package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestCapacitySourceAndApprovedBudget(t *testing.T) {
	catalog := []byte(`{"models":[{"slug":"gpt-6-luna","context_window":272000,"supported_in_api":true}]}`)
	path := filepath.Join(t.TempDir(), "catalog.json")
	if err := os.WriteFile(path, catalog, 0600); err != nil {
		t.Fatal(err)
	}
	c := capacityRecord{Model: "gpt-6-luna", Source: "local Codex model capability catalog", CatalogPath: path, CatalogSHA: digest(catalog), FetchedAt: "2026-11-19T20:05:07.910647Z", ContextWindow: 272000, Supported: true, MaximumBytes: maximumInputBytes, MaximumTokens: maximumEstimatedTokens, HarnessReserve: 32000, OutputReserve: 16000, Margin: 96000, EstimateContract: "ceil UTF-8 bytes / 3"}
	encode := func(c capacityRecord) []byte {
		b, err := json.Marshal(c)
		if err != nil {
			t.Fatal(err)
		}
		return b
	}
	if _, err := loadCapacity(encode(c)); err != nil {
		t.Fatal(err)
	}
	refreshed := []byte(`{"fetched_at":"2026-11-19T20:08:28Z","models":[{"slug":"unrelated-model","context_window":1,"supported_in_api":false},{"slug":"gpt-6-luna","context_window":272000,"supported_in_api":true}]}`)
	if err := os.WriteFile(path, refreshed, 0600); err != nil {
		t.Fatal(err)
	}
	observed, err := loadCapacity(encode(c))
	if err != nil || !observed.Observation.CacheDrift || !observed.Observation.ExactFactsEqual || observed.Observation.CurrentCatalogSHA != digest(refreshed) || observed.Observation.FactSHA == "" {
		t.Fatalf("unrelated cache refresh rejected or not recorded: %+v %v", observed.Observation, err)
	}
	changed := []byte(`{"models":[{"slug":"gpt-6-luna","context_window":271999,"supported_in_api":true}]}`)
	if err := os.WriteFile(path, changed, 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := loadCapacity(encode(c)); err == nil {
		t.Fatal("changed relevant capability accepted")
	}
	if err := os.WriteFile(path, catalog, 0600); err != nil {
		t.Fatal(err)
	}
	wrong := c
	wrong.MaximumTokens++
	if _, err := loadCapacity(encode(wrong)); err == nil {
		t.Fatal("unapproved input budget accepted")
	}
	wrong = c
	wrong.Margin--
	if _, err := loadCapacity(encode(wrong)); err == nil {
		t.Fatal("incorrect reserve arithmetic accepted")
	}
	wrong = c
	wrong.CatalogSHA = "wrong"
	if _, err := loadCapacity(encode(wrong)); err == nil {
		t.Fatal("changed capacity source accepted")
	}
	if err := os.WriteFile(path, []byte(`{"models":[]}`), 0600); err != nil {
		t.Fatal(err)
	}
	c.CatalogSHA = digest([]byte(`{"models":[]}`))
	if _, err := loadCapacity(encode(c)); err == nil {
		t.Fatal("missing model capability accepted")
	}
}
