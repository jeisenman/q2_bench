package formalmethod

import (
	"context"
	"fmt"
	"sort"
)

// InterfaceCoverage retains every job-unit identity, including unresolved classes.
type InterfaceCoverage struct {
	EntryPoint string        `json:"entrypoint"`
	UnitIDs    []string      `json:"unit_ids"`
	Interface  *JobInterface `json:"interface,omitempty"`
	Error      string        `json:"error,omitempty"`
}

// InterfaceInventory separates invocation counts from distinct implementation classes.
type InterfaceInventory struct {
	Format          string              `json:"format"`
	Commit          string              `json:"commit"`
	UnitCount       int                 `json:"unit_count"`
	Classes         []InterfaceCoverage `json:"classes"`
	PredictionReady bool                `json:"prediction_ready"`
}

// DescribeInventory resolves each distinct class declared by the pinned unit
// inventory. Errors remain in coverage rather than removing jobs from the scope.
func DescribeInventory(ctx context.Context, root string, inventory Inventory) (InterfaceInventory, error) {
	result := InterfaceInventory{Format: "q2-formal-interfaces/v1", Commit: inventory.Commit, Classes: []InterfaceCoverage{}}
	if inventory.Format != "q2-formal-inventory/v1" || !commitRE.MatchString(inventory.Commit) {
		return result, fmt.Errorf("unsupported or unpinned source inventory")
	}
	entries := map[string][]string{}
	for _, f := range inventory.Files {
		for _, unit := range f.Units {
			if unit.Source.Commit != inventory.Commit {
				return result, fmt.Errorf("job-unit commit differs from inventory")
			}
			entries[unit.EntryPoint] = append(entries[unit.EntryPoint], unit.ID)
			result.UnitCount++
		}
	}
	names := []string{}
	for name := range entries {
		names = append(names, name)
	}
	sort.Strings(names)
	for _, name := range names {
		if err := ctx.Err(); err != nil {
			return result, err
		}
		ids := entries[name]
		sort.Strings(ids)
		coverage := InterfaceCoverage{EntryPoint: name, UnitIDs: ids}
		described, err := DescribeJob(ctx, root, inventory.Commit, name)
		if err != nil {
			coverage.Error = err.Error()
		} else {
			coverage.Interface = &described
		}
		result.Classes = append(result.Classes, coverage)
	}
	return result, nil
}
