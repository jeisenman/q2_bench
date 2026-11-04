package dipipelines

import (
	"context"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math/rand/v2"
	"sort"
)

// GeneratePropertySuite adds seeded differential properties for every supported
// clause. It retains all exact boundary/empty cases and all unresolved jobs.
func GeneratePropertySuite(ctx context.Context, suite BoundarySuite, config PropertyConfig) (BoundarySuite, error) {
	if err := config.validate(); err != nil {
		return BoundarySuite{}, err
	}
	if suite.Format != "q2-boundary-suite/v1" || suite.ScenarioLimit != 10 || suite.PropertyConfig != nil || len(suite.Cases) == 0 || len(suite.Cases) > 50000 {
		return BoundarySuite{}, fmt.Errorf("provide a nonempty boundary suite without prior property generation")
	}
	b, err := json.Marshal(suite)
	if err != nil {
		return BoundarySuite{}, err
	}
	var result BoundarySuite
	if err := json.Unmarshal(b, &result); err != nil {
		return result, err
	}
	result.CaseBatches = nil
	config.Seeds = append([]uint64{}, config.Seeds...)
	result.PropertyConfig = &config
	byID := map[string]ComparisonCase{}
	for _, c := range result.Cases {
		if c.ID == "" || byID[c.ID].ID != "" || c.Generation != nil || c.Clause == nil {
			return BoundarySuite{}, fmt.Errorf("require unique source-bound boundary cases without generated instances")
		}
		byID[c.ID] = c
	}
	for i := range result.Clauses {
		if err := ctx.Err(); err != nil {
			return BoundarySuite{}, err
		}
		clause := &result.Clauses[i]
		base, err := largestPropertyBase(clause.CaseIDs, byID)
		if err != nil {
			return BoundarySuite{}, err
		}
		if base.ID == "" {
			continue // Unsupported/empty-only clauses stay explicit in the catalog.
		}
		for _, seed := range config.Seeds {
			generated, err := generatePropertyCase(base, seed, config.SamplesPerTable)
			if err != nil {
				return BoundarySuite{}, fmt.Errorf("clause %s: %w", clause.ID, err)
			}
			result.Cases = append(result.Cases, generated)
			clause.CaseIDs = append(clause.CaseIDs, generated.ID)
			if len(result.Cases) > 50000 {
				return BoundarySuite{}, fmt.Errorf("property suite exceeds 50000 cases; select fewer seeds explicitly")
			}
		}
	}
	clauses := map[string]BoundaryClause{}
	for _, clause := range result.Clauses {
		clauses[clause.ID] = clause
	}
	for i := range result.Jobs {
		for _, id := range result.Jobs[i].ClauseIDs {
			result.Jobs[i].Clauses = append(result.Jobs[i].Clauses, clauses[id])
		}
	}
	return result, nil
}

func largestPropertyBase(ids []string, cases map[string]ComparisonCase) (ComparisonCase, error) {
	var base ComparisonCase
	best := 0
	for _, id := range ids {
		c, ok := cases[id]
		if !ok {
			return base, fmt.Errorf("property clause references missing case %s", id)
		}
		if c.Generation != nil {
			continue
		}
		size := 0
		for _, rows := range c.Bindings.Tables {
			size += len(rows)
		}
		if size > best {
			base, best = c, size
		}
	}
	return base, nil
}

func generatePropertyCase(base ComparisonCase, seed uint64, samples int) (ComparisonCase, error) {
	b, err := json.Marshal(base)
	if err != nil {
		return ComparisonCase{}, err
	}
	var c ComparisonCase
	if err := json.Unmarshal(b, &c); err != nil {
		return c, err
	}
	c.ID = fmt.Sprintf("property:%s:seed:%d:rows:%d:v1", base.ID, seed, samples)
	c.Generation = &PropertyGeneration{Generator: propertyGenerator, Seed: seed, SamplesPerTable: samples, BaseCaseID: base.ID, Property: "go_spark_output_bag_and_columns_equivalence"}
	tables := make([]string, 0, len(c.Bindings.Tables))
	for name := range c.Bindings.Tables {
		tables = append(tables, name)
	}
	sort.Strings(tables)
	domains, err := propertyDomains(c)
	if err != nil {
		return c, err
	}
	for _, name := range tables {
		fields, err := propertyFields(c.SparkSchemas[name])
		if err != nil {
			return c, fmt.Errorf("table %s: %w", name, err)
		}
		rows := c.Bindings.Tables[name]
		if len(rows)+samples > maxRows {
			return c, fmt.Errorf("requested samples plus boundary rows exceed %d rows for table %s", maxRows, name)
		}
		// A table-local stream makes generation independent of map iteration and
		// unrelated clauses, while IDs/input digests make every failure replayable.
		digest, _ := hex.DecodeString(hash([]byte(fmt.Sprintf("%s:%s:%d:%s", propertyGenerator, base.ID, seed, name))))
		rng := rand.New(rand.NewPCG(binary.BigEndian.Uint64(digest[:8]), binary.BigEndian.Uint64(digest[8:16])))
		for range samples {
			row := Row{}
			if len(rows) > 0 && rng.IntN(8) == 0 {
				row = copyRow(rows[rng.IntN(len(rows))])
			} else {
				for _, field := range fields {
					value, err := sampledPropertyValue(rng, field, domains[field.key()])
					if err != nil {
						return c, err
					}
					row[field.name] = value
				}
			}
			rows = append(rows, row)
		}
		c.Bindings.Tables[name] = rows
	}
	return c, nil
}
