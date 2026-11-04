package dipipelines

import (
	"encoding/json"
	"fmt"
	"strconv"
	"strings"

	sitter "github.com/tree-sitter/go-tree-sitter"
)

func literal(v any) *Expression {
	b, _ := json.Marshal(v)
	return &Expression{Op: "literal", Kind: Scalar, Value: b}
}
func in(s string, options ...string) bool {
	for _, v := range options {
		if s == v {
			return true
		}
	}
	return false
}

func (c *compiler) lower(n *sitter.Node) (*Expression, error) {
	c.nodes++
	if n == nil || c.nodes > maxNodes {
		return nil, fmt.Errorf("missing expression or node limit exceeded")
	}
	text := n.Utf8Text(c.source)
	switch n.Kind() {
	case "parenthesized_expression":
		xs := children(n)
		if len(xs) == 1 {
			return c.lower(xs[0])
		}
	case "identifier":
		k := c.names[text]
		if k != "" {
			return &Expression{Op: "ref", Kind: k, Name: text}, nil
		}
		if len(c.constants[text]) == 1 {
			return c.constant(text, c.constants[text][0])
		}
		return nil, fmt.Errorf("unbound name %s", text)
	case "string":
		s, err := pythonString(text)
		if err != nil {
			return nil, err
		}
		return literal(s), nil
	case "integer", "float":
		v, err := strconv.ParseFloat(strings.ReplaceAll(text, "_", ""), 64)
		if err != nil {
			return nil, fmt.Errorf("unsupported number %s", text)
		}
		return literal(v), nil
	case "true":
		return literal(true), nil
	case "false":
		return literal(false), nil
	case "none":
		return literal(nil), nil
	case "list":
		e := &Expression{Op: "list", Kind: List}
		for _, x := range children(n) {
			a, err := c.lower(x)
			if err != nil {
				return nil, err
			}
			if a.Kind != Scalar {
				return nil, fmt.Errorf("list elements must be scalar")
			}
			e.Args = append(e.Args, a)
		}
		return e, nil
	case "tuple", "expression_list":
		e := &Expression{Op: "tuple", Kind: Tuple}
		for _, x := range children(n) {
			a, err := c.lower(x)
			if err != nil {
				return nil, err
			}
			if a.Kind != Table {
				return nil, fmt.Errorf("tuple values must be relations")
			}
			e.Args = append(e.Args, a)
		}
		return e, nil
	case "attribute":
		base, err := c.lower(n.ChildByFieldName("object"))
		if err != nil {
			return nil, err
		}
		if base.Kind != Table {
			return nil, fmt.Errorf("attribute requires table")
		}
		attribute := n.ChildByFieldName("attribute").Utf8Text(c.source)
		if attribute == "columns" {
			return &Expression{Op: "table_columns", Kind: List, Args: []*Expression{base}}, nil
		}
		if in(attribute, "schema", "dtypes", "rdd", "na", "write", "stat", "sparkSession", "isStreaming", "storageLevel") {
			return nil, fmt.Errorf("DataFrame metadata attribute %s requires explicit lowering", attribute)
		}
		if base.Op != "ref" {
			return nil, fmt.Errorf("column receiver requires a bound relation")
		}
		return &Expression{Op: "column", Kind: Column, Name: n.ChildByFieldName("attribute").Utf8Text(c.source), Origin: base.Name}, nil
	case "subscript":
		base, err := c.lower(n.ChildByFieldName("value"))
		if err != nil {
			return nil, err
		}
		index := n.ChildByFieldName("subscript")
		if base.Kind != Table || index == nil || index.Kind() != "string" {
			return nil, fmt.Errorf("only literal table column subscripts supported")
		}
		name, err := pythonString(index.Utf8Text(c.source))
		if err != nil {
			return nil, err
		}
		if !simpleColumnName(name) {
			return nil, fmt.Errorf("nested or quoted column resolution is outside the primitive profile")
		}
		if base.Op != "ref" {
			return nil, fmt.Errorf("column receiver requires a bound relation")
		}
		return &Expression{Op: "column", Kind: Column, Name: name, Origin: base.Name}, nil
	case "binary_operator", "comparison_operator":
		left, right := n.ChildByFieldName("left"), n.ChildByFieldName("right")
		xs := children(n)
		if n.Kind() == "comparison_operator" {
			if len(xs) != 2 {
				return nil, fmt.Errorf("chained comparisons unsupported")
			}
			left, right = xs[0], xs[1]
		}
		if left == nil || right == nil {
			return nil, fmt.Errorf("missing binary operands")
		}
		opText := strings.TrimSpace(string(c.source[left.EndByte():right.StartByte()]))
		ops := map[string]string{"+": "add", "-": "sub", "*": "mul", "/": "div", "&": "and", "|": "or", "==": "eq", "!=": "ne", "<": "lt", "<=": "le", ">": "gt", ">=": "ge"}
		return c.binary(ops[opText], left, right)
	case "unary_operator":
		op := n.ChildByFieldName("operator").Utf8Text(c.source)
		if !in(op, "~", "-") {
			return nil, fmt.Errorf("unsupported unary operator %s", op)
		}
		x, err := c.lower(n.ChildByFieldName("argument"))
		if err != nil {
			return nil, err
		}
		if op == "~" && x.Kind != Column {
			return nil, fmt.Errorf("scalar bitwise inversion is outside the semantic profile")
		}
		name := "not"
		if op == "-" {
			name = "neg"
		}
		return &Expression{Op: name, Kind: x.Kind, Args: []*Expression{x}}, nil
	case "call":
		return c.call(n)
	}
	return nil, fmt.Errorf("unsupported expression %s", n.Kind())
}

