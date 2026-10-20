package kubernetes

import (
	"fmt"
	"math/big"
	"strings"
)

var quantityMultipliers = map[string]*big.Int{
	"":   big.NewInt(1),
	"K":  big.NewInt(1_000),
	"M":  big.NewInt(1_000_000),
	"G":  big.NewInt(1_000_000_000),
	"T":  big.NewInt(1_000_000_000_000),
	"Ki": big.NewInt(1 << 10),
	"Mi": big.NewInt(1 << 20),
	"Gi": big.NewInt(1 << 30),
	"Ti": big.NewInt(1 << 40),
}

// ParseMemoryQuantity converts a Kubernetes memory quantity to bytes.
func ParseMemoryQuantity(value string) (uint64, error) {
	value = strings.TrimSpace(value)
	suffix, number := quantitySuffix(value)
	rational, ok := new(big.Rat).SetString(number)
	if !ok || rational.Sign() < 0 {
		return 0, fmt.Errorf("invalid Kubernetes memory quantity %q", value)
	}
	rational.Mul(rational, new(big.Rat).SetInt(quantityMultipliers[suffix]))
	numerator := rational.Num()
	denominator := rational.Denom()
	bytes := new(big.Int).Quo(numerator, denominator)
	if new(big.Int).Mod(numerator, denominator).Sign() > 0 {
		bytes.Add(bytes, big.NewInt(1))
	}
	if !bytes.IsUint64() {
		return 0, fmt.Errorf("Kubernetes memory quantity %q exceeds uint64", value)
	}
	return bytes.Uint64(), nil
}

func quantitySuffix(value string) (string, string) {
	for _, suffix := range []string{"Ki", "Mi", "Gi", "Ti", "K", "M", "G", "T"} {
		if strings.HasSuffix(value, suffix) {
			return suffix, strings.TrimSuffix(value, suffix)
		}
	}
	return "", value
}
