package formalmethod

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
)

type environment map[string]any
type deferredColumn struct {
	expression *Expression
	bindings   environment
}
type grouping struct {
	table *tableData
	keys  []string
}
type tableData struct {
	rows    []Row
	columns []string
}
type evaluator struct {
	ctx     context.Context
	work    *int
	active  *tableData
	depth   int
	library map[string]Method
}

// Evaluate interprets a compiled method over bounded input bags. It never runs
// Python, Spark, helper functions, network requests or application side effects.
func Evaluate(ctx context.Context, m Method, b Bindings) ([]Row, error) {
	work := 0
	if err := validateLibrary(m); err != nil {
		return nil, err
	}
	t, err := evaluate(ctx, m, b, &work, 0, m.Library)
	if err != nil {
		return nil, err
	}
	if len(t) != 1 || m.Steps[len(m.Steps)-1].Expression.Kind == Tuple {
		return nil, fmt.Errorf("multiple/tuple outputs require EvaluateOutputs")
	}
	out := make([]Row, len(t[0].rows))
	for i, row := range t[0].rows {
		out[i] = copyRow(row)
	}
	return out, nil
}

func evaluate(ctx context.Context, m Method, b Bindings, work *int, depth int, library map[string]Method) ([]*tableData, error) {
	if depth > 32 {
		return nil, fmt.Errorf("linked evaluation exceeds 32 frames")
	}
	if m.Format != Format || m.Profile != Profile || m.ID != methodID(m) || m.Status != "compiled" || len(m.Diagnostics) > 0 {
		return nil, fmt.Errorf("method must be compiled with valid digest and supported semantic profile")
	}
	if len(m.Steps) == 0 || len(m.Steps) > maxNodes || len(m.Parameters) > 100 {
		return nil, fmt.Errorf("invalid method size")
	}
	env := environment{}
	for _, p := range m.Parameters {
		if _, ok := env[p.Name]; ok {
			return nil, fmt.Errorf("duplicate parameter %s", p.Name)
		}
		switch p.Kind {
		case Table:
			rows, ok := b.Tables[p.Name]
			if !ok {
				return nil, fmt.Errorf("missing table %s", p.Name)
			}
			if len(rows) > maxRows {
				return nil, fmt.Errorf("input table exceeds %d rows", maxRows)
			}
			for _, r := range rows {
				if len(r) > 1000 {
					return nil, fmt.Errorf("row exceeds 1000 columns")
				}
				for _, v := range r {
					if err := scalarValue(v); err != nil {
						return nil, err
					}
				}
			}
			t, err := inputTable(rows, b.Schemas[p.Name])
			if err != nil {
				return nil, fmt.Errorf("table %s: %w", p.Name, err)
			}
			env[p.Name] = t
		case Scalar:
			v, ok := b.Scalars[p.Name]
			if !ok {
				return nil, fmt.Errorf("missing scalar %s", p.Name)
			}
			if err := scalarValue(v); err != nil {
				return nil, err
			}
			env[p.Name] = v
		default:
			return nil, fmt.Errorf("invalid parameter kind %s", p.Kind)
		}
	}
	for name := range b.Tables {
		if _, ok := env[name]; !ok {
			return nil, fmt.Errorf("unexpected table %s", name)
		}
		if _, ok := b.Scalars[name]; ok {
			return nil, fmt.Errorf("duplicate binding %s", name)
		}
	}
	for name := range b.Scalars {
		if _, ok := env[name]; !ok {
			return nil, fmt.Errorf("unexpected scalar %s", name)
		}
	}
	for name := range b.Schemas {
		if _, ok := b.Tables[name]; !ok {
			return nil, fmt.Errorf("schema supplied for unknown table %s", name)
		}
	}
	count := 0
	for i, s := range m.Steps {
		if err := validateTree(s.Expression, 0, &count); err != nil {
			return nil, err
		}
		if s.Return != (i == len(m.Steps)-1) || (!s.Return && s.Target == "" && len(s.Targets) == 0) || (!s.Return && s.Target != "" && len(s.Targets) > 0) {
			return nil, fmt.Errorf("method requires assignments followed by one final return")
		}
	}
	ev := evaluator{ctx: ctx, work: work, depth: depth, library: library}
	for _, s := range m.Steps {
		if s.Expression.Kind == Column && !s.Return {
			env[s.Target] = deferredColumn{s.Expression, capture(s.Expression, env)}
			continue
		}
		v, err := ev.eval(s.Expression, env, nil, nil)
		if err != nil {
			return nil, fmt.Errorf("%s line %d: %w", m.Function, s.Line, err)
		}
		if s.Return {
			if tuple, ok := v.([]any); ok {
				result := []*tableData{}
				for _, item := range tuple {
					table, ok := item.(*tableData)
					if !ok {
						return nil, fmt.Errorf("tuple output must contain relations")
					}
					result = append(result, table)
				}
				return result, nil
			}
			r, ok := v.(*tableData)
			if !ok {
				return nil, fmt.Errorf("return is not a relation")
			}
			return []*tableData{r}, nil
		}
		if len(s.Targets) > 0 {
			tuple, ok := v.([]any)
			if !ok || len(tuple) != len(s.Targets) {
				return nil, fmt.Errorf("tuple assignment arity mismatch")
			}
			for i, name := range s.Targets {
				env[name] = tuple[i]
			}
			continue
		}
		env[s.Target] = v
	}
	return nil, fmt.Errorf("missing return")
}

func scalarValue(v any) error {
	switch v := v.(type) {
	case nil, string, bool:
		return nil
	case float64:
		if !math.IsNaN(v) && !math.IsInf(v, 0) {
			return nil
		}
	}
	return fmt.Errorf("values must be null, string, boolean or finite float64")
}

