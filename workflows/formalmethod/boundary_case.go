package formalmethod

import "fmt"

func (b *projectionDomains) caseExpression(e *Expression, hint string) (string, error) {
	var conditions func(*Expression) error
	conditions = func(x *Expression) error {
		switch x.Op {
		case "when":
			return b.predicate(x.Args[0])
		case "when_next":
			if err := conditions(x.Args[0]); err != nil {
				return err
			}
			return b.predicate(x.Args[1])
		case "otherwise":
			return conditions(x.Args[0])
		}
		return nil
	}
	if err := conditions(e); err != nil {
		return "", err
	}
	values, err := caseValues(e, environment{})
	if err != nil {
		return "", err
	}
	kind := hint
	for _, v := range values {
		k := b.knownKind(v.expression)
		if k == "" {
			continue
		}
		if kind != "" && kind != k {
			return "", fmt.Errorf("CASE/coalesce fixture would require implicit primitive coercion")
		}
		kind = k
	}
	for _, v := range values {
		k, err := b.expression(v.expression, kind)
		if err != nil {
			return "", err
		}
		if kind == "" && k != "" {
			kind = k
		}
	}
	return kind, nil
}

func (b *projectionDomains) knownKind(e *Expression) string {
	if value, ok := expressionLiteral(e); ok {
		return primitiveType(value)
	}
	if name := columnName(e, b.receiver); name != "" {
		if d := b.domains[name]; d != nil && !d.tentative {
			return d.kind
		}
		return ""
	}
	switch e.Op {
	case "lit", "alias":
		return b.knownKind(e.Args[0])
	case "lower", "upper", "trim":
		return "string"
	case "add", "sub", "mul", "div", "neg", "abs", "length":
		return "double"
	case "eq", "ne", "gt", "ge", "lt", "le", "and", "or", "not", "isNull", "isNotNull", "isnull", "isin", "like", "contains", "startswith", "endswith":
		return "boolean"
	case "cast":
		value, _ := expressionLiteral(e.Args[1])
		if value == "string" {
			return "string"
		}
		return "double"
	}
	return ""
}

func independentProjection(e *Expression) bool {
	if e.Op == "alias" {
		return independentProjection(e.Args[0])
	}
	return in(e.Op, "column", "col", "literal", "lit")
}
