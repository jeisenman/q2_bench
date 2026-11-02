package formalmethod

import "fmt"

func (v *evaluator) dropColumns(t *tableData, e *Expression, env environment) (*tableData, error) {
	drop := map[string]bool{}
	for _, a := range e.Args[1:] {
		// DataFrame.drop(Column) has different qualification/ambiguity rules.
		// This profile supports only literal column names, as Spark documents.
		if a.Kind != Scalar {
			return nil, fmt.Errorf("drop supports string column names only")
		}
		name, err := v.name(a, env)
		if err != nil {
			return nil, err
		}
		drop[name] = true
	}
	out := &tableData{rows: []Row{}, columns: []string{}}
	for _, name := range t.columns {
		if !drop[name] {
			out.columns = append(out.columns, name)
		}
	}
	for _, row := range t.rows {
		r := Row{}
		for _, name := range out.columns {
			r[name] = row[name]
		}
		out.rows = append(out.rows, r)
	}
	return out, nil
}
