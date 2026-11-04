package dipipelines

import (
	"encoding/json"
	"fmt"
	"math"
)

func (v *evaluator) aggregate(e *Expression, env environment, rows []Row) (any, error) {
	var out any
	for _, r := range rows {
		x, err := v.eval(e.Args[0], env, r, nil)
		if err != nil {
			return nil, err
		}
		if x == nil {
			continue
		}
		if out == nil {
			out = x
			continue
		}
		if e.Op == "sum" {
			a, ok := out.(float64)
			if !ok {
				return nil, fmt.Errorf("sum requires numbers")
			}
			b, ok := x.(float64)
			if !ok {
				return nil, fmt.Errorf("sum requires numbers")
			}
			out = a + b
			if math.IsInf(out.(float64), 0) {
				return nil, fmt.Errorf("aggregate overflow")
			}
		} else {
			op := "gt"
			if e.Op == "min" {
				op = "lt"
			}
			gt, err := scalar(op, []any{x, out})
			if err != nil {
				return nil, err
			}
			if gt == true {
				out = x
			}
		}
	}
	if e.Op == "sum" && out != nil {
		if _, ok := out.(float64); !ok {
			return nil, fmt.Errorf("sum requires numbers")
		}
	}
	return out, nil
}

func (v *evaluator) aggregateTable(g *grouping, args []*Expression, env environment) (*tableData, error) {
	prior := v.active
	v.active = g.table
	defer func() { v.active = prior }()
	out := &tableData{rows: []Row{}, columns: append([]string{}, g.keys...)}
	var exprs []*Expression
	for _, a := range args {
		if err := v.checkColumns(a, env, g.table); err != nil {
			return nil, err
		}
		name, expr, err := v.projection(a, env)
		if err != nil {
			return nil, err
		}
		if in(name, out.columns...) {
			return nil, fmt.Errorf("duplicate aggregate column")
		}
		out.columns = append(out.columns, name)
		exprs = append(exprs, expr)
	}
	groups := map[string][]Row{}
	var order []string
	for _, r := range g.table.rows {
		values := []any{}
		for _, k := range g.keys {
			values = append(values, r[k])
		}
		b, err := json.Marshal(values)
		if err != nil {
			return nil, err
		}
		key := string(b)
		if _, ok := groups[key]; !ok {
			order = append(order, key)
		}
		groups[key] = append(groups[key], r)
	}
	for _, key := range order {
		rows := groups[key]
		n := Row{}
		for _, k := range g.keys {
			n[k] = rows[0][k]
		}
		for i, a := range exprs {
			x, err := v.eval(a, env, nil, rows)
			if err != nil {
				return nil, err
			}
			n[out.columns[len(g.keys)+i]] = x
		}
		out.rows = append(out.rows, n)
	}
	return out, nil
}
