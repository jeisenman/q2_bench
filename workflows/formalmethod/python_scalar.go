package formalmethod

import "fmt"

// Python control values have different null/error behavior from Spark columns.
// This separation prevents a scalar TypeError from becoming SQL NULL rows.
func pythonScalar(op string, args []any) (any, error) {
	if in(op, "eq", "ne") {
		equal := false
		if args[0] == nil || args[1] == nil {
			equal = args[0] == nil && args[1] == nil
		} else {
			a, aNum := pythonNumber(args[0])
			b, bNum := pythonNumber(args[1])
			if aNum && bNum {
				equal = a == b
			} else if a, ok := args[0].(string); ok {
				if b, ok := args[1].(string); ok {
					equal = a == b
				}
			}
		}
		if op == "ne" {
			return !equal, nil
		}
		return equal, nil
	}
	for _, value := range args {
		if value == nil {
			return nil, fmt.Errorf("Python scalar %s does not accept None", op)
		}
	}
	if op == "div" {
		if divisor, ok := pythonNumber(args[1]); ok && divisor == 0 {
			return nil, fmt.Errorf("Python scalar division by zero")
		}
	}
	return scalar(op, args)
}

func pythonNumber(value any) (float64, bool) {
	switch x := value.(type) {
	case float64:
		return x, true
	case bool:
		if x {
			return 1, true
		}
		return 0, true
	}
	return 0, false
}
