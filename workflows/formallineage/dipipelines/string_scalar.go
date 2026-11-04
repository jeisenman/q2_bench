package dipipelines

import (
	"fmt"
	"math"
	"regexp"
	"strings"
	"unicode/utf8"
)

func stringScalar(op string, args []any) (any, error) {
	for _, a := range args {
		if a == nil {
			return nil, nil
		}
	}
	if op == "abs" {
		if x, ok := args[0].(float64); ok {
			return math.Abs(x), nil
		}
		return nil, fmt.Errorf("abs requires a numeric column within this profile")
	}
	value, ok := args[0].(string)
	if !ok {
		return nil, fmt.Errorf("%s requires a string column within this profile", op)
	}
	switch op {
	case "length":
		return float64(utf8.RuneCountInString(value)), nil
	case "trim":
		return strings.Trim(value, " "), nil
	case "lower", "upper":
		for _, r := range value {
			if r > 127 {
				return nil, fmt.Errorf("Unicode case mapping requires a separate semantic profile")
			}
		}
		if op == "lower" {
			return strings.ToLower(value), nil
		}
		return strings.ToUpper(value), nil
	}
	pattern, ok := args[1].(string)
	if !ok {
		return nil, fmt.Errorf("%s requires a string pattern", op)
	}
	switch op {
	case "contains":
		return strings.Contains(value, pattern), nil
	case "startswith":
		return strings.HasPrefix(value, pattern), nil
	case "endswith":
		return strings.HasSuffix(value, pattern), nil
	case "like":
		re, err := sqlLikePattern(pattern)
		if err != nil {
			return nil, err
		}
		return re.MatchString(value), nil
	}
	return nil, fmt.Errorf("unsupported string operation %s", op)
}

func sqlLikePattern(pattern string) (*regexp.Regexp, error) {
	var b strings.Builder
	b.WriteString("(?s)^")
	escaped := false
	for _, r := range pattern {
		if escaped {
			if r != '%' && r != '_' && r != '\\' {
				return nil, fmt.Errorf("invalid SQL LIKE escape")
			}
			b.WriteString(regexp.QuoteMeta(string(r)))
			escaped = false
			continue
		}
		switch r {
		case '\\':
			escaped = true
		case '%':
			b.WriteString(".*")
		case '_':
			b.WriteString(".")
		default:
			b.WriteString(regexp.QuoteMeta(string(r)))
		}
	}
	if escaped {
		return nil, fmt.Errorf("unterminated SQL LIKE escape")
	}
	b.WriteString("$")
	return regexp.Compile(b.String())
}
