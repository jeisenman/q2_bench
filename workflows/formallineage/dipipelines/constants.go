package dipipelines

import (
	"fmt"

	sitter "github.com/tree-sitter/go-tree-sitter"
)

func moduleConstants(root *sitter.Node, source []byte) map[string][]*sitter.Node {
	result := map[string][]*sitter.Node{}
	for _, s := range children(root) {
		if s.Kind() != "expression_statement" || s.NamedChildCount() != 1 || s.NamedChild(0).Kind() != "assignment" {
			continue
		}
		a := s.NamedChild(0)
		left, right := a.ChildByFieldName("left"), a.ChildByFieldName("right")
		if left != nil && right != nil && left.Kind() == "identifier" {
			name := left.Utf8Text(source)
			result[name] = append(result[name], right)
		}
	}
	return result
}

func (c *compiler) constant(name string, n *sitter.Node) (*Expression, error) {
	// No function calls, names, attributes or comprehensions are evaluated while
	// reading module constants. In particular metadata constructors stay opaque.
	var allowed func(*sitter.Node) bool
	allowed = func(n *sitter.Node) bool {
		if !in(n.Kind(), "string", "string_start", "string_content", "string_end", "escape_sequence", "integer", "float", "true", "false", "none", "list", "unary_operator", "binary_operator", "parenthesized_expression") {
			return false
		}
		for _, x := range children(n) {
			if !allowed(x) {
				return false
			}
		}
		return true
	}
	if !allowed(n) {
		return nil, fmt.Errorf("global %s is not a supported literal constant", name)
	}
	isolated := compiler{source: c.source, names: map[string]Kind{}}
	x, err := isolated.lower(n)
	c.nodes += isolated.nodes
	if err != nil {
		return nil, err
	}
	c.assumptions["module literal "+name+" is unmodified at invocation"] = true
	return x, nil
}