func validateTree(e *Expression, depth int, count *int) error {
	*count++
	if e == nil || depth > 128 || *count > maxNodes {
		return fmt.Errorf("invalid expression or expression bounds exceeded")
	}
	if !in(string(e.Kind), string(Scalar), string(Column), string(Table), string(List), string(Grouped), string(Tuple)) {
		return fmt.Errorf("invalid expression kind")
	}
	for _, x := range e.Args {
		if err := validateTree(x, depth+1, count); err != nil {
			return err
		}
	}
	for _, x := range e.Keywords {
		if err := validateTree(x, depth+1, count); err != nil {
			return err
		}
	}
	n := len(e.Args)
	switch e.Op {
	case "invoke":
		if e.Name == "" || n > 100 || len(e.Keywords) != 0 || (e.Kind != Table && e.Kind != Tuple) {
			return fmt.Errorf("invalid invocation")
		}
	case "literal", "ref", "column":
		if n != 0 || len(e.Keywords) != 0 {
			return fmt.Errorf("invalid leaf")
		}
		if e.Op == "column" && !simpleColumnName(e.Name) {
			return fmt.Errorf("nested or quoted columns require a separate semantic profile")
		}
	case "list", "tuple":
		if len(e.Keywords) != 0 {
			return fmt.Errorf("invalid list")
		}
	case "add", "sub", "mul", "div", "and", "or", "eq", "ne", "lt", "le", "gt", "ge":
		if n != 2 || len(e.Keywords) != 0 {
			return fmt.Errorf("invalid binary operator")
		}
	case "not", "neg", "str":
		if n != 1 || len(e.Keywords) != 0 {
			return fmt.Errorf("invalid unary operator")
		}
	default:
		return checkCall(e)
	}
	return nil
}

func (v *evaluator) eval(e *Expression, env environment, row Row, group []Row) (any, error) {
	*v.work++
	if *v.work > 2000000 {
		return nil, fmt.Errorf("evaluation work limit exceeded")
	}
	if err := v.ctx.Err(); err != nil {
		return nil, err
	}
	if e.Op == "invoke" {
		return v.invoke(e, env)
	}
	if in(e.Op, "when", "when_next", "otherwise", "coalesce") {
		return v.caseExpression(e, env, row, group)
	}
	if e.Op == "table_columns" {
		x, err := v.eval(e.Args[0], env, nil, nil)
		if err != nil {
			return nil, err
		}
		t, ok := x.(*tableData)
		if !ok {
			return nil, fmt.Errorf("columns metadata requires a table")
		}
		names := []any{}
		for _, name := range t.columns {
			names = append(names, name)
		}
		return names, nil
	}
	if in(e.Op, "filter", "drop", "dropna", "withColumn", "withColumnRenamed", "select", "join", "groupBy", "agg") {
		return v.relation(e, env)
	}
	if e.Op == "literal" {
		var x any
		err := json.Unmarshal(e.Value, &x)
		if err != nil {
			return nil, err
		}
		return x, scalarValue(x)
	}
	if e.Op == "ref" {
		x, ok := env[e.Name]
		if !ok {
			return nil, fmt.Errorf("unbound reference %s", e.Name)
		}
		if deferred, ok := x.(deferredColumn); ok {
			return v.eval(deferred.expression, deferred.bindings, row, group)
		}
		return x, nil
	}
	if e.Op == "column" {
		if e.Origin != "" && env[e.Origin] != v.active {
			return nil, fmt.Errorf("column %s belongs to a different relation; qualified lineage is unresolved", e.Name)
		}
		x, ok := row[e.Name]
		if !ok {
			return nil, fmt.Errorf("missing column %s", e.Name)
		}
		return x, nil
	}
	if in(e.Op, "sum", "max", "min") {
		return v.aggregate(e, env, group)
	}
	if e.Op == "alias" {
		return v.eval(e.Args[0], env, row, group)
	}
	args := make([]any, len(e.Args))
	for i, a := range e.Args {
		x, err := v.eval(a, env, row, group)
		if err != nil {
			return nil, err
		}
		args[i] = x
	}
	if e.Op == "list" || e.Op == "tuple" {
		return args, nil
	}
	if e.Op == "col" {
		name, ok := args[0].(string)
		if !ok || !simpleColumnName(name) {
			return nil, fmt.Errorf("column name must be a simple string; nested or quoted resolution is unsupported")
		}
		x, ok := row[name]
		if !ok {
			return nil, fmt.Errorf("missing column %s", name)
		}
		return x, nil
	}
	if e.Op == "lit" {
		return args[0], nil
	}
	if e.Op == "to_date" && e.Keywords["format"] != nil {
		x, err := v.eval(e.Keywords["format"], env, row, group)
		if err != nil {
			return nil, err
		}
		args = append(args, x)
	}
	if e.Kind == Scalar && in(e.Op, "add", "sub", "mul", "div", "eq", "ne", "lt", "le", "gt", "ge", "neg") {
		return pythonScalar(e.Op, args)
	}
	return scalar(e.Op, args)
}

func capture(e *Expression, env environment) environment {
	out := environment{}
	var walk func(*Expression)
	walk = func(e *Expression) {
		if e.Op == "ref" {
			out[e.Name] = env[e.Name]
		}
		if e.Origin != "" {
			out[e.Origin] = env[e.Origin]
		}
		for _, a := range e.Args {
			walk(a)
		}
		for _, a := range e.Keywords {
			walk(a)
		}
	}
	walk(e)
	return out
}
