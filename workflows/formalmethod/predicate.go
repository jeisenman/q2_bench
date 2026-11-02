package formalmethod

import (
	"fmt"
	"strings"
)

func simpleColumnName(name string) bool {
	return name != "" && !strings.ContainsAny(name, ".`\x00\r\n")
}

func predicateScalar(op string, args []any) (any, error) {
	if in(op, "isNull", "isnull") {
		return args[0] == nil, nil
	}
	if op == "isNotNull" {
		return args[0] != nil, nil
	}
	if op != "isin" {
		return nil, fmt.Errorf("unsupported predicate %s", op)
	}
	choices := args[1:]
	if len(choices) == 1 {
		if list, ok := choices[0].([]any); ok {
			choices = list
		}
	}
	if len(choices) == 0 {
		return false, nil
	}
	if args[0] == nil {
		return nil, nil
	}
	unknown := false
	for _, choice := range choices {
		if err := scalarValue(choice); err != nil {
			return nil, err
		}
		equal, err := scalar("eq", []any{args[0], choice})
		if err != nil {
			return nil, err
		}
		if equal == true {
			return true, nil
		}
		unknown = unknown || equal == nil
	}
	if unknown {
		return nil, nil
	}
	return false, nil
}
