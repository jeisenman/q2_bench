package formalmethod

import (
	"fmt"
	"sort"
	"strings"

	sitter "github.com/tree-sitter/go-tree-sitter"
)

var boundaryFamilies = []string{"predicates", "nulls", "joins", "duplicates", "dates", "empty", "schema", "branches", "arithmetic", "effects"}

func clauseKind(n *sitter.Node, b []byte) string {
	switch n.Kind() {
	case "comparison_operator":
		return "comparison"
	case "if_statement", "elif_clause", "conditional_expression", "boolean_operator":
		return "branch"
	case "for_statement", "while_statement", "try_statement", "except_clause", "raise_statement", "assert_statement":
		return "control"
	case "binary_operator":
		if op := n.ChildByFieldName("operator"); op != nil && in(op.Utf8Text(b), "/", "//", "%") {
			return "division"
		}
	case "subscript":
		return "index_or_projection"
	case "call":
		f := n.ChildByFieldName("function")
		name := f.Utf8Text(b)
		if f.Kind() == "attribute" {
			name = f.ChildByFieldName("attribute").Utf8Text(b)
		}
		switch name {
		case "filter", "where", "query", "between", "isin", "like", "rlike", "startswith", "endswith":
			return "filter"
		case "join", "merge", "crossJoin":
			return "join"
		case "drop", "dropna", "drop_duplicates", "dropDuplicates", "distinct":
			return name
		case "select", "selectExpr", "withColumn", "withColumnRenamed", "rename", "pivot", "unpivot", "stack", "explode", "union", "unionByName":
			return "projection"
		case "groupBy", "groupby", "agg", "sum", "avg", "mean", "min", "max", "count":
			return "aggregate"
		case "when", "otherwise", "coalesce", "fillna", "isNull", "isNotNull", "isnull", "isnan":
			return "null_or_case"
		case "over", "partitionBy", "orderBy", "rank", "row_number", "lag", "lead", "rowsBetween", "rangeBetween", "to_date", "date_add", "datediff", "add_months", "cast":
			return "window_or_cast"
		case "upload", "download", "return_df", "write", "save", "saveAsTable", "insertInto", "copy", "set_uris", "from_runner", "assign_df":
			return "effect"
		case "col", "lit", "alias", "StringType", "DoubleType", "IntegerType", "StructField", "StructType":
			return "" // Operands are retained in their containing clause.
		default:
			return "unclassified_call"
		}
	}
	return ""
}

func familiesFor(kind string) []string {
	switch kind {
	case "comparison", "filter":
		return []string{"predicates", "nulls", "empty"}
	case "join":
		return []string{"joins", "nulls", "duplicates", "empty", "schema"}
	case "dropna", "null_or_case":
		return []string{"nulls", "empty", "schema"}
	case "dropDuplicates", "distinct", "drop_duplicates":
		return []string{"duplicates", "nulls", "empty"}
	case "drop", "projection", "index_or_projection":
		return []string{"schema", "nulls", "empty"}
	case "aggregate", "division":
		return []string{"arithmetic", "duplicates", "nulls", "empty"}
	case "window_or_cast":
		return []string{"dates", "nulls", "duplicates", "empty"}
	case "effect":
		return []string{"effects", "empty", "branches"}
	default:
		return []string{"branches", "nulls", "empty"}
	}
}

func extractBoundaryClauses(m *parsedModule) []BoundaryClause {
	result := []BoundaryClause{}
	var walk func(*sitter.Node, string)
	walk = func(n *sitter.Node, function string) {
		if in(n.Kind(), "function_definition", "class_definition") {
			if function != "" {
				function += "."
			}
			function += n.ChildByFieldName("name").Utf8Text(m.content)
		}
		if kind := clauseKind(n, m.content); kind != "" {
			id := hash([]byte(fmt.Sprintf("%s:%s:%d:%d", m.source.Commit, m.source.Path, n.StartByte(), n.EndByte())))
			result = append(result, BoundaryClause{ID: id, Source: m.source, Function: function, Line: int(n.StartPosition().Row) + 1, StartByte: n.StartByte(), EndByte: n.EndByte(), Kind: kind, Expression: n.Utf8Text(m.content), Families: familiesFor(kind), CaseIDs: []string{}, EdgeCases: describeBoundary(n, m.content, kind)})
		}
		for _, x := range children(n) {
			if function == "" && !in(x.Kind(), "function_definition", "class_definition", "decorated_definition") {
				continue
			}
			walk(x, function)
		}
	}
	walk(m.tree.RootNode(), "")
	return result
}

func moduleFromPath(path string) string {
	for _, prefix := range []string{"ds-jobs/src/", "de-jobs/src/", "ra-jobs/src/"} {
		if strings.HasPrefix(path, prefix) && strings.HasSuffix(path, ".py") {
			return strings.ReplaceAll(strings.TrimSuffix(strings.TrimPrefix(path, prefix), ".py"), "/", ".")
		}
	}
	return ""
}

func sortedUnique(values []string) []string {
	seen := map[string]bool{}
	for _, v := range values {
		seen[v] = true
	}
	result := make([]string, 0, len(seen))
	for v := range seen {
		result = append(result, v)
	}
	sort.Strings(result)
	return result
}

func boundaryImports(m *parsedModule) map[string]string {
	result := sourceImports(m.tree.RootNode(), m.content)
	for _, n := range children(m.tree.RootNode()) {
		if n.Kind() != "import_statement" {
			continue
		}
		for _, x := range children(n) {
			name, alias := x.Utf8Text(m.content), ""
			if x.Kind() == "aliased_import" {
				name = x.ChildByFieldName("name").Utf8Text(m.content)
				alias = x.ChildByFieldName("alias").Utf8Text(m.content)
			}
			if alias == "" {
				alias = strings.Split(name, ".")[0]
				name = alias
			}
			result[alias] = name
		}
	}
	return result
}
