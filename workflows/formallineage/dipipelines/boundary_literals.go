package dipipelines

import (
	"sort"
	"strings"

	sitter "github.com/tree-sitter/go-tree-sitter"
)

func clauseNode(root *sitter.Node, start, end uint) *sitter.Node {
	if root.StartByte() == start && root.EndByte() == end && root.Kind() == "call" {
		return root
	}
	if root.StartByte() > start || root.EndByte() < end {
		return nil
	}
	for _, c := range children(root) {
		if found := clauseNode(c, start, end); found != nil {
			return found
		}
	}
	return nil
}

func clauseLiteralBindings(m *parsedModule, node *sitter.Node, params []string) []ClauseLiteral {
	used := map[string]bool{}
	var names func(*sitter.Node)
	names = func(n *sitter.Node) {
		if n.Kind() == "identifier" {
			name := n.Utf8Text(m.content)
			if !in(name, append(params, "F", "StringType", "str")...) {
				used[name] = true
			}
			return
		}
		if n.Kind() == "attribute" {
			names(n.ChildByFieldName("object"))
			return
		}
		if n.Kind() == "keyword_argument" {
			names(n.ChildByFieldName("value"))
			return
		}
		for _, c := range children(n) {
			names(c)
		}
	}
	names(node)
	var function *sitter.Node
	for p := node.Parent(); p != nil; p = p.Parent() {
		if p.Kind() == "function_definition" {
			function = p
			break
		}
	}
	bindings := []ClauseLiteral{}
	for name := range used {
		value := literalBinding(m, function, node, name)
		if value == nil || !clauseLiteralValue(value) {
			continue
		}
		c := compiler{source: m.content, names: map[string]Kind{}, assumptions: map[string]bool{}}
		if in(value.Kind(), "tuple", "set") {
			if _, err := c.scalarCollection(value); err != nil {
				continue
			}
		} else if _, err := c.constant(name, value); err != nil {
			continue
		}
		bindings = append(bindings, ClauseLiteral{Name: name, StartByte: value.StartByte(), EndByte: value.EndByte()})
	}
	sort.Slice(bindings, func(i, j int) bool { return bindings[i].Name < bindings[j].Name })
	return bindings
}

func literalBinding(m *parsedModule, function, clause *sitter.Node, name string) *sitter.Node {
	var value *sitter.Node
	writes, mutated := 0, false
	if function != nil {
		for _, p := range children(function.ChildByFieldName("parameters")) {
			if n := parameterName(p); n != nil && n.Utf8Text(m.content) == name {
				return nil
			}
		}
		var walk func(*sitter.Node)
		walk = func(n *sitter.Node) {
			if n.Kind() == "function_definition" && n.Id() != function.Id() {
				if n.ChildByFieldName("name").Utf8Text(m.content) == name {
					writes++
				}
				return
			}
			if n.Kind() == "class_definition" {
				if n.ChildByFieldName("name").Utf8Text(m.content) == name {
					writes++
				}
				return
			}
			if in(n.Kind(), "assignment", "augmented_assignment", "for_statement", "for_in_clause") {
				left := n.ChildByFieldName("left")
				if left != nil && hasIdentifier(left, m.content, name) {
					writes++
					if left.Kind() == "identifier" && n.Kind() == "assignment" && n.EndByte() < clause.StartByte() && n.Parent() != nil && n.Parent().Kind() == "expression_statement" && n.Parent().Parent() != nil && n.Parent().Parent().Id() == function.ChildByFieldName("body").Id() {
						value = n.ChildByFieldName("right")
					}
				}
				right := n.ChildByFieldName("right")
				if n.Kind() == "assignment" && n.StartByte() < clause.StartByte() && right != nil && in(right.Kind(), "identifier", "list", "tuple", "dictionary", "set") && hasIdentifier(right, m.content, name) {
					mutated = true
				}
			}
			if in(n.Kind(), "global_statement", "nonlocal_statement", "delete_statement", "import_statement", "import_from_statement", "with_item", "except_clause") && hasIdentifier(n, m.content, name) {
				writes++
			}
			if n.Kind() == "call" && n.StartByte() < clause.StartByte() {
				f := n.ChildByFieldName("function")
				if f.Kind() == "attribute" && f.ChildByFieldName("object").Utf8Text(m.content) == name {
					mutated = true
				}
				if hasIdentifier(n.ChildByFieldName("arguments"), m.content, name) {
					operation := ""
					if f.Kind() == "attribute" {
						operation = f.ChildByFieldName("attribute").Utf8Text(m.content)
					}
					if !in(operation, "groupBy", "groupby", "agg", "filter", "where", "join", "select", "drop", "withColumn", "withColumnRenamed", "isin", "col") {
						mutated = true
					}
				}
			}
			for _, c := range children(n) {
				walk(c)
			}
		}
		walk(function)
		if mutated {
			return nil
		}
		if writes > 0 {
			if writes == 1 && !mutated {
				return value
			}
			return nil
		}
	}
	values := moduleConstants(m.tree.RootNode(), m.content)[name]
	if len(values) == 1 {
		return values[0]
	}
	return nil
}

func hasIdentifier(n *sitter.Node, source []byte, name string) bool {
	if n == nil {
		return false
	}
	if n.Kind() == "identifier" && n.Utf8Text(source) == name {
		return true
	}
	for _, c := range children(n) {
		if hasIdentifier(c, source, name) {
			return true
		}
	}
	return false
}

func clauseLiteralValue(n *sitter.Node) bool {
	if !in(n.Kind(), "integer", "float", "string", "true", "false", "none", "list", "tuple", "set", "unary_operator", "parenthesized_expression", "string_start", "string_end", "string_content", "escape_sequence") {
		return false
	}
	for _, c := range children(n) {
		if !clauseLiteralValue(c) {
			return false
		}
	}
	return true
}

func literalClauseAdapter(m *parsedModule, node *sitter.Node, params []string) (string, []ClauseLiteral) {
	bindings := clauseLiteralBindings(m, node, params)
	base := boundaryAdapter(node.Utf8Text(m.content), params)
	if len(bindings) == 0 {
		return base, bindings
	}
	var prelude strings.Builder
	for _, b := range bindings {
		prelude.WriteString(b.Name + " = " + string(m.content[b.StartByte:b.EndByte]) + "\n")
	}
	return prelude.String() + base, bindings
}
