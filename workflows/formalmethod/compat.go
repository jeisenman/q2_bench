package formalmethod

import (
	"context"

	"github.com/jeisenman/q2_bench/workflows/formallineage/dipipelines"
)

// BoundarySummary forwards to the DI Pipelines adapter.
func BoundarySummary(s BoundarySuite) map[string]any { return dipipelines.BoundarySummary(s) }

// CheckBoundaryEvidence forwards to the DI Pipelines adapter.
func CheckBoundaryEvidence(ctx context.Context, suite BoundarySuite, observations []ClauseObservation) (BoundaryEvidence, error) {
	return dipipelines.CheckBoundaryEvidence(ctx, suite, observations)
}

// Compile forwards to the DI Pipelines adapter.
func Compile(content []byte, source Source, function string, tables []string) (Method, error) {
	return dipipelines.Compile(content, source, function, tables)
}

// CompileCases forwards to the DI Pipelines adapter.
func CompileCases(ctx context.Context, root string, recipes []CaseRecipe) ([]ComparisonCase, error) {
	return dipipelines.CompileCases(ctx, root, recipes)
}

// CompileGit forwards to the DI Pipelines adapter.
func CompileGit(ctx context.Context, root, commit, file, function string, tables []string) (Method, error) {
	return dipipelines.CompileGit(ctx, root, commit, file, function, tables)
}

// DecodeBoundaryGraphPin forwards to the DI Pipelines adapter.
func DecodeBoundaryGraphPin(content []byte) (string, error) {
	return dipipelines.DecodeBoundaryGraphPin(content)
}

// DecodeBoundaryObservations forwards to the DI Pipelines adapter.
func DecodeBoundaryObservations(content []byte) ([]ClauseObservation, error) {
	return dipipelines.DecodeBoundaryObservations(content)
}

// DescribeInventory forwards to the DI Pipelines adapter.
func DescribeInventory(ctx context.Context, root string, inventory Inventory) (InterfaceInventory, error) {
	return dipipelines.DescribeInventory(ctx, root, inventory)
}

// DescribeJob forwards to the DI Pipelines adapter.
func DescribeJob(ctx context.Context, root, commit, entrypoint string) (JobInterface, error) {
	return dipipelines.DescribeJob(ctx, root, commit, entrypoint)
}

// Evaluate forwards to the DI Pipelines adapter.
func Evaluate(ctx context.Context, m Method, b Bindings) ([]Row, error) {
	return dipipelines.Evaluate(ctx, m, b)
}

// EvaluateOutputs forwards to the DI Pipelines adapter.
func EvaluateOutputs(ctx context.Context, m Method, b Bindings) (Result, error) {
	return dipipelines.EvaluateOutputs(ctx, m, b)
}

// GeneratePropertySuite forwards to the DI Pipelines adapter.
func GeneratePropertySuite(ctx context.Context, suite BoundarySuite, config PropertyConfig) (BoundarySuite, error) {
	return dipipelines.GeneratePropertySuite(ctx, suite, config)
}

// InventoryGit forwards to the DI Pipelines adapter.
func InventoryGit(ctx context.Context, root, commit string) (Inventory, error) {
	return dipipelines.InventoryGit(ctx, root, commit)
}

// LoadBoundarySuite forwards to the DI Pipelines adapter.
func LoadBoundarySuite(dir string) (BoundarySuite, error) { return dipipelines.LoadBoundarySuite(dir) }

// PendingBoundaryCases forwards to the DI Pipelines adapter.
func PendingBoundaryCases(ctx context.Context, suite BoundarySuite, observations []ClauseObservation) ([]ComparisonCase, error) {
	return dipipelines.PendingBoundaryCases(ctx, suite, observations)
}

// PlanBoundariesGit forwards to the DI Pipelines adapter.
func PlanBoundariesGit(ctx context.Context, root string, inventory Inventory, graphBytes []byte) (BoundarySuite, error) {
	return dipipelines.PlanBoundariesGit(ctx, root, inventory, graphBytes)
}

// PrepareComparison forwards to the DI Pipelines adapter.
func PrepareComparison(ctx context.Context, root string, cases []ComparisonCase) (ComparisonPayload, error) {
	return dipipelines.PrepareComparison(ctx, root, cases)
}

// WriteBoundarySuite forwards to the DI Pipelines adapter.
func WriteBoundarySuite(dir string, suite BoundarySuite) error {
	return dipipelines.WriteBoundarySuite(dir, suite)
}
