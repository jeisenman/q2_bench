package formalmethod

import (
	"fmt"
	"math"
)

type numericInterval struct {
	lower, upper             float64
	lowerClosed, upperClosed bool
}

func impossiblePredicate(e *Expression, receiver string) (string, string) {
	intervals := map[string]numericInterval{}
	var conjuncts func(*Expression) (string, string)
	conjuncts = func(x *Expression) (string, string) {
		if x.Op == "and" {
			for _, a := range x.Args {
				if field, reason := conjuncts(a); reason != "" {
					return field, reason
				}
			}
			return "", ""
		}
		if !in(x.Op, "gt", "ge", "lt", "le", "eq") || len(x.Args) != 2 {
			return "", ""
		}
		field := columnName(x.Args[0], receiver)
		value, ok := expressionLiteral(x.Args[1])
		op := x.Op
		if field == "" {
			field = columnName(x.Args[1], receiver)
			value, ok = expressionLiteral(x.Args[0])
			op = map[string]string{"gt": "lt", "ge": "le", "lt": "gt", "le": "ge", "eq": "eq"}[op]
		}
		v, number := value.(float64)
		if field == "" || !ok || !number || math.IsInf(v, 0) || math.IsNaN(v) {
			return "", ""
		}
		bounds, exists := intervals[field]
		if !exists {
			bounds = numericInterval{lower: math.Inf(-1), upper: math.Inf(1)}
		}
		if in(op, "gt", "ge", "eq") {
			closed := op != "gt"
			if v > bounds.lower {
				bounds.lower = v
				bounds.lowerClosed = closed
			} else if v == bounds.lower {
				bounds.lowerClosed = bounds.lowerClosed && closed
			}
		}
		if in(op, "lt", "le", "eq") {
			closed := op != "lt"
			if v < bounds.upper {
				bounds.upper = v
				bounds.upperClosed = closed
			} else if v == bounds.upper {
				bounds.upperClosed = bounds.upperClosed && closed
			}
		}
		intervals[field] = bounds
		if bounds.lower > bounds.upper || (bounds.lower == bounds.upper && (!bounds.lowerClosed || !bounds.upperClosed)) {
			lower, upper := ">", "<"
			if bounds.lowerClosed {
				lower = ">="
			}
			if bounds.upperClosed {
				upper = "<="
			}
			return field, fmt.Sprintf("%s %s %g AND %s %s %g has no finite numeric solution. Null comparisons yield UNKNOWN, so this predicate cannot be TRUE within the primitive numeric profile.", field, lower, bounds.lower, field, upper, bounds.upper)
		}
		return "", ""
	}
	return conjuncts(e)
}

func boundaryImpossibleFindings(cases []ComparisonCase) []BoundaryFinding {
	if len(cases) == 0 {
		return nil
	}
	m := cases[0].Method
	receiver := ""
	for _, p := range m.Parameters {
		if p.Kind == Table {
			receiver = p.Name
			break
		}
	}
	findings := []BoundaryFinding{}
	var walk func(*Expression, []int)
	walk = func(e *Expression, path []int) {
		var condition *Expression
		switch e.Op {
		case "when":
			condition = e.Args[0]
		case "when_next":
			condition = e.Args[1]
		case "filter":
			condition = e.Args[1]
		}
		if condition != nil {
			if field, reason := impossiblePredicate(condition, receiver); reason != "" {
				findings = append(findings, BoundaryFinding{Code: "contradictory_numeric_bounds", Field: field, Message: reason, OperatorPath: fmt.Sprint(path)})
			}
		}
		for i, a := range e.Args {
			walk(a, append(append([]int{}, path...), i))
		}
	}
	walk(m.Steps[0].Expression, nil)
	return findings
}
