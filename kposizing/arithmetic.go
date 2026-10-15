package kposizing

import (
	"fmt"
	"math/bits"
)

func checkedAdd(name string, values ...uint64) (uint64, error) {
	var total uint64
	for _, value := range values {
		next, carry := bits.Add64(total, value, 0)
		if carry != 0 {
			return 0, fmt.Errorf("%s exceeds the uint64 byte range", name)
		}
		total = next
	}
	return total, nil
}

func checkedMultiply(name string, left, right uint64) (uint64, error) {
	high, low := bits.Mul64(left, right)
	if high != 0 {
		return 0, fmt.Errorf("%s exceeds the uint64 byte range", name)
	}
	return low, nil
}

func ceilMultiply(name string, value uint64, ratio Ratio) (uint64, error) {
	if ratio.Denominator == 0 {
		return 0, fmt.Errorf("%s ratio denominator must be greater than zero", name)
	}
	high, low := bits.Mul64(value, ratio.Numerator)
	if high >= ratio.Denominator {
		return 0, fmt.Errorf("%s exceeds the uint64 byte range", name)
	}
	quotient, remainder := bits.Div64(high, low, ratio.Denominator)
	if remainder == 0 {
		return quotient, nil
	}
	return checkedAdd(name, quotient, 1)
}

func ratioGreater(left, right Ratio) bool {
	leftHigh, leftLow := bits.Mul64(left.Numerator, right.Denominator)
	rightHigh, rightLow := bits.Mul64(right.Numerator, left.Denominator)
	if leftHigh != rightHigh {
		return leftHigh > rightHigh
	}
	return leftLow > rightLow
}

func sumBytes(name string, values []uint64) (uint64, error) {
	return checkedAdd(name, values...)
}