func pythonString(s string) (string, error) {
	if len(s) < 2 || !in(s[:1], "'", "\"") || strings.HasPrefix(s, "'''") || strings.HasPrefix(s, "\"\"\"") {
		return "", fmt.Errorf("prefixed or multiline strings require explicit lowering")
	}
	q := s[0]
	if s[len(s)-1] != q {
		return "", fmt.Errorf("invalid string")
	}
	s = s[1 : len(s)-1]
	var out strings.Builder
	for s != "" {
		r, _, tail, err := strconv.UnquoteChar(s, q)
		if err != nil {
			return "", fmt.Errorf("unsupported string escape: %w", err)
		}
		out.WriteRune(r)
		s = tail
	}
	return out.String(), nil
}

func (c *compiler) binary(op string, left, right *sitter.Node) (*Expression, error) {
	if op == "" {
		return nil, fmt.Errorf("unsupported binary operator")
	}
	a, err := c.lower(left)
	if err != nil {
		return nil, err
	}
	b, err := c.lower(right)
	if err != nil {
		return nil, err
	}
	if op == "add" && a.Kind == List && b.Kind == List {
		return &Expression{Op: op, Kind: List, Args: []*Expression{a, b}}, nil
	}
	if in(op, "and", "or") && a.Kind != Column && b.Kind != Column {
		return nil, fmt.Errorf("scalar bitwise operations are outside the semantic profile")
	}
	if (a.Kind != Scalar && a.Kind != Column) || (b.Kind != Scalar && b.Kind != Column) {
		return nil, fmt.Errorf("binary operands require scalar or column")
	}
	k := Scalar
	if a.Kind == Column || b.Kind == Column {
		k = Column
	}
	return &Expression{Op: op, Kind: k, Args: []*Expression{a, b}}, nil
}

