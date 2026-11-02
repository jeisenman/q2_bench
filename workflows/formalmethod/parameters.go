package formalmethod

import sitter "github.com/tree-sitter/go-tree-sitter"

// Parameter annotations constrain callers, not the body calculation. Inputs
// still receive explicit formal boundary kinds; annotation code is never run.
func parameterName(n *sitter.Node) *sitter.Node {
	if n.Kind() == "identifier" {
		return n
	}
	if n.Kind() == "typed_parameter" {
		for _, x := range children(n) {
			if x.Kind() == "identifier" {
				return x
			}
		}
	}
	return nil
}
