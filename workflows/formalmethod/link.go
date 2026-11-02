package formalmethod

import (
	"fmt"

	sitter "github.com/tree-sitter/go-tree-sitter"
)

func (c *compiler) link(name string, args []*sitter.Node) (*Expression, error) {
	if len(c.constants[name]) > 0 {
		return nil, fmt.Errorf("helper %s is reassigned at module scope", name)
	}
	if len(c.chain) >= 32 || in(name, c.chain...) {
		return nil, fmt.Errorf("recursive or excessive helper closure at %s", name)
	}
	defs := c.definitions[name]
	if len(defs) != 1 {
		return nil, fmt.Errorf("ambiguous helper %s", name)
	}
	params := children(defs[0].ChildByFieldName("parameters"))
	if len(args) != len(params) {
		return nil, fmt.Errorf("helper %s requires exact positional arity", name)
	}
	exprs := []*Expression{}
	tables := []string{}
	for i, a := range args {
		param := parameterName(params[i])
		if a.Kind() == "keyword_argument" || param == nil {
			return nil, fmt.Errorf("helper %s defaults/keywords require explicit binding", name)
		}
		x, err := c.lower(a)
		if err != nil {
			return nil, err
		}
		if x.Kind != Table && x.Kind != Scalar {
			return nil, fmt.Errorf("helper %s parameter %s needs richer value semantics", name, param.Utf8Text(c.source))
		}
		exprs = append(exprs, x)
		if x.Kind == Table {
			tables = append(tables, param.Utf8Text(c.source))
		}
	}
	method := compileLinked(c.source, c.receipt, name, defs[0], tables, c.chain)
	if method.Status != "compiled" {
		return nil, fmt.Errorf("helper %s is unresolved: %+v", name, method.Diagnostics)
	}
	for id, dependency := range method.Library {
		c.library[id] = dependency
	}
	method.Library = nil
	c.library[method.ID] = method
	if len(c.library) > 1000 {
		return nil, fmt.Errorf("helper closure exceeds 1000 methods")
	}
	kind := method.Steps[len(method.Steps)-1].Expression.Kind
	return &Expression{Op: "invoke", Kind: kind, Name: method.ID, Args: exprs}, nil
}

func validateLibrary(m Method) error {
	if len(m.Library) > 1000 {
		return fmt.Errorf("method library exceeds 1000 entries")
	}
	for id, child := range m.Library {
		if id != child.ID || child.ID != methodID(child) || len(child.Library) != 0 || child.Status != "compiled" || child.Format != Format || child.Profile != Profile {
			return fmt.Errorf("invalid linked method %s", id)
		}
	}
	return nil
}

func (v *evaluator) invoke(e *Expression, env environment) (any, error) {
	child, ok := v.library[e.Name]
	if !ok {
		return nil, fmt.Errorf("unbound formal method %s", e.Name)
	}
	if len(e.Args) != len(child.Parameters) {
		return nil, fmt.Errorf("linked method arity mismatch")
	}
	b := Bindings{Tables: map[string][]Row{}, Scalars: map[string]any{}, Schemas: map[string][]string{}}
	for i, p := range child.Parameters {
		x, err := v.eval(e.Args[i], env, nil, nil)
		if err != nil {
			return nil, err
		}
		if p.Kind == Table {
			t, ok := x.(*tableData)
			if !ok {
				return nil, fmt.Errorf("linked method requires table %s", p.Name)
			}
			b.Tables[p.Name] = t.rows
			b.Schemas[p.Name] = t.columns
		} else {
			if err := scalarValue(x); err != nil {
				return nil, err
			}
			b.Scalars[p.Name] = x
		}
	}
	result, err := evaluate(v.ctx, child, b, v.work, v.depth+1, v.library)
	if err != nil {
		return nil, err
	}
	if e.Kind == Table && len(result) == 1 {
		return result[0], nil
	}
	out := make([]any, len(result))
	for i, t := range result {
		out[i] = t
	}
	return out, nil
}
