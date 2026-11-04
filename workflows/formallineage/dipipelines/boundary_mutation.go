package dipipelines

import (
	"context"
	"encoding/json"
	"fmt"
	"sort"
)

func fixtureMutations(ctx context.Context, cases []ComparisonCase) []BoundaryMutation {
	if len(cases) == 0 {
		return nil
	}
	original := cases[0].Method
	encoded, _ := json.Marshal(original)
	mutations := []BoundaryMutation{}
	var inspect func(*Expression, []int)
	inspect = func(e *Expression, path []int) {
		replacements := map[string]string{"gt": "ge", "ge": "gt", "lt": "le", "le": "lt", "eq": "ne", "ne": "eq", "and": "or", "or": "and"}
		if replacement := replacements[e.Op]; replacement != "" {
			var mutant Method
			_ = json.Unmarshal(encoded, &mutant)
			target := mutant.Steps[0].Expression
			for _, index := range path {
				target = target.Args[index]
			}
			target.Op = replacement
			mutant.ID = methodID(mutant)
			mutations = append(mutations, mutationOutcome(ctx, cases, mutant, fmt.Sprintf("%v: %s -> %s", path, e.Op, replacement)))
		}
		for i, a := range e.Args {
			inspect(a, append(append([]int{}, path...), i))
		}
	}
	inspect(original.Steps[0].Expression, nil)
	if original.Steps[0].Expression.Op == "join" {
		var mutant Method
		_ = json.Unmarshal(encoded, &mutant)
		e := mutant.Steps[0].Expression
		how := e.Keywords["how"]
		if len(e.Args) > 3 {
			how = e.Args[3]
		}
		value, _ := expressionLiteral(how)
		other := "left"
		if value == "left" {
			other = "inner"
		}
		if len(e.Args) > 3 {
			e.Args[3] = literal(other)
		} else {
			if e.Keywords == nil {
				e.Keywords = map[string]*Expression{}
			}
			e.Keywords["how"] = literal(other)
		}
		mutant.ID = methodID(mutant)
		mutations = append(mutations, mutationOutcome(ctx, cases, mutant, "join mode -> "+other))
	}
	return mutations
}

func mutationOutcome(ctx context.Context, cases []ComparisonCase, mutant Method, description string) BoundaryMutation {
	result := BoundaryMutation{Change: description, Status: "survived"}
	for _, c := range cases {
		actual, err := EvaluateOutputs(ctx, c.Method, c.Bindings)
		if err != nil {
			result.Status = "blocked_original_error"
			return result
		}
		changed, err := EvaluateOutputs(ctx, mutant, c.Bindings)
		if err != nil {
			result.Status = "blocked_mutant_error"
			return result
		}
		if boundaryResultKey(actual) != boundaryResultKey(changed) {
			result.Status = "killed"
			return result
		}
	}
	return result
}

func boundaryResultKey(result Result) string {
	bags := map[string][]string{}
	for port, rows := range result.Tables {
		bag := []string{}
		for _, row := range rows {
			encoded, _ := json.Marshal(row)
			bag = append(bag, string(encoded))
		}
		sort.Strings(bag)
		bags[port] = bag
	}
	b, _ := json.Marshal(struct {
		Bags    map[string][]string
		Schemas map[string][]string
	}{bags, result.Schemas})
	return string(b)
}
