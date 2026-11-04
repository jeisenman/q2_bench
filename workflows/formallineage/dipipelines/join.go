package dipipelines

import (
	"fmt"
	"strings"
)

func (v *evaluator) join(left *tableData, e *Expression, env environment) (*tableData, error) {
	x, err := v.eval(e.Args[1], env, nil, nil)
	if err != nil {
		return nil, err
	}
	right, ok := x.(*tableData)
	if !ok {
		return nil, fmt.Errorf("join requires right relation")
	}
	on := e.Keywords["on"]
	if len(e.Args) > 2 {
		on = e.Args[2]
	}
	if on == nil {
		return nil, fmt.Errorf("join requires keys")
	}
	keys, err := v.names(on, env)
	if err != nil {
		return nil, err
	}
	if len(keys) == 0 {
		return nil, fmt.Errorf("join keys cannot be empty")
	}
	how := "inner"
	a := e.Keywords["how"]
	if len(e.Args) > 3 {
		a = e.Args[3]
	}
	if a != nil {
		how, err = v.name(a, env)
		if err != nil {
			return nil, err
		}
	}
	how = strings.ReplaceAll(strings.ToLower(how), "_", "")
	switch how {
	case "leftouter":
		how = "left"
	case "rightouter":
		how = "right"
	case "outer", "fullouter":
		how = "full"
	case "leftsemi":
		how = "semi"
	case "leftanti":
		how = "anti"
	}
	if !in(how, "inner", "left", "right", "full", "semi", "anti") {
		return nil, fmt.Errorf("unsupported join type %s", how)
	}
	if len(sortedUnique(keys)) != len(keys) {
		return nil, fmt.Errorf("join keys must be distinct")
	}
	for _, k := range keys {
		if !simpleColumnName(k) {
			return nil, fmt.Errorf("nested or quoted join keys require a separate semantic profile")
		}
		if !in(k, left.columns...) || !in(k, right.columns...) {
			return nil, fmt.Errorf("missing join key %s", k)
		}
	}
	out := &tableData{rows: []Row{}, columns: append([]string{}, left.columns...)}
	for _, k := range right.columns {
		if in(how, "semi", "anti") {
			break
		}
		if in(k, keys...) {
			continue
		}
		if in(k, left.columns...) {
			return nil, fmt.Errorf("ambiguous non-key join column %s", k)
		}
		out.columns = append(out.columns, k)
	}
	rightMatched := make([]bool, len(right.rows))
	for _, l := range left.rows {
		matched := false
		for rightIndex, r := range right.rows {
			*v.work++
			if *v.work > 2000000 {
				return nil, fmt.Errorf("join work limit exceeded")
			}
			if err := v.ctx.Err(); err != nil {
				return nil, err
			}
			equal := true
			for _, k := range keys {
				eq, err := scalar("eq", []any{l[k], r[k]})
				if err != nil {
					return nil, err
				}
				if eq != true {
					equal = false
					break
				}
			}
			if equal {
				matched = true
				rightMatched[rightIndex] = true
				if in(how, "semi", "anti") {
					break
				}
				n := copyRow(l)
				for _, k := range right.columns {
					if !in(k, keys...) {
						n[k] = r[k]
					}
				}
				out.rows = append(out.rows, n)
			}
			if len(out.rows) > maxRows {
				return nil, fmt.Errorf("join output exceeds row limit")
			}
		}
		if (matched && how == "semi") || (!matched && how == "anti") {
			out.rows = append(out.rows, copyRow(l))
		}
		if !matched && in(how, "left", "full") {
			n := copyRow(l)
			for _, k := range right.columns {
				if !in(k, keys...) {
					n[k] = nil
				}
			}
			out.rows = append(out.rows, n)
		}
		if len(out.rows) > maxRows {
			return nil, fmt.Errorf("join output exceeds row limit")
		}
	}
	if in(how, "right", "full") {
		for i, r := range right.rows {
			if rightMatched[i] {
				continue
			}
			n := Row{}
			for _, k := range left.columns {
				n[k] = nil
			}
			for _, k := range right.columns {
				n[k] = r[k]
			}
			out.rows = append(out.rows, n)
			if len(out.rows) > maxRows {
				return nil, fmt.Errorf("join output exceeds row limit")
			}
		}
	}
	return out, nil
}
