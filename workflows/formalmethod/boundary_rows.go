package formalmethod

import (
	"fmt"
	"sort"
	"strings"
)

func boundaryDomainBindings(domains map[string]*boundaryDomain, receiver string, cartesian bool) ([]Bindings, map[string]string, error) {
	if len(domains) == 0 || (cartesian && len(domains) > 8) || len(domains) > 100 {
		return nil, nil, fmt.Errorf("automatic fixtures need 1..8 interacting fields or at most 100 independent projection fields")
	}
	names := []string{}
	for name, d := range domains {
		if len(d.values) == 0 {
			switch d.kind {
			case "boolean":
				d.values = []any{true, false}
			case "double":
				d.values = []any{float64(-1), float64(0), float64(1), float64(0.5)}
			case "string":
				d.values = []any{"value", "", " ", "1.5", "0", "-1"}
			default:
				return nil, nil, fmt.Errorf("column %s lacks boundary candidates", name)
			}
		}
		d.values = uniqueBoundaryValues(append(d.values, nil))
		names = append(names, name)
	}
	sort.Strings(names)
	// Full cross products are required here, rather than silently claiming
	// independent-condition coverage from a truncated or random sample.
	product := 1
	for _, name := range names {
		if !cartesian {
			break
		}
		product *= len(domains[name].values)
		if product > 1024 {
			return nil, nil, fmt.Errorf("truth table exceeds 1024 rows; requires reviewed covering fixtures")
		}
	}
	rows := []Row{{}}
	ddl := []string{}
	for _, name := range names {
		if strings.Contains(name, "`") || strings.ContainsAny(name, "\n\r") {
			return nil, nil, fmt.Errorf("column needs an explicit Spark schema")
		}
		ddl = append(ddl, "`"+name+"` "+domains[name].kind)
		if !cartesian {
			continue
		}
		next := []Row{}
		for _, row := range rows {
			for _, v := range domains[name].values {
				r := Row{}
				for k, old := range row {
					r[k] = old
				}
				r[name] = v
				next = append(next, r)
			}
		}
		rows = next
	}
	if !cartesian {
		baseline := Row{}
		ddl = nil
		for _, name := range names {
			if !simpleColumnName(name) {
				return nil, nil, fmt.Errorf("projection needs simple field names")
			}
			baseline[name] = domains[name].values[0]
			ddl = append(ddl, "`"+name+"` "+domains[name].kind)
		}
		rows = []Row{baseline}
		for _, name := range names {
			for _, value := range domains[name].values[1:] {
				r := copyRow(baseline)
				r[name] = value
				rows = append(rows, r)
			}
		}
	}
	// Include a duplicate to check bag semantics as well as threshold truth.
	rows = append(rows, rows[0])
	full := Bindings{Tables: map[string][]Row{receiver: rows}}
	empty := Bindings{Tables: map[string][]Row{receiver: {}}, Schemas: map[string][]string{receiver: names}}
	return []Bindings{full, empty}, map[string]string{receiver: strings.Join(ddl, ", ")}, nil
}
