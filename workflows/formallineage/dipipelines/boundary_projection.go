package dipipelines

import "fmt"

type projectionDomains struct {
	receiver string
	domains  map[string]*boundaryDomain
}

func projectionBoundaryBindings(m Method, receiver string) ([]Bindings, map[string]string, error) {
	e := m.Steps[0].Expression
	b := projectionDomains{receiver: receiver, domains: map[string]*boundaryDomain{}}
	independent := false
	switch e.Op {
	case "select":
		independent = true
		for _, a := range e.Args[1:] {
			if starProjection(a) || (a.Op == "table_columns" && len(a.Args) == 1 && a.Args[0].Op == "ref" && a.Args[0].Name == receiver) {
				if err := b.field("__boundary_key", "string", false, nil); err != nil {
					return nil, nil, err
				}
				if err := b.field("__boundary_amount", "double", false, nil); err != nil {
					return nil, nil, err
				}
				continue
			}
			if a.Kind == Scalar || a.Kind == List {
				names, err := literalNames(a)
				if err != nil {
					return nil, nil, err
				}
				for _, name := range names {
					if err := b.field(name, "string", true, nil); err != nil {
						return nil, nil, err
					}
				}
				continue
			}
			hint := ""
			if independentProjection(a) {
				hint = "string"
			}
			if _, err := b.expression(a, hint); err != nil {
				return nil, nil, err
			}
			if !independentProjection(a) {
				independent = false
			}
		}
	case "withColumn":
		if _, err := b.expression(e.Args[2], ""); err != nil {
			return nil, nil, err
		}
	case "withColumnRenamed":
		name, err := literalNames(e.Args[1])
		if err != nil || len(name) != 1 {
			return nil, nil, fmt.Errorf("rename requires a literal source name")
		}
		if err := b.field(name[0], "string", true, nil); err != nil {
			return nil, nil, err
		}
		independent = true
	default:
		return nil, nil, fmt.Errorf("projection operator %s needs a dedicated fixture oracle", e.Op)
	}
	if b.domains["__boundary_retained"] == nil {
		b.domains["__boundary_retained"] = &boundaryDomain{kind: "string", values: []any{"retained"}}
	}
	return boundaryDomainBindings(b.domains, receiver, !independent)
}

func (b *projectionDomains) field(name, hint string, tentative bool, values []any) error {
	if name == "" || !simpleColumnName(name) {
		return fmt.Errorf("projection needs direct primitive fields")
	}
	if hint == "" {
		hint = "double"
		tentative = true
	}
	if old := b.domains[name]; old != nil {
		if old.kind != hint {
			if old.tentative && !tentative {
				b.domains[name] = nil
			} else if tentative {
				return nil
			} else {
				return fmt.Errorf("projection field %s has conflicting primitive types", name)
			}
		} else {
			old.values = uniqueBoundaryValues(append(old.values, values...))
			old.tentative = old.tentative && tentative
			return nil
		}
	}
	b.domains[name] = &boundaryDomain{kind: hint, tentative: tentative, values: append([]any{}, values...)}
	return nil
}

func (b *projectionDomains) predicate(e *Expression) error {
	ghost := Method{Steps: []Step{{Expression: &Expression{Op: "filter", Kind: Table, Args: []*Expression{{Op: "ref", Kind: Table, Name: b.receiver}, e}}}}}
	bindings, _, err := filterBoundaryBindings(ghost, b.receiver)
	if err != nil {
		return err
	}
	values := map[string][]any{}
	for _, row := range bindings[0].Tables[b.receiver] {
		for name, value := range row {
			values[name] = append(values[name], value)
		}
	}
	for name, items := range values {
		kind := ""
		for _, value := range items {
			if k := primitiveType(value); k != "" {
				kind = k
				break
			}
		}
		if err := b.field(name, kind, fieldOnlyNull(e, name, b.receiver), uniqueBoundaryValues(items)); err != nil {
			return err
		}
	}
	return nil
}

func fieldOnlyNull(e *Expression, name, receiver string) bool {
	if in(e.Op, "isNull", "isNotNull", "isnull") {
		return true
	}
	if columnName(e, receiver) == name {
		return false
	}
	for _, a := range e.Args {
		if !fieldOnlyNull(a, name, receiver) {
			return false
		}
	}
	return true
}

func (b *projectionDomains) expression(e *Expression, hint string) (string, error) {
	if value, ok := expressionLiteral(e); ok {
		return primitiveType(value), nil
	}
	if name := columnName(e, b.receiver); name != "" {
		if err := b.field(name, hint, hint == "", nil); err != nil {
			return "", err
		}
		return b.domains[name].kind, nil
	}
	switch e.Op {
	case "lit", "alias":
		return b.expression(e.Args[0], hint)
	case "add", "sub", "mul", "div", "neg", "abs", "length":
		argHint := "double"
		if e.Op == "length" {
			argHint = "string"
		}
		for _, a := range e.Args {
			if _, err := b.expression(a, argHint); err != nil {
				return "", err
			}
		}
		return "double", nil
	case "lower", "upper", "trim":
		_, err := b.expression(e.Args[0], "string")
		return "string", err
	case "cast":
		value, ok := expressionLiteral(e.Args[1])
		target, yes := value.(string)
		if !ok || !yes {
			return "", fmt.Errorf("cast fixture requires a literal type")
		}
		if _, err := b.expression(e.Args[0], "string"); err != nil {
			return "", err
		}
		if target == "string" {
			return "string", nil
		}
		return "double", nil
	case "eq", "ne", "gt", "ge", "lt", "le", "and", "or", "not", "isNull", "isNotNull", "isnull", "isin", "like", "contains", "startswith", "endswith":
		return "boolean", b.predicate(e)
	case "when", "when_next", "otherwise", "coalesce":
		return b.caseExpression(e, hint)
	}
	return "", fmt.Errorf("projection expression %s needs explicit typed fixtures", e.Op)
}
