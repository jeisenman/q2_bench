package formalmethod

import sitter "github.com/tree-sitter/go-tree-sitter"

func boundaryShadowed(node *sitter.Node, source []byte) bool {
	shadowed := false
	var bindings func(*sitter.Node)
	bindings = func(n *sitter.Node) {
		if n == nil {
			return
		}
		if n.Kind() == "identifier" && in(n.Utf8Text(source), "F", "StringType") {
			shadowed = true
		}
		for _, child := range children(n) {
			bindings(child)
		}
	}
	var walk func(*sitter.Node)
	walk = func(n *sitter.Node) {
		switch n.Kind() {
		case "assignment", "augmented_assignment", "for_statement", "for_in_clause":
			bindings(n.ChildByFieldName("left"))
		case "function_definition":
			bindings(n.ChildByFieldName("parameters"))
			bindings(n.ChildByFieldName("name"))
		case "import_statement", "import_from_statement":
			// Local imports change the binding from the module-level proof.
			bindings(n)
		}
		for _, child := range children(n) {
			walk(child)
		}
	}
	for ancestor := node.Parent(); ancestor != nil; ancestor = ancestor.Parent() {
		if ancestor.Kind() == "function_definition" {
			walk(ancestor)
		}
	}
	return shadowed
}
