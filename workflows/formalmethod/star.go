package formalmethod

func starProjection(e *Expression) bool {
	if e.Op == "column" {
		return e.Name == "*"
	}
	if e.Op == "col" && len(e.Args) == 1 {
		value, ok := expressionLiteral(e.Args[0])
		return ok && value == "*"
	}
	value, ok := expressionLiteral(e)
	return ok && value == "*"
}

func (v *evaluator) expandProjections(args []*Expression, t *tableData, env environment) ([]*Expression, error) {
	expanded := []*Expression{}
	for _, a := range args {
		items := []*Expression{a}
		if a.Kind == List {
			names, err := v.names(a, env)
			if err != nil {
				return nil, err
			}
			items = nil
			for _, name := range names {
				items = append(items, literal(name))
			}
		}
		for _, a := range items {
			if starProjection(a) {
				for _, name := range t.columns {
					expanded = append(expanded, &Expression{Op: "column", Kind: Column, Name: name})
				}
			} else {
				expanded = append(expanded, a)
			}
		}
	}
	return expanded, nil
}
