// Package dipipelines compiles and verifies DI Pipelines source contracts.
package dipipelines

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"

	"github.com/jeisenman/q2_bench/workflows/formallineage/model"
)

// Format preserves the existing executable artifact contract.
const Format = model.Format

// Profile fixes the verified Spark evaluator semantics.
const Profile = model.SparkProfile
const (
	maxSource = 1 << 20
	maxNodes  = 10000
	maxRows   = 10000
)

// Kind uses the shared formal model.
type Kind = model.Kind

// Source uses the shared formal model.
type Source = model.Source

// Parameter uses the shared formal model.
type Parameter = model.Parameter

// Expression uses the shared formal model.
type Expression = model.Expression

// Step uses the shared formal model.
type Step = model.Step

// Diagnostic uses the shared formal model.
type Diagnostic = model.Diagnostic

// Method uses the shared formal model.
type Method = model.Method

// Row uses the shared formal model.
type Row = model.Row

// Bindings uses the shared formal model.
type Bindings = model.Bindings

// Result uses the shared formal model.
type Result = model.Result

// Scalar is a shared expression kind.
const Scalar = model.Scalar

// Column is a shared expression kind.
const Column = model.Column

// Table is a shared expression kind.
const Table = model.Table

// List is a shared expression kind.
const List = model.List

// Grouped is a shared expression kind.
const Grouped = model.Grouped

// Tuple is a shared expression kind.
const Tuple = model.Tuple

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