func (c *compiler) call(n *sitter.Node) (*Expression, error) {
	target := n.ChildByFieldName("function")
	args := children(n.ChildByFieldName("arguments"))
	e := &Expression{Keywords: map[string]*Expression{}}
	if target.Kind() == "identifier" {
		name := target.Utf8Text(c.source)
		if len(c.definitions[name]) > 0 {
			return c.link(name, args)
		}
		if !c.symbols[name] {
			return nil, fmt.Errorf("call %s has no verified semantic binding", name)
		}
		if name == "StringType" && len(args) == 0 {
			return literal("string"), nil
		}
		if name != "str" {
			return nil, fmt.Errorf("helper %s requires linking and explicit lowering", name)
		}
		e.Op = "str"
		e.Kind = Scalar
	} else if target.Kind() == "attribute" {
		object := target.ChildByFieldName("object")
		e.Op = target.ChildByFieldName("attribute").Utf8Text(c.source)
		if e.Op == "groupby" {
			e.Op = "groupBy"
		}
		if e.Op == "where" {
			e.Op = "filter"
		}
		if object.Kind() == "identifier" && object.Utf8Text(c.source) == "F" {
			if !c.symbols["F"] {
				return nil, fmt.Errorf("F is not bound to pyspark.sql.functions")
			}
			e.Kind = Column
			if !in(e.Op, "col", "lit", "to_date", "datediff", "date_add", "sum", "max", "min", "isnull", "lower", "upper", "trim", "length", "abs", "when", "coalesce") {
				return nil, fmt.Errorf("unsupported Spark function F.%s", e.Op)
			}
		} else {
			base, err := c.lower(object)
			if err != nil {
				return nil, err
			}
			e.Args = append(e.Args, base)
			switch base.Kind {
			case Table:
				e.Kind = Table
				if e.Op == "groupBy" {
					e.Kind = Grouped
				} else if !in(e.Op, "filter", "drop", "dropna", "withColumn", "withColumnRenamed", "select", "join") {
					return nil, fmt.Errorf("unsupported table operation %s", e.Op)
				}
			case Grouped:
				if e.Op != "agg" {
					return nil, fmt.Errorf("unsupported grouped operation %s", e.Op)
				}
				e.Kind = Table
			case Column:
				if !in(e.Op, "cast", "alias", "isNull", "isNotNull", "isin", "between", "contains", "startswith", "endswith", "like", "when", "otherwise") {
					return nil, fmt.Errorf("unsupported column operation %s", e.Op)
				}
				if e.Op == "when" {
					e.Op = "when_next"
				}
				e.Kind = Column
			default:
				return nil, fmt.Errorf("unsupported receiver for %s", e.Op)
			}
		}
	} else {
		return nil, fmt.Errorf("dynamic calls require explicit lowering")
	}
	for _, a := range args {
		if a.Kind() == "keyword_argument" {
			name := a.ChildByFieldName("name").Utf8Text(c.source)
			if e.Keywords[name] != nil {
				return nil, fmt.Errorf("duplicate keyword %s", name)
			}
			x, err := c.lower(a.ChildByFieldName("value"))
			if err != nil {
				return nil, err
			}
			e.Keywords[name] = x
		} else {
			xs, err := c.lowerArgument(e.Op, a)
			if err != nil {
				return nil, err
			}
			e.Args = append(e.Args, xs...)
		}
	}
	if err := checkCall(e); err != nil {
		return nil, err
	}
	if in(e.Op, "lower", "upper", "trim", "length", "abs", "isnull") && e.Args[0].Kind == Scalar {
		e.Args[0] = &Expression{Op: "col", Kind: Column, Args: []*Expression{e.Args[0]}}
	}
	if e.Op == "coalesce" {
		for i, a := range e.Args {
			if a.Kind == Scalar {
				e.Args[i] = &Expression{Op: "col", Kind: Column, Args: []*Expression{a}}
			}
		}
	}
	if e.Op == "col" {
		name, ok := expressionLiteral(e.Args[0])
		text, yes := name.(string)
		if e.Args[0].Kind != Scalar || (ok && (!yes || !simpleColumnName(text))) {
			return nil, fmt.Errorf("col requires a simple string name; nested and quoted resolution is outside the primitive profile")
		}
	}
	if e.Op == "between" {
		return &Expression{Op: "and", Kind: Column, Args: []*Expression{{Op: "ge", Kind: Column, Args: []*Expression{e.Args[0], e.Args[1]}}, {Op: "le", Kind: Column, Args: []*Expression{e.Args[0], e.Args[2]}}}}, nil
	}
	if in(e.Op, "sum", "max", "min") && e.Args[0].Op == "literal" {
		var name string
		if err := json.Unmarshal(e.Args[0].Value, &name); err != nil {
			return nil, fmt.Errorf("aggregate literal must name a column")
		}
		e.Args[0] = &Expression{Op: "column", Kind: Column, Name: name}
	}
	return e, nil
}
