package model

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
)

// Runtime identifies the source semantics that still require explicit binding.
type Runtime string

const (
	// Pandas identifies Pandas source operations.
	Pandas Runtime = "pandas"
	// PySpark identifies PySpark source operations.
	PySpark Runtime = "pyspark"
	// PythonUnbound retains missing or mixed Python engine bindings.
	PythonUnbound Runtime = "python-unbound"
	// DotNet identifies C# source operations.
	DotNet Runtime = "dotnet"
	// TypeScript identifies TypeScript source operations.
	TypeScript Runtime = "typescript"
	// ADF identifies declarative orchestration.
	ADF Runtime = "adf"
)

// Span binds a syntax observation to source bytes or a JSON pointer.
type Span struct {
	StartByte   uint   `json:"start_byte"`
	EndByte     uint   `json:"end_byte"`
	Line        int    `json:"line"`
	JSONPointer string `json:"json_pointer,omitempty"`
}

// Operation retains a normalized candidate without claiming executable lowering.
type Operation struct {
	Kind       string `json:"kind"`
	Expression string `json:"expression"`
	Span       Span   `json:"span"`
	Resolved   bool   `json:"resolved"`
}

// Declaration pairs the common program contract with syntax-only observations.
type Declaration struct {
	Method       Method      `json:"method"`
	Runtime      Runtime     `json:"runtime"`
	Span         Span        `json:"span"`
	Operations   []Operation `json:"operations"`
	Dependencies []string    `json:"dependencies"`
}

// ParsedFile retains complete source identity and unresolved discovery scope.
type ParsedFile struct {
	Format          string        `json:"format"`
	Project         string        `json:"project"`
	Repository      string        `json:"repository"`
	Source          Source        `json:"source"`
	Runtime         Runtime       `json:"runtime"`
	Declarations    []Declaration `json:"declarations"`
	ModuleCalls     []Operation   `json:"module_calls"`
	Imports         []string      `json:"imports"`
	Unresolved      []string      `json:"unresolved"`
	Status          string        `json:"status"`
	PredictionReady bool          `json:"prediction_ready"`
}

// MethodID preserves canonical executable-contract hashing across project moves.
func MethodID(method Method) (string, error) {
	method.ID = ""
	method.Library = nil
	b, err := json.Marshal(method)
	if err != nil {
		return "", fmt.Errorf("encode formal method identity: %w", err)
	}
	digest := sha256.Sum256(b)
	return hex.EncodeToString(digest[:]), nil
}
