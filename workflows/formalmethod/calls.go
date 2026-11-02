package formalmethod

import "fmt"

func checkCall(e *Expression) error {
	min, max := 0, 0
	var keys []string
	switch e.Op {
	case "col", "lit", "sum", "max", "min", "str", "isNull", "isNotNull", "isnull", "lower", "upper", "trim", "length", "abs", "table_columns":
		min, max = 1, 1
	case "isin":
		min, max = 2, 100
	case "when", "otherwise":
		min, max = 2, 2
	case "when_next":
		min, max = 3, 3
	case "coalesce":
		min, max = 1, 100
	case "between":
		min, max = 3, 3
	case "to_date":
		min, max = 1, 2
		keys = []string{"format"}
	case "datediff", "date_add", "filter", "cast", "alias", "contains", "startswith", "endswith", "like":
		min, max = 2, 2
	case "withColumn", "withColumnRenamed":
		min, max = 3, 3
	case "dropna":
		min, max = 1, 1
		keys = []string{"how", "subset"}
	case "join":
		min, max = 2, 4
		keys = []string{"on", "how"}
	case "select", "groupBy", "agg", "drop":
		min, max = 2, 100
	default:
		return fmt.Errorf("unsupported call operator %s", e.Op)
	}
	if len(e.Args) < min || len(e.Args) > max {
		return fmt.Errorf("%s requires %d..%d positional operands", e.Op, min, max)
	}
	if e.Op == "join" && e.Args[1].Kind != Table {
		return fmt.Errorf("join right operand must be a table")
	}
	if e.Op == "filter" && e.Args[1].Kind != Column {
		return fmt.Errorf("filter requires a Column predicate; SQL strings and Python booleans need separate lowering")
	}
	if in(e.Op, "when", "otherwise", "when_next") && e.Args[0].Kind != Column {
		return fmt.Errorf("%s requires a Column condition/receiver", e.Op)
	}
	if e.Op == "when_next" && e.Args[1].Kind != Column {
		return fmt.Errorf("chained when requires a Column condition")
	}
	if e.Op == "join" {
		on := e.Keywords["on"]
		if len(e.Args) > 2 {
			on = e.Args[2]
		}
		if on != nil && on.Kind != Scalar && on.Kind != List {
			return fmt.Errorf("predicate joins require qualified duplicate-column semantics")
		}
	}
	if in(e.Op, "filter", "drop", "dropna", "withColumn", "withColumnRenamed", "select", "join", "groupBy") && e.Args[0].Kind != Table {
		return fmt.Errorf("%s receiver must be table", e.Op)
	}
	if e.Op == "agg" && e.Args[0].Kind != Grouped {
		return fmt.Errorf("agg receiver must be grouped")
	}
	for k := range e.Keywords {
		if !in(k, keys...) {
			return fmt.Errorf("unsupported %s keyword %s", e.Op, k)
		}
		if (e.Op == "join" && ((k == "on" && len(e.Args) > 2) || (k == "how" && len(e.Args) > 3))) || (e.Op == "to_date" && k == "format" && len(e.Args) > 1) {
			return fmt.Errorf("duplicate argument %s", k)
		}
	}
	if e.Op == "join" && len(e.Args) < 3 && e.Keywords["on"] == nil {
		return fmt.Errorf("join requires explicit keys")
	}
	return nil
}
