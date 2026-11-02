package formalmethod

import (
	"context"
	"fmt"
)

func tupleWidth(e *Expression, library map[string]Method) int {
	if e.Op == "tuple" {
		return len(e.Args)
	}
	if e.Op == "invoke" {
		return len(library[e.Name].Outputs)
	}
	return 0
}

func outputPorts(e *Expression, library map[string]Method) []Parameter {
	if e.Op == "invoke" {
		return append([]Parameter{}, library[e.Name].Outputs...)
	}
	xs := []*Expression{e}
	if e.Kind == Tuple {
		xs = e.Args
	}
	ports := []Parameter{}
	seen := map[string]bool{}
	for i, x := range xs {
		name := fmt.Sprintf("output_%d", i+1)
		if x.Op == "ref" && !seen[x.Name] {
			name = x.Name
		}
		seen[name] = true
		ports = append(ports, Parameter{name, Table})
	}
	return ports
}

// EvaluateOutputs evaluates every returned table and retains empty-table schemas.
func EvaluateOutputs(ctx context.Context, m Method, b Bindings) (Result, error) {
	result := Result{Tables: map[string][]Row{}, Schemas: map[string][]string{}}
	if err := validateLibrary(m); err != nil {
		return result, err
	}
	work := 0
	tables, err := evaluate(ctx, m, b, &work, 0, m.Library)
	if err != nil {
		return result, err
	}
	ports := m.Outputs
	if len(ports) == 0 && len(tables) == 1 {
		ports = []Parameter{{"result", Table}}
	}
	if len(ports) != len(tables) {
		return result, fmt.Errorf("output port arity mismatch")
	}
	for i, p := range ports {
		if p.Kind != Table || p.Name == "" {
			return result, fmt.Errorf("invalid output port")
		}
		if _, ok := result.Tables[p.Name]; ok {
			return result, fmt.Errorf("duplicate output port")
		}
		rows := make([]Row, len(tables[i].rows))
		for j, r := range tables[i].rows {
			rows[j] = copyRow(r)
		}
		result.Tables[p.Name] = rows
		result.Schemas[p.Name] = append([]string{}, tables[i].columns...)
	}
	return result, nil
}
