package formalmethod

import (
	sitter "github.com/tree-sitter/go-tree-sitter"
	"strings"
)

// semanticBindings verifies the small namespace of external operations lowered
// by this dialect. A matching attribute spelling alone is not source evidence.
func semanticBindings(root *sitter.Node, b []byte) map[string]bool {
	allowed := map[string]bool{"str": true}
	var inspect func(*sitter.Node)
	inspect = func(n *sitter.Node) {
		if in(n.Kind(), "function_definition", "class_definition") {
			name := n.ChildByFieldName("name").Utf8Text(b)
			if in(name, "F", "StringType", "str") {
				allowed[name] = false
			}
			return
		}
		if in(n.Kind(), "import_statement", "import_from_statement") {
			module := ""
			if x := n.ChildByFieldName("module_name"); x != nil {
				module = x.Utf8Text(b)
			}
			for _, x := range children(n) {
				if n.ChildByFieldName("module_name") != nil && x.Id() == n.ChildByFieldName("module_name").Id() {
					continue
				}
				name, alias := x.Utf8Text(b), ""
				if x.Kind() == "aliased_import" {
					name = x.ChildByFieldName("name").Utf8Text(b)
					alias = x.ChildByFieldName("alias").Utf8Text(b)
				}
				if alias == "" {
					alias = strings.Split(name, ".")[0]
				}
				if in(alias, "F", "StringType", "str") {
					qualified := name
					if module != "" {
						qualified = module + "." + name
					}
					allowed[alias] = (alias == "F" && qualified == "pyspark.sql.functions") || (alias == "StringType" && qualified == "pyspark.sql.types.StringType")
				}
			}
			return
		}
		if n.Kind() == "assignment" {
			left := n.ChildByFieldName("left")
			if left != nil && left.Kind() == "identifier" && in(left.Utf8Text(b), "F", "StringType", "str") {
				allowed[left.Utf8Text(b)] = false
			}
		}
		for _, x := range children(n) {
			inspect(x)
		}
	}
	inspect(root)
	return allowed
}
