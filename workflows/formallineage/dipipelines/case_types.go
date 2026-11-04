package dipipelines

import "fmt"

type boundCaseValue struct {
	expression *Expression
	bindings   environment
}

func primitiveType(value any) string {
	switch value.(type) {
	case string:
		return "string"
	case float64:
		return "double"
	case bool:
		return "boolean"
	}
	return ""
}

func (v *evaluator) expressionType(e *Expression, env environment, t *tableData) (string, error) {
	if e.Kind == Scalar {
		x, err := v.eval(e, env, nil, nil)
		return primitiveType(x), err
	}
	if e.Op == "ref" {
		if d, ok := env[e.Name].(deferredColumn); ok {
			return v.expressionType(d.expression, d.bindings, t)
		}
	}
	if e.Op == "column" || e.Op == "col" {
		name := e.Name
		if e.Op == "col" {
			var err error
			name, err = v.name(e.Args[0], env)
			if err != nil {
				return "", err
			}
		}
		for _, row := range t.rows {
			if row[name] != nil {
				return primitiveType(row[name]), nil
			}
		}
		return "", nil
	}
	switch e.Op {
	case "lit", "alias":
		return v.expressionType(e.Args[0], env, t)
	case "to_date", "date_add":
		return "date", nil
	case "lower", "upper", "trim":
		return "string", nil
	case "eq", "ne", "gt", "ge", "lt", "le", "and", "or", "not", "like", "contains", "startswith", "endswith", "isNull", "isNotNull", "isnull", "isin":
		return "boolean", nil
	case "add", "sub", "mul", "div", "neg", "sum", "max", "min", "abs", "length", "datediff":
		return "double", nil
	case "cast":
		target, err := v.name(e.Args[1], env)
		if err != nil {
			return "", err
		}
		if target == "string" {
			return "string", nil
		}
		return "double", nil
	case "when", "when_next", "otherwise", "coalesce":
		branches, err := caseValues(e, env)
		if err != nil {
			return "", err
		}
		kind := ""
		for _, branch := range branches {
			k, err := v.expressionType(branch.expression, branch.bindings, t)
			if err != nil {
				return "", err
			}
			if kind != "" && k != "" && k != kind {
				return "", fmt.Errorf("CASE/coalesce implicit type coercion requires a separate semantic profile")
			}
			if k != "" {
				kind = k
			}
		}
		return kind, nil
	}
	return "", nil
}

func caseValues(e *Expression, env environment) ([]boundCaseValue, error) {
	if e.Op == "ref" {
		if d, ok := env[e.Name].(deferredColumn); ok {
			return caseValues(d.expression, d.bindings)
		}
	}
	switch e.Op {
	case "when":
		return []boundCaseValue{{e.Args[1], env}}, nil
	case "when_next":
		prior, err := unfinishedCaseValues(e.Args[0], env)
		return append(prior, boundCaseValue{e.Args[2], env}), err
	case "otherwise":
		prior, err := unfinishedCaseValues(e.Args[0], env)
		return append(prior, boundCaseValue{e.Args[1], env}), err
	case "coalesce":
		values := []boundCaseValue{}
		for _, a := range e.Args {
			values = append(values, boundCaseValue{a, env})
		}
		return values, nil
	}
	return nil, fmt.Errorf("unfinished CASE receiver required")
}

func unfinishedCaseValues(e *Expression, env environment) ([]boundCaseValue, error) {
	if e.Op == "ref" {
		if d, ok := env[e.Name].(deferredColumn); ok {
			return unfinishedCaseValues(d.expression, d.bindings)
		}
	}
	if !in(e.Op, "when", "when_next") {
		return nil, fmt.Errorf("unfinished CASE receiver required")
	}
	return caseValues(e, env)
}
