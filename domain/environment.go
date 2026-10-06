// Package domain contains provider-neutral SDK contracts.
package domain

import (
	"fmt"
	"strings"
)

// Environment identifies where warehouse and inference calls are served.
type Environment string

const (
	EnvironmentDev     Environment = "dev"
	EnvironmentStage   Environment = "stage"
	EnvironmentProd    Environment = "prod"
	EnvironmentSandbox Environment = "sandbox"
)

// ParseEnvironment validates and normalizes a configured environment name.
func ParseEnvironment(name string) (Environment, error) {
	normalized := strings.ToLower(strings.TrimSpace(name))
	switch Environment(normalized) {
	case EnvironmentDev, EnvironmentStage, EnvironmentProd, EnvironmentSandbox:
		return Environment(normalized), nil
	default:
		return "", fmt.Errorf(
			"unknown environment %q; supported: dev, stage, prod, sandbox",
			name,
		)
	}
}

// Deterministic reports whether repeated calls must return identical results.
func (e Environment) Deterministic() bool {
	return e == EnvironmentSandbox
}

// Production reports whether the environment serves production data.
func (e Environment) Production() bool {
	return e == EnvironmentProd
}
