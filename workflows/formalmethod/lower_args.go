package formalmethod

import (
	"fmt"

	sitter "github.com/tree-sitter/go-tree-sitter"
)

func (c *compiler) scalarCollection(n *sitter.Node) (*Expression, error) {
	if !in(n.Kind(), "tuple", "set", "list") {
		return nil, fmt.Errorf("expected a literal collection")
	}
	e := &Expression{Op: "list", Kind: List}
	for _, child := range children(n) {
		x, err := c.lower(child)
		if err != nil {
			return nil, err
		}
		if x.Kind != Scalar {
			return nil, fmt.Errorf("collection contains a non-scalar value")
		}
		e.Args = append(e.Args, x)
	}
	return e, nil
}

func (c *compiler) lowerArgument(op string, n *sitter.Node) ([]*Expression, error) {
	if n.Kind() == "list_splat" {
		if !in(op, "drop", "select", "groupBy", "isin") {
			return nil, fmt.Errorf("expanded arguments unsupported for %s", op)
		}
		parts := children(n)
		if len(parts) != 1 {
			return nil, fmt.Errorf("invalid expanded argument")
		}
		collection := parts[0]
		if collection.Kind() == "identifier" && len(c.constants[collection.Utf8Text(c.source)]) == 1 {
			name := collection.Utf8Text(c.source)
			collection = c.constants[name][0]
			c.assumptions["module literal "+name+" is unmodified at invocation"] = true
		}
		if collection.Kind() == "set" && op != "isin" {
			return nil, fmt.Errorf("unordered argument expansion requires a separate profile")
		}
		x, err := c.scalarCollection(collection)
		if err != nil {
			return nil, err
		}
		return x.Args, nil
	}
	if op == "isin" {
		collection := n
		if n.Kind() == "identifier" && len(c.constants[n.Utf8Text(c.source)]) == 1 {
			candidate := c.constants[n.Utf8Text(c.source)][0]
			if in(candidate.Kind(), "set", "tuple") {
				collection = candidate
				c.assumptions["module literal "+n.Utf8Text(c.source)+" is unmodified at invocation"] = true
			}
		}
		if in(collection.Kind(), "set", "tuple") {
			x, err := c.scalarCollection(collection)
			if err != nil {
				return nil, err
			}
			return []*Expression{x}, nil
		}
	}
	x, err := c.lower(n)
	if err != nil {
		return nil, err
	}
	return []*Expression{x}, nil
}
