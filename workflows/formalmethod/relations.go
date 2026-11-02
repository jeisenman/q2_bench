package formalmethod

import (
	"fmt"
	"sort"
)

func inputTable(rows []Row, columns []string) (*tableData, error) {
	if len(columns) == 0 && len(rows) > 0 {
		for k := range rows[0] {
			columns = append(columns, k)
		}
		sort.Strings(columns)
	}
	if len(columns) == 0 {
		return nil, fmt.Errorf("empty tables require an explicit column schema")
	}
	seen := map[string]bool{}
	for _, k := range columns {
		if k == "" || seen[k] {
			return nil, fmt.Errorf("empty or duplicate column")
		}
		seen[k] = true
	}
	for _, r := range rows {
		if len(r) != len(columns) {
			return nil, fmt.Errorf("inconsistent row columns")
		}
		for _, k := range columns {
			if _, ok := r[k]; !ok {
				return nil, fmt.Errorf("missing column %s", k)
			}
		}
	}
	types := map[string]string{}
	for _, r := range rows {
		for k, value := range r {
			kind := primitiveType(value)
			if kind != "" {
				if prior := types[k]; prior != "" && prior != kind {
					return nil, fmt.Errorf("mixed primitive types in column %s", k)
				}
				types[k] = kind
			}
		}
	}
	return &tableData{rows, columns}, nil
}

func copyRow(r Row) Row {
	out := Row{}
	for k, v := range r {
		out[k] = v
	}
	return out
}

func (v *evaluator) names(e *Expression, env environment) ([]string, error) {
	if e.Op == "ref" {
		if deferred, ok := env[e.Name].(deferredColumn); ok {
			return v.names(deferred.expression, deferred.bindings)
		}
	}
	if e.Op == "column" {
		if e.Origin != "" && env[e.Origin] != v.active {
			return nil, fmt.Errorf("group key belongs to a different relation")
		}
		return []string{e.Name}, nil
	}
	if e.Op == "col" {
		return v.names(e.Args[0], env)
	}
	x, err := v.eval(e, env, nil, nil)
	if err != nil {
		return nil, err
	}
	if s, ok := x.(string); ok {
		return []string{s}, nil
	}
	list, ok := x.([]any)
	if !ok {
		return nil, fmt.Errorf("expected string or list of strings")
	}
	var out []string
	for _, a := range list {
		s, ok := a.(string)
		if !ok {
			return nil, fmt.Errorf("expected string column name")
		}
		out = append(out, s)
	}
	return out, nil
}

func (v *evaluator) name(e *Expression, env environment) (string, error) {
	xs, err := v.names(e, env)
	if err != nil {
		return "", err
	}
	if len(xs) != 1 {
		return "", fmt.Errorf("expected one name")
	}
	return xs[0], nil
}

