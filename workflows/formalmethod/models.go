// Package formalmethod compiles restricted Python relations into executable contracts.
package formalmethod

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
)

const (
	// Format identifies the separately versioned executable contract.
	Format = "q2-formal-method/v1"
	// Profile fixes the deliberately restricted evaluator semantics.
	Profile   = "bag-sql-null-utc-float64-ansi-off/v1"
	maxSource = 1 << 20
	maxNodes  = 10000
	maxRows   = 10000
)

// Kind describes an expression's value category.
type Kind string

const (
	Scalar  Kind = "scalar"
	Column  Kind = "column"
	Table   Kind = "table"
	List    Kind = "list"
	Grouped Kind = "grouped"
	Tuple   Kind = "table_tuple"
)

// Source pins the exact Python file compiled into a method.
type Source struct {
	Commit string `json:"commit"`
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
}

// Parameter declares a required input port.
type Parameter struct {
	Name string `json:"name"`
	Kind Kind   `json:"kind"`
}

// Expression is a closed operator tree; no application calls survive lowering.
type Expression struct {
	Op       string                 `json:"op"`
	Kind     Kind                   `json:"kind"`
	Name     string                 `json:"name,omitempty"`
	Origin   string                 `json:"origin,omitempty"`
	Value    json.RawMessage        `json:"value,omitempty"`
	Args     []*Expression          `json:"args,omitempty"`
	Keywords map[string]*Expression `json:"keywords,omitempty"`
}

// Step binds a value or returns the final relation in source order.
type Step struct {
	Target     string      `json:"target,omitempty"`
	Targets    []string    `json:"targets,omitempty"`
	Line       int         `json:"line"`
	Return     bool        `json:"return,omitempty"`
	Expression *Expression `json:"expression"`
}

// Diagnostic identifies a source construct that prevents compilation.
type Diagnostic struct {
	Line    int    `json:"line"`
	Message string `json:"message"`
}

// Method is a content-addressed executable contract or an explicit unknown.
type Method struct {
	Format      string            `json:"format"`
	ID          string            `json:"id"`
	Profile     string            `json:"semantic_profile"`
	Function    string            `json:"function"`
	Source      Source            `json:"source"`
	Parameters  []Parameter       `json:"parameters"`
	Outputs     []Parameter       `json:"outputs,omitempty"`
	Status      string            `json:"status"`
	Steps       []Step            `json:"steps"`
	Diagnostics []Diagnostic      `json:"diagnostics"`
	Library     map[string]Method `json:"library,omitempty"`
	Assumptions []string          `json:"assumptions,omitempty"`
}

// Row preserves column values and duplicate row multiplicity in a table bag.
// Values must be null, finite float64 numbers, strings, or booleans.
type Row map[string]any

// Bindings supplies all required method parameters, without ambient state.
type Bindings struct {
	Tables  map[string][]Row    `json:"tables"`
	Scalars map[string]any      `json:"scalars"`
	Schemas map[string][]string `json:"schemas,omitempty"`
}

// Result retains every returned relation and its schema under a stable port name.
type Result struct {
	Tables  map[string][]Row    `json:"tables"`
	Schemas map[string][]string `json:"schemas"`
}

func hash(b []byte) string {
	s := sha256.Sum256(b)
	return hex.EncodeToString(s[:])
}

func methodID(m Method) string {
	m.ID = ""
	// Invocations bind child content IDs; the flat library is validated separately.
	m.Library = nil
	b, _ := json.Marshal(m)
	return hash(b)
}
