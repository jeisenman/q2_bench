package dipipelines

import (
	"fmt"
	"math"
	"strconv"
	"strings"
	"time"
)

func scalar(op string, a []any) (any, error) {
	if in(op, "lower", "upper", "trim", "length", "abs", "contains", "startswith", "endswith", "like") {
		return stringScalar(op, a)
	}
	if in(op, "isNull", "isNotNull", "isnull", "isin") {
		return predicateScalar(op, a)
	}
	bad := func() (any, error) { return nil, fmt.Errorf("unsupported operand types for %s", op) }
	if op == "and" || op == "or" {
		for _, x := range a {
			if x != nil {
				if _, ok := x.(bool); !ok {
					return bad()
				}
			}
		}
		if op == "and" {
			if a[0] == false || a[1] == false {
				return false, nil
			}
			if a[0] == nil || a[1] == nil {
				return nil, nil
			}
			return true, nil
		}
		if a[0] == true || a[1] == true {
			return true, nil
		}
		if a[0] == nil || a[1] == nil {
			return nil, nil
		}
		return false, nil
	}
	if op == "str" {
		switch x := a[0].(type) {
		case string:
			return x, nil
		case float64:
			if x == math.Trunc(x) {
				return strconv.FormatFloat(x, 'f', 0, 64), nil
			}
		}
		return nil, fmt.Errorf("str supports strings and integral parameters only")
	}
	for _, x := range a {
		if x == nil {
			return nil, nil
		}
	}
	if op == "cast" {
		return cast(a[0], a[1])
	}
	if op == "not" {
		if x, ok := a[0].(bool); ok {
			return !x, nil
		}
		return bad()
	}
	if op == "neg" {
		if x, ok := a[0].(float64); ok {
			return -x, nil
		}
		return bad()
	}
	if op == "to_date" {
		text, ok := a[0].(string)
		if !ok {
			return bad()
		}
		layout := "2006-01-02"
		if len(a) > 1 {
			switch a[1] {
			case "yyyyMMdd":
				layout = "20060102"
			case "yyyy-MM-dd":
			default:
				return nil, fmt.Errorf("unsupported date format %v", a[1])
			}
		}
		d, err := time.Parse(layout, text)
		if err != nil {
			return nil, nil
		}
		return d.Format("2006-01-02"), nil
	}
	if op == "datediff" || op == "date_add" {
		s, ok := a[0].(string)
		if !ok {
			return bad()
		}
		d, err := time.Parse("2006-01-02", s)
		if err != nil {
			return nil, nil
		}
		if op == "datediff" {
			s, ok := a[1].(string)
			if !ok {
				return bad()
			}
			b, err := time.Parse("2006-01-02", s)
			if err != nil {
				return nil, nil
			}
			return float64(d.Unix()-b.Unix()) / 86400, nil
		}
		n, ok := a[1].(float64)
		if !ok || n != math.Trunc(n) || math.Abs(n) > 365000 {
			return nil, fmt.Errorf("date_add requires integral days within 365000")
		}
		return d.AddDate(0, 0, int(n)).Format("2006-01-02"), nil
	}
	if in(op, "eq", "ne", "lt", "le", "gt", "ge") {
		cmp := 0
		switch x := a[0].(type) {
		case float64:
			y, ok := a[1].(float64)
			if !ok {
				return bad()
			}
			if x < y {
				cmp = -1
			} else if x > y {
				cmp = 1
			}
		case string:
			y, ok := a[1].(string)
			if !ok {
				return bad()
			}
			if x < y {
				cmp = -1
			} else if x > y {
				cmp = 1
			}
		case bool:
			y, ok := a[1].(bool)
			if !ok || !in(op, "eq", "ne") {
				return bad()
			}
			if x != y {
				cmp = 1
			}
		default:
			return bad()
		}
		switch op {
		case "eq":
			return cmp == 0, nil
		case "ne":
			return cmp != 0, nil
		case "lt":
			return cmp < 0, nil
		case "le":
			return cmp <= 0, nil
		case "gt":
			return cmp > 0, nil
		case "ge":
			return cmp >= 0, nil
		}
	}
	if op == "add" {
		if x, ok := a[0].([]any); ok {
			if y, ok := a[1].([]any); ok {
				return append(append([]any{}, x...), y...), nil
			}
			return bad()
		}
		if x, ok := a[0].(string); ok {
			if y, ok := a[1].(string); ok {
				return x + y, nil
			}
			return bad()
		}
	}
	x, ok := a[0].(float64)
	if !ok {
		return bad()
	}
	y, ok := a[1].(float64)
	if !ok {
		return bad()
	}
	var result float64
	switch op {
	case "add":
		result = x + y
	case "sub":
		result = x - y
	case "mul":
		result = x * y
	case "div":
		if y == 0 {
			return nil, nil
		}
		result = x / y
	default:
		return nil, fmt.Errorf("unsupported scalar operator %s", op)
	}
	if math.IsNaN(result) || math.IsInf(result, 0) {
		return nil, fmt.Errorf("numeric result outside finite profile")
	}
	return result, nil
}

func cast(value, target any) (any, error) {
	if target == "string" {
		if s, ok := value.(string); ok {
			return s, nil
		}
		return nil, fmt.Errorf("string cast requires string input in this profile")
	}
	if !in(fmt.Sprint(target), "double", "float", "int") {
		return nil, fmt.Errorf("unsupported cast target %v", target)
	}
	var n float64
	switch x := value.(type) {
	case float64:
		n = x
	case string:
		if target == "int" && strings.ContainsAny(x, "eExX") {
			return nil, nil
		}
		var err error
		n, err = strconv.ParseFloat(strings.TrimSpace(x), 64)
		if err != nil {
			return nil, nil
		}
	default:
		return nil, fmt.Errorf("numeric cast requires number or string")
	}
	if math.IsNaN(n) || math.IsInf(n, 0) {
		return nil, fmt.Errorf("cast result outside finite profile")
	}
	if target == "int" {
		n = math.Trunc(n)
		if n < math.MinInt32 || n > math.MaxInt32 {
			return nil, nil
		}
	}
	if target == "float" {
		n = float64(float32(n))
		if math.IsInf(n, 0) {
			return nil, fmt.Errorf("float cast overflow")
		}
	}
	return n, nil
}
