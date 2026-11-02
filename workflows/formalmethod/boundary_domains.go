package formalmethod

import "fmt"

func propagateBoundaryDomains(domains map[string]*boundaryDomain, links [][2]string) error {
	for range len(domains) {
		changed := false
		for _, link := range links {
			a, b := domains[link[0]], domains[link[1]]
			if a.kind != b.kind {
				if a.tentative && !b.tentative {
					a.kind = b.kind
					a.values = nil
					a.tentative = false
				} else if b.tentative && !a.tentative {
					b.kind = a.kind
					b.values = nil
					b.tentative = false
				} else {
					return fmt.Errorf("field comparison has conflicting primitive test types")
				}
			}
			union := uniqueBoundaryValues(append(append([]any{}, a.values...), b.values...))
			if len(a.values) != len(union) || len(b.values) != len(union) {
				changed = true
			}
			a.values = append([]any{}, union...)
			b.values = append([]any{}, union...)
		}
		if !changed {
			break
		}
	}
	return nil
}
