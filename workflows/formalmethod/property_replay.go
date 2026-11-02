package formalmethod

import (
	"encoding/json"
	"fmt"
)

func validatePropertyReplay(suite BoundarySuite) error {
	byID := map[string]ComparisonCase{}
	for _, c := range suite.Cases {
		if c.ID == "" || byID[c.ID].ID != "" {
			return fmt.Errorf("property replay requires unique nonempty case IDs")
		}
		byID[c.ID] = c
		if suite.PropertyConfig == nil && c.Generation != nil {
			return fmt.Errorf("case %s has property metadata without a suite configuration", c.ID)
		}
	}
	if suite.PropertyConfig == nil {
		return nil
	}
	if err := suite.PropertyConfig.validate(); err != nil {
		return err
	}
	seeds := map[uint64]bool{}
	for _, seed := range suite.PropertyConfig.Seeds {
		seeds[seed] = true
	}
	expectedIDs := map[string]bool{}
	for _, clause := range suite.Clauses {
		base, err := largestPropertyBase(clause.CaseIDs, byID)
		if err != nil {
			return err
		}
		if base.ID == "" {
			continue
		}
		declared := map[string]bool{}
		for _, id := range clause.CaseIDs {
			declared[id] = true
		}
		for _, seed := range suite.PropertyConfig.Seeds {
			id := fmt.Sprintf("property:%s:seed:%d:rows:%d:v1", base.ID, seed, suite.PropertyConfig.SamplesPerTable)
			if c, ok := byID[id]; !ok || c.Generation == nil || !declared[id] {
				return fmt.Errorf("property suite is missing declared seed instance %s", id)
			}
			expectedIDs[id] = true
		}
	}
	for _, c := range suite.Cases {
		g := c.Generation
		if g == nil {
			continue
		}
		base, ok := byID[g.BaseCaseID]
		if !ok || !expectedIDs[c.ID] || base.Generation != nil || g.Generator != propertyGenerator || !seeds[g.Seed] || g.SamplesPerTable != suite.PropertyConfig.SamplesPerTable {
			return fmt.Errorf("case %s has unsupported or inconsistent property generation metadata", c.ID)
		}
		replayed, err := generatePropertyCase(base, g.Seed, g.SamplesPerTable)
		if err != nil {
			return err
		}
		actual, err := json.Marshal(c)
		if err != nil {
			return err
		}
		expected, err := json.Marshal(replayed)
		if err != nil {
			return err
		}
		if string(actual) != string(expected) {
			return fmt.Errorf("case %s does not match its recorded seed, inputs, schema, and generator", c.ID)
		}
	}
	return nil
}