func (v *evaluator) relation(e *Expression, env environment) (any, error) {
	base, err := v.eval(e.Args[0], env, nil, nil)
	if err != nil {
		return nil, err
	}
	if e.Op == "agg" {
		g, ok := base.(*grouping)
		if !ok {
			return nil, fmt.Errorf("agg requires grouped relation")
		}
		return v.aggregateTable(g, e.Args[1:], env)
	}
	t, ok := base.(*tableData)
	if !ok {
		return nil, fmt.Errorf("%s requires a relation", e.Op)
	}
	prior := v.active
	v.active = t
	defer func() { v.active = prior }()
	for _, a := range e.Args[1:] {
		if e.Op == "select" && starProjection(a) {
			if a.Op == "column" && a.Origin != "" && env[a.Origin] != t {
				return nil, fmt.Errorf("qualified star belongs to a different relation")
			}
			continue
		}
		if err := v.checkColumns(a, env, t); err != nil {
			return nil, err
		}
	}
	if e.Op == "join" {
		return v.join(t, e, env)
	}
	if e.Op == "groupBy" {
		var keys []string
		for _, a := range e.Args[1:] {
			xs, err := v.names(a, env)
			if err != nil {
				return nil, err
			}
			keys = append(keys, xs...)
		}
		if len(keys) == 0 {
			return nil, fmt.Errorf("groupBy needs keys")
		}
		seen := map[string]bool{}
		for _, k := range keys {
			if seen[k] {
				return nil, fmt.Errorf("duplicate group key %s", k)
			}
			seen[k] = true
		}
		for _, k := range keys {
			if !simpleColumnName(k) {
				return nil, fmt.Errorf("nested or quoted group keys require a separate semantic profile")
			}
			if !in(k, t.columns...) {
				return nil, fmt.Errorf("missing group key %s", k)
			}
		}
		return &grouping{t, keys}, nil
	}
	out := &tableData{rows: []Row{}, columns: append([]string{}, t.columns...)}
	switch e.Op {
	case "drop":
		return v.dropColumns(t, e, env)
	case "filter":
		for _, r := range t.rows {
			x, err := v.eval(e.Args[1], env, r, nil)
			if err != nil {
				return nil, err
			}
			if x != nil {
				b, ok := x.(bool)
				if !ok {
					return nil, fmt.Errorf("filter requires boolean")
				}
				if b {
					out.rows = append(out.rows, copyRow(r))
				}
			}
		}
	case "dropna":
		how := "any"
		if a := e.Keywords["how"]; a != nil {
			how, err = v.name(a, env)
			if err != nil {
				return nil, err
			}
		}
		if !in(how, "all", "any") {
			return nil, fmt.Errorf("dropna how must be any or all")
		}
		subset := t.columns
		if a := e.Keywords["subset"]; a != nil {
			subset, err = v.names(a, env)
			if err != nil {
				return nil, err
			}
		}
		for _, k := range subset {
			if !in(k, t.columns...) {
				return nil, fmt.Errorf("missing dropna column %s", k)
			}
		}
		for _, r := range t.rows {
			nulls := 0
			for _, k := range subset {
				if r[k] == nil {
					nulls++
				}
			}
			drop := nulls > 0
			if how == "all" {
				drop = nulls == len(subset)
			}
			if !drop {
				out.rows = append(out.rows, copyRow(r))
			}
		}
	case "withColumn", "withColumnRenamed":
		name, err := v.name(e.Args[1], env)
		if err != nil {
			return nil, err
		}
		if e.Op == "withColumn" {
			if !in(name, out.columns...) {
				out.columns = append(out.columns, name)
			}
			for _, r := range t.rows {
				x, err := v.eval(e.Args[2], env, r, nil)
				if err != nil {
					return nil, err
				}
				n := copyRow(r)
				n[name] = x
				out.rows = append(out.rows, n)
			}
		} else {
			to, err := v.name(e.Args[2], env)
			if err != nil {
				return nil, err
			}
			if !in(name, t.columns...) {
				return nil, fmt.Errorf("rename missing column %s", name)
			}
			if to != name && in(to, t.columns...) {
				return nil, fmt.Errorf("rename creates duplicate column %s", to)
			}
			for i, k := range out.columns {
				if k == name {
					out.columns[i] = to
				}
			}
			for _, r := range t.rows {
				n := copyRow(r)
				delete(n, name)
				n[to] = r[name]
				out.rows = append(out.rows, n)
			}
		}
	case "select":
		out.columns = nil
		exprs := []*Expression{}
		expanded, err := v.expandProjections(e.Args[1:], t, env)
		if err != nil {
			return nil, err
		}
		for _, a := range expanded {
			name, expr, err := v.projection(a, env)
			if err != nil {
				return nil, err
			}
			if err := v.checkColumns(expr, env, t); err != nil {
				return nil, err
			}
			if in(name, out.columns...) {
				return nil, fmt.Errorf("duplicate projected column %s", name)
			}
			out.columns = append(out.columns, name)
			exprs = append(exprs, expr)
		}
		for _, r := range t.rows {
			n := Row{}
			for i, a := range exprs {
				x, err := v.eval(a, env, r, nil)
				if err != nil {
					return nil, err
				}
				n[out.columns[i]] = x
			}
			out.rows = append(out.rows, n)
		}
	default:
		return nil, fmt.Errorf("unsupported relation operator %s", e.Op)
	}
	if len(out.columns) > 1000 {
		return nil, fmt.Errorf("output exceeds 1000 columns")
	}
	return out, nil
}

func (v *evaluator) checkColumns(e *Expression, env environment, t *tableData) error {
	if e.Kind == Scalar {
		_, err := v.eval(e, env, nil, nil)
		return err
	}
	if in(e.Op, "when", "when_next", "otherwise", "coalesce") {
		if _, err := v.expressionType(e, env, t); err != nil {
			return err
		}
	}
	if e.Op == "ref" {
		if deferred, ok := env[e.Name].(deferredColumn); ok {
			return v.checkColumns(deferred.expression, deferred.bindings, t)
		}
		return nil
	}
	name := ""
	if e.Op == "column" {
		name = e.Name
		if e.Origin != "" && env[e.Origin] != t {
			return fmt.Errorf("column %s belongs to a different relation", name)
		}
	}
	if e.Op == "col" {
		var err error
		name, err = v.name(e.Args[0], env)
		if err != nil {
			return err
		}
	}
	if name != "" && !simpleColumnName(name) {
		return fmt.Errorf("nested or quoted column %s requires a separate semantic profile", name)
	}
	if name != "" && !in(name, t.columns...) {
		return fmt.Errorf("missing column %s", name)
	}
	if name != "" {
		return nil
	}
	// Nested relation expressions have their own input schema and are checked
	// when evaluated; their column namespace is not this relation's namespace.
	if e.Kind == Table || e.Kind == Grouped {
		return nil
	}
	for _, a := range e.Args {
		if err := v.checkColumns(a, env, t); err != nil {
			return err
		}
	}
	return nil
}

func (v *evaluator) projection(e *Expression, env environment) (string, *Expression, error) {
	if e.Op == "col" {
		name, err := v.name(e.Args[0], env)
		return name, &Expression{Op: "column", Kind: Column, Name: name}, err
	}
	if e.Op == "alias" {
		name, err := v.name(e.Args[1], env)
		return name, e.Args[0], err
	}
	if e.Op == "column" {
		return e.Name, e, nil
	}
	if e.Kind == Scalar {
		name, err := v.name(e, env)
		return name, &Expression{Op: "column", Kind: Column, Name: name}, err
	}
	return "", nil, fmt.Errorf("projection requires named column or alias")
}
