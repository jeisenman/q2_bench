package calculationengine

import (
	"context"
	"fmt"
	"github.com/jeisenman/q2_bench/workflows/formallineage/model"
	"github.com/jeisenman/q2_bench/workflows/formallineage/source"
	"path"
	"strings"
)

// Dependency is an unevaluated declaration or one exact npm lock entry.
type Dependency struct {
	Kind                 string            `json:"kind"`
	Name                 string            `json:"name"`
	Version              string            `json:"version,omitempty"`
	Location             string            `json:"location,omitempty"`
	Condition            string            `json:"condition,omitempty"`
	Metadata             map[string]string `json:"metadata,omitempty"`
	Dependencies         map[string]string `json:"dependencies,omitempty"`
	OptionalDependencies map[string]string `json:"optional_dependencies,omitempty"`
	PeerDependencies     map[string]string `json:"peer_dependencies,omitempty"`
}

// DependencyFile binds package/build observations to immutable bytes.
type DependencyFile struct {
	Source      model.Source `json:"source"`
	SDK         string       `json:"sdk,omitempty"`
	Frameworks  []string     `json:"frameworks,omitempty"`
	LockVersion int          `json:"lock_version,omitempty"`
	Entries     []Dependency `json:"entries"`
}

// DependencyInventory records declarations and lockfile instances, not a restore.
type DependencyInventory struct {
	Format     string           `json:"format"`
	Repository string           `json:"repository"`
	Commit     string           `json:"commit"`
	Files      []DependencyFile `json:"files"`
	Summary    map[string]int   `json:"summary"`
	Unresolved []string         `json:"unresolved"`
	Complete   bool             `json:"complete"`
}

// InventoryDependencies reads every supported manifest at one pinned engine commit.
// MSBuild conditions are retained; NuGet resolution requires a separate restore.
func InventoryDependencies(ctx context.Context, root, commit string) (DependencyInventory, error) {
	paths, err := source.ListGit(ctx, root, commit)
	if err != nil {
		return DependencyInventory{}, err
	}
	result := DependencyInventory{Format: "q2-engine-dependency-inventory/v2", Repository: "pl-calculation-engine", Commit: commit, Files: []DependencyFile{}, Summary: map[string]int{}, Unresolved: []string{"MSBuild properties, imports, conditions and central/package versions are unevaluated.", "NuGet transitive closure requires authenticated restore and project.assets.json; no restore was performed.", "npm locks retain exact instances and declared outgoing edges, not install/runtime reachability.", "Package dependencies are separate from unbound method calls and dataset lineage."}}
	packages, npmDirect, npmLocked, npmNames := map[string]bool{}, map[string]bool{}, map[string]bool{}, map[string]bool{}
	total := 0
	for _, file := range paths {
		if err := ctx.Err(); err != nil {
			return DependencyInventory{}, err
		}
		base := path.Base(file)
		xmlFile := strings.HasSuffix(file, ".csproj") || strings.HasSuffix(file, ".proj") || strings.HasSuffix(file, ".props") || strings.HasSuffix(file, ".targets")
		if !xmlFile && base != "package.json" && base != "package-lock.json" && base != "global.json" && base != "NuGet.Config" && base != "nuget.config" {
			continue
		}
		if len(result.Files) >= 200 {
			return DependencyInventory{}, fmt.Errorf("dependency inventory exceeds 200 manifests")
		}
		b, err := source.ReadGit(ctx, root, commit, file, 16<<20)
		if err != nil {
			return DependencyInventory{}, err
		}
		total += len(b)
		if total > 64<<20 {
			return DependencyInventory{}, fmt.Errorf("dependency manifests exceed 64 MiB")
		}
		receipt, err := source.Receipt(commit, file, b)
		if err != nil {
			return DependencyInventory{}, err
		}
		f := DependencyFile{Source: receipt, Entries: []Dependency{}}
		switch {
		case xmlFile:
			err = parseBuild(b, &f)
		case base == "package.json":
			err = parsePackage(b, &f)
		case base == "package-lock.json":
			err = parseLock(b, &f)
		default:
			result.Unresolved = append(result.Unresolved, "Configuration retained by hash, not semantically evaluated: "+file)
		}
		if err != nil {
			return DependencyInventory{}, fmt.Errorf("parse %s: %w", file, err)
		}
		result.Files = append(result.Files, f)
		if strings.HasSuffix(file, ".csproj") {
			result.Summary["dotnet_projects"]++
		}
		for _, d := range f.Entries {
			switch d.Kind {
			case "PackageReference":
				result.Summary["nuget_declarations"]++
				packages[d.Name+"@"+d.Version] = true
			case "ProjectReference":
				result.Summary["project_references"]++
			case "dependencies", "devDependencies", "peerDependencies", "optionalDependencies":
				npmDirect[d.Name+"@"+d.Version] = true
				result.Summary["npm_direct_declarations"]++
			case "npm-lock":
				result.Summary["npm_locked_instances"]++
				npmLocked[d.Name+"@"+d.Version] = true
				npmNames[d.Name] = true
			}
		}
	}
	result.Summary["nuget_unique_direct"] = len(packages)
	result.Summary["npm_unique_direct"] = len(npmDirect)
	result.Summary["npm_unique_locked_versions"] = len(npmLocked)
	result.Summary["npm_unique_locked_names"] = len(npmNames)
	return result, nil
}
