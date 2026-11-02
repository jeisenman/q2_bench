package formalmethod

import (
	"fmt"
	"strings"
)

func literalNames(e *Expression) ([]string, error) {
	if e == nil {
		return nil, fmt.Errorf("explicit literal columns required")
	}
	if e.Op == "list" {
		result := []string{}
		for _, a := range e.Args {
			names, err := literalNames(a)
			if err != nil {
				return nil, err
			}
			result = append(result, names...)
		}
		return result, nil
	}
	if value, ok := expressionLiteral(e); ok {
		if name, ok := value.(string); ok && name != "" && !strings.ContainsAny(name, "`\r\n") {
			return []string{name}, nil
		}
	}
	return nil, fmt.Errorf("column declarations need literal string names")
}

func joinBoundaryBindings(m Method, params []string) ([]Bindings, map[string]string, error) {
	e := m.Steps[0].Expression
	on := e.Keywords["on"]
	if len(e.Args) > 2 {
		on = e.Args[2]
	}
	keys, err := literalNames(on)
	if err != nil || len(keys) == 0 || len(keys) > 8 {
		return nil, nil, fmt.Errorf("join fixtures require 1..8 literal key columns")
	}
	if len(sortedUnique(keys)) != len(keys) {
		return nil, nil, fmt.Errorf("join key list contains duplicates")
	}
	keyRow := func(value any) Row {
		r := Row{}
		for _, key := range keys {
			r[key] = value
		}
		return r
	}
	left := []Row{keyRow("match"), keyRow("match"), keyRow("left_only"), keyRow(nil)}
	right := []Row{keyRow("match"), keyRow("match"), keyRow("right_only"), keyRow(nil)}
	for i := range keys {
		r := keyRow("match")
		r[keys[i]] = "partial_mismatch"
		right = append(right, r)
		r = keyRow("match")
		r[keys[i]] = nil
		left = append(left, r)
		right = append(right, copyRow(r))
	}
	// Separate non-key fields expose LEFT null extension in the observed output.
	leftPayload, rightPayload := "__boundary_left", "__boundary_right"
	if in(leftPayload, keys...) || in(rightPayload, keys...) {
		return nil, nil, fmt.Errorf("reserved fixture column conflicts with join key")
	}
	for _, r := range left {
		r[leftPayload] = "L"
	}
	for _, r := range right {
		r[rightPayload] = "R"
	}
	leftCols := append(append([]string{}, keys...), leftPayload)
	rightCols := append(append([]string{}, keys...), rightPayload)
	schema := func(names []string) string {
		parts := []string{}
		for _, name := range names {
			parts = append(parts, "`"+name+"` string")
		}
		return strings.Join(parts, ", ")
	}
	schemas := map[string]string{params[0]: schema(leftCols), params[1]: schema(rightCols)}
	bindings := []Bindings{}
	for _, pair := range [][2][]Row{{left, right}, {left, {}}, {{}, right}, {{}, {}}} {
		bindings = append(bindings, Bindings{Tables: map[string][]Row{params[0]: pair[0], params[1]: pair[1]}, Schemas: map[string][]string{params[0]: leftCols, params[1]: rightCols}})
	}
	return bindings, schemas, nil
}

func dropnaBoundaryBindings(m Method, receiver string) ([]Bindings, map[string]string, error) {
	e := m.Steps[0].Expression
	keys := []string{"value", "other"}
	if subset := e.Keywords["subset"]; subset != nil {
		var err error
		keys, err = literalNames(subset)
		if err != nil {
			return nil, nil, err
		}
	}
	if len(keys) == 0 || len(keys) > 8 || len(sortedUnique(keys)) != len(keys) {
		return nil, nil, fmt.Errorf("dropna needs 1..8 distinct subset fields")
	}
	rows := []Row{}
	for mask := 0; mask < 1<<len(keys); mask++ {
		r := Row{}
		for i, key := range keys {
			r[key] = "present"
			if mask&(1<<i) != 0 {
				r[key] = nil
			}
		}
		rows = append(rows, r)
	}
	for _, value := range []string{"", " "} {
		r := Row{}
		for _, key := range keys {
			r[key] = value
		}
		rows = append(rows, r)
	}
	ddl := []string{}
	for _, key := range keys {
		ddl = append(ddl, "`"+key+"` string")
	}
	return []Bindings{{Tables: map[string][]Row{receiver: rows}}, {Tables: map[string][]Row{receiver: {}}, Schemas: map[string][]string{receiver: keys}}}, map[string]string{receiver: strings.Join(ddl, ", ")}, nil
}

func dropBoundaryBindings(m Method, receiver string) ([]Bindings, map[string]string, error) {
	e := m.Steps[0].Expression
	keys := []string{}
	for _, a := range e.Args[1:] {
		names, err := literalNames(a)
		if err != nil {
			return nil, nil, err
		}
		keys = append(keys, names...)
	}
	keys = sortedUnique(keys)
	keep := "__boundary_retained"
	if len(keys) == 0 || in(keep, keys...) {
		return nil, nil, fmt.Errorf("drop needs explicit columns without fixture name collisions")
	}
	all := append(append([]string{}, keys...), keep)
	r := Row{}
	ddl := []string{}
	for _, name := range all {
		r[name] = "present"
		ddl = append(ddl, "`"+name+"` string")
	}
	nulls := Row{}
	for _, name := range all {
		nulls[name] = nil
	}
	return []Bindings{{Tables: map[string][]Row{receiver: {r, r, nulls}}}, {Tables: map[string][]Row{receiver: {}}, Schemas: map[string][]string{receiver: all}}}, map[string]string{receiver: strings.Join(ddl, ", ")}, nil
}
