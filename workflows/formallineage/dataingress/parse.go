// Package dataingress inventories existing ingress and engine-proxy C# source.
package dataingress

import (
	"context"
	"fmt"
	"github.com/jeisenman/q2_bench/workflows/formallineage/discovery"
	"github.com/jeisenman/q2_bench/workflows/formallineage/model"
	"github.com/jeisenman/q2_bench/workflows/formallineage/projects"
	"strings"
)

// Parse retains C# syntax candidates while leaving type/effect binding unknown.
func Parse(ctx context.Context, repository string, receipt model.Source, content []byte) (model.ParsedFile, error) {
	if err := projects.Allows("data-ingress", repository); err != nil {
		return model.ParsedFile{}, err
	}
	if !strings.HasSuffix(receipt.Path, ".cs") {
		return model.ParsedFile{}, fmt.Errorf("data-ingress requires C# source")
	}
	if repository == "pl-application" && !strings.HasPrefix(receipt.Path, "PrecisionLender.Common.Engine.Proxy/ServiceWrappers/") {
		return model.ParsedFile{}, fmt.Errorf("application source is restricted to engine service wrappers")
	}
	return discovery.Parse(ctx, "data-ingress", repository, receipt, content)
}
