// Package calculationengine inventories existing engine code and dependencies.
package calculationengine

import (
	"context"
	"fmt"
	"github.com/jeisenman/q2_bench/workflows/formallineage/discovery"
	"github.com/jeisenman/q2_bench/workflows/formallineage/model"
	"github.com/jeisenman/q2_bench/workflows/formallineage/projects"
	"path"
)

// Parse retains C#/TypeScript candidates without guessing engine semantics.
func Parse(ctx context.Context, repository string, receipt model.Source, content []byte) (model.ParsedFile, error) {
	if err := projects.Allows("pl-calculation-engine", repository); err != nil {
		return model.ParsedFile{}, err
	}
	switch path.Ext(receipt.Path) {
	case ".cs", ".ts", ".tsx":
	default:
		return model.ParsedFile{}, fmt.Errorf("calculation-engine requires C# or TypeScript source")
	}
	return discovery.Parse(ctx, "pl-calculation-engine", repository, receipt, content)
}
