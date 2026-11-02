package formalmethod

import (
	"fmt"
	"strings"
)

func stringField(e *Expression, receiver string) string {
	if name := columnName(e, receiver); name != "" {
		return name
	}
	if in(e.Op, "lower", "upper", "trim") && len(e.Args) == 1 {
		return stringField(e.Args[0], receiver)
	}
	return ""
}

func stringPredicateDomain(e *Expression, receiver string) (string, []any, error) {
	name := stringField(e.Args[0], receiver)
	value, ok := expressionLiteral(e.Args[1])
	pattern, yes := value.(string)
	if name == "" || !ok || !yes {
		return "", nil, fmt.Errorf("string predicate requires a direct string field and literal pattern")
	}
	match := pattern
	if e.Op == "like" {
		if _, err := sqlLikePattern(pattern); err != nil {
			return "", nil, err
		}
		var b strings.Builder
		escaped := false
		for _, r := range pattern {
			if escaped {
				b.WriteRune(r)
				escaped = false
				continue
			}
			switch r {
			case '\\':
				escaped = true
			case '%':
				b.WriteString("fragment")
			case '_':
				b.WriteRune('x')
			default:
				b.WriteRune(r)
			}
		}
		match = b.String()
	}
	return name, []any{match, pattern, "", " ", "unmatched", match + "X", "X" + match, "X" + match + "X", strings.ToUpper(match), strings.ToLower(match), " " + match + " ", "\n" + match + "\n", nil}, nil
}
