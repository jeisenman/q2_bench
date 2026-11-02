package formalmethod

import (
	"encoding/json"
	"fmt"
	"math"
	"strings"
)

type boundaryDomain struct {
	kind      string
	values    []any
	tentative bool
}

func expressionLiteral(e *Expression) (any, bool) {
	if e == nil {
		return nil, false
	}
	if in(e.Op, "lit", "neg") && len(e.Args) == 1 {
		v, ok := expressionLiteral(e.Args[0])
		if !ok || e.Op == "lit" {
			return v, ok
		}
		v, err := pythonScalar("neg", []any{v})
		return v, err == nil
	}
	if e.Op != "literal" {
		return nil, false
	}
	var v any
	err := json.Unmarshal(e.Value, &v)
	return v, err == nil
}

func columnName(e *Expression, receiver string) string {
	if e.Op == "column" && (e.Origin == "" || e.Origin == receiver) {
		return e.Name
	}
	if e.Op == "col" && len(e.Args) == 1 {
		value, ok := expressionLiteral(e.Args[0])
		if s, yes := value.(string); ok && yes {
			return s
		}
	}
	return ""
}

func filterBoundaryBindings(m Method, receiver string) ([]Bindings, map[string]string, error) {
	e := m.Steps[0].Expression
	if e.Op != "filter" || len(e.Args) != 2 {
		return nil, nil, fmt.Errorf("only complete filter predicates have automatic fixtures")
	}
	domains := map[string]*boundaryDomain{}
	links := [][2]string{}
	var inspect func(*Expression, string) error
	inspect = func(x *Expression, hint string) error {
		if in(x.Op, "contains", "startswith", "endswith", "like") {
			name, values, err := stringPredicateDomain(x, receiver)
			if err != nil {
				return err
			}
			if old := domains[name]; old != nil && old.kind != "string" && !old.tentative {
				return fmt.Errorf("conflicting string predicate field type")
			}
			if domains[name] == nil || domains[name].tentative {
				domains[name] = &boundaryDomain{kind: "string"}
			}
			domains[name].values = append(domains[name].values, values...)
			return nil
		}
		if name := columnName(x, receiver); name != "" {
			if hint == "" {
				return fmt.Errorf("column %s has no source-proven primitive test type", name)
			}
			if old := domains[name]; old != nil && old.kind != hint {
				if !old.tentative {
					return fmt.Errorf("column %s has conflicting test types", name)
				}
				domains[name] = nil
			}
			if domains[name] == nil {
				domains[name] = &boundaryDomain{kind: hint}
			}
			return nil
		}
		if in(x.Op, "isNull", "isNotNull", "isnull") {
			name := columnName(x.Args[0], receiver)
			if name == "" {
				return fmt.Errorf("null predicate needs a direct field")
			}
			if domains[name] == nil {
				// Nullness is type-independent within this primitive profile.
				domains[name] = &boundaryDomain{kind: "string", values: []any{"value", "", " "}, tentative: true}
			}
			return nil
		}
		if x.Op == "isin" {
			name := columnName(x.Args[0], receiver)
			if name == "" {
				return fmt.Errorf("membership predicate needs a direct field")
			}
			items := x.Args[1:]
			if len(items) == 1 && items[0].Op == "list" {
				items = items[0].Args
			}
			for _, item := range items {
				value, ok := expressionLiteral(item)
				if !ok {
					return fmt.Errorf("membership candidates require literal values")
				}
				if value == nil {
					continue
				}
				kind, values := domainAround(value)
				if kind == "" {
					return fmt.Errorf("unsupported membership literal")
				}
				if err := inspect(x.Args[0], kind); err != nil {
					return err
				}
				domains[name].values = append(domains[name].values, values...)
			}
			if domains[name] == nil {
				return fmt.Errorf("membership predicate has no typed literal")
			}
			return nil
		}
		if in(x.Op, "eq", "ne", "lt", "le", "gt", "ge") && len(x.Args) == 2 {
			left, right := columnName(x.Args[0], receiver), columnName(x.Args[1], receiver)
			if left != "" && right != "" {
				for _, name := range []string{left, right} {
					if domains[name] == nil {
						domains[name] = &boundaryDomain{kind: "double", values: []any{float64(-1), float64(0), float64(1)}, tentative: true}
					}
				}
				links = append(links, [2]string{left, right})
				return nil
			}
			for i := range 2 {
				value, ok := expressionLiteral(x.Args[1-i])
				name := columnName(x.Args[i], receiver)
				if name == "" {
					name = stringField(x.Args[i], receiver)
				}
				if !ok || value == nil || name == "" {
					continue
				}
				kind, values := domainAround(value)
				if kind == "" {
					return fmt.Errorf("unsupported boundary literal")
				}
				field := x.Args[i]
				if kind == "string" && stringField(field, receiver) != "" {
					field = &Expression{Op: "column", Kind: Column, Name: name, Origin: receiver}
				}
				if err := inspect(field, kind); err != nil {
					return err
				}
				domains[name].values = append(domains[name].values, values...)
				return nil
			}
			return fmt.Errorf("predicate boundary depends on derived columns or unbound context")
		}
		if in(x.Op, "and", "or", "not") {
			for _, a := range x.Args {
				if err := inspect(a, "boolean"); err != nil {
					return err
				}
			}
			return nil
		}
		return fmt.Errorf("predicate %s needs explicit typed fixtures", x.Op)
	}
	if err := inspect(e.Args[1], "boolean"); err != nil {
		return nil, nil, err
	}
	if err := propagateBoundaryDomains(domains, links); err != nil {
		return nil, nil, err
	}
	return boundaryDomainBindings(domains, receiver, true)
}

func domainAround(value any) (string, []any) {
	switch v := value.(type) {
	case float64:
		// Integers beyond exact float64 representation need another profile.
		if !math.IsInf(v, 0) && !math.IsNaN(v) && math.Abs(v) < 1<<52 {
			return "double", []any{v - 1, v, v + 1, math.Nextafter(v, math.Inf(-1)), math.Nextafter(v, math.Inf(1))}
		}
	case string:
		return "string", []any{v, "", " ", v + "__unmatched", strings.ToLower(v), strings.ToUpper(v)}
	case bool:
		return "boolean", []any{false, true}
	}
	return "", nil
}

func uniqueBoundaryValues(values []any) []any {
	result := []any{}
	seen := map[string]bool{}
	for _, value := range values {
		b, _ := json.Marshal(value)
		if !seen[string(b)] {
			seen[string(b)] = true
			result = append(result, value)
		}
	}
	return result
}
