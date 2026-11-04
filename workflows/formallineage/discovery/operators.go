package discovery

import (
	"strings"

	"github.com/jeisenman/q2_bench/workflows/formallineage/model"
	sitter "github.com/tree-sitter/go-tree-sitter"
)

func isImport(kind string) bool {
	return kind == "import_statement" || kind == "import_from_statement" || kind == "using_directive"
}

func isScope(kind string) bool {
	return kind == "class_definition" || kind == "class_declaration" || kind == "struct_declaration" || kind == "namespace_declaration" || kind == "file_scoped_namespace_declaration"
}

func isMethod(kind string) bool {
	return kind == "function_definition" || kind == "function_declaration" || kind == "method_declaration" || kind == "constructor_declaration" || kind == "method_definition" || kind == "local_function_statement"
}

func span(n *sitter.Node) model.Span {
	return model.Span{StartByte: n.StartByte(), EndByte: n.EndByte(), Line: int(n.StartPosition().Row) + 1}
}

func operation(n *sitter.Node, content []byte) (model.Operation, string, bool) {
	kind, dependency := "", ""
	switch n.Kind() {
	case "call", "invocation_expression", "call_expression", "object_creation_expression", "new_expression":
		f := n.ChildByFieldName("function")
		if f == nil {
			f = n.ChildByFieldName("type")
		}
		if f != nil {
			dependency = f.Utf8Text(content)
			for _, name := range []string{"attribute", "name", "property"} {
				if field := f.ChildByFieldName(name); field != nil {
					kind = candidateKind(field.Utf8Text(content))
					break
				}
			}
			if kind == "" {
				kind = candidateKind(dependency)
			}
		} else {
			kind = "call"
		}
	case "binary_operator", "binary_expression", "comparison_operator":
		kind = "expression"
	case "if_statement", "conditional_expression", "switch_statement", "switch_expression":
		kind = "branch"
	case "where_clause":
		kind = "filter"
	case "join_clause":
		kind = "join"
	case "select_clause", "let_clause":
		kind = "project"
	case "group_clause":
		kind = "aggregate"
	case "order_by_clause":
		kind = "order_or_window"
	case "subscript", "element_access_expression", "subscript_expression":
		kind = "index_or_projection"
	case "comment":
		if strings.HasPrefix(n.Utf8Text(content), "# MAGIC") {
			kind = "notebook_magic"
		}
	}
	if kind == "" {
		return model.Operation{}, "", false
	}
	return model.Operation{Kind: kind, Expression: n.Utf8Text(content), Span: span(n)}, dependency, true
}

func candidateKind(name string) string {
	name = strings.ToLower(strings.SplitN(name, "<", 2)[0])
	switch name {
	case "where", "filter", "query":
		return "filter"
	case "select", "selectexpr", "withcolumn", "assign":
		return "project"
	case "join", "merge", "groupjoin", "crossjoin":
		return "join"
	case "drop", "dropna":
		return "drop"
	case "rename", "withcolumnrenamed":
		return "rename"
	case "groupby", "agg", "sum", "count", "min", "max", "average", "mean":
		return "aggregate"
	case "distinct", "dropduplicates", "drop_duplicates":
		return "deduplicate"
	case "orderby", "sort_values", "sortby", "over", "partitionby":
		return "order_or_window"
	case "when", "otherwise", "coalesce", "fillna", "isnull", "isnotnull":
		return "null_or_case"
	case "union", "unionbyname", "concat":
		return "union"
	}
	if strings.HasPrefix(name, "load") || strings.HasPrefix(name, "read") || name == "download" {
		return "read"
	}
	if strings.HasPrefix(name, "output") || strings.HasPrefix(name, "write") || name == "upload" || name == "save" {
		return "write"
	}
	return "call"
}
