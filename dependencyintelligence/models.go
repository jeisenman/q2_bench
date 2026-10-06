// Package dependencyintelligence contains package-release contracts.
package dependencyintelligence

import (
	"context"
	"fmt"
	"strings"
	"time"
)

const maxChangeMarkers = 20

// PackageRelease describes one package release and reported changes.
type PackageRelease struct {
	Package        string
	Version        string
	RequiresPython string
	Yanked         bool
	PublishedAt    *time.Time
	ChangeMarkers  []string
}

// Validate checks package identity and bounded marker content.
func (r PackageRelease) Validate() error {
	if strings.TrimSpace(r.Package) == "" {
		return fmt.Errorf("package must not be empty")
	}
	if strings.TrimSpace(r.Version) == "" {
		return fmt.Errorf("version must not be empty")
	}
	if r.RequiresPython != "" && strings.TrimSpace(r.RequiresPython) == "" {
		return fmt.Errorf("requires_python must not be empty")
	}
	if len(r.ChangeMarkers) > maxChangeMarkers {
		return fmt.Errorf("change_markers must contain at most 20 entries")
	}
	return nil
}

// PackageCompatibility reports declared Python-version compatibility.
type PackageCompatibility struct {
	Package        string
	Version        string
	PythonVersion  string
	RequiresPython string
	Compatible     *bool
}

// Validate checks compatibility identity fields.
func (c PackageCompatibility) Validate() error {
	for name, value := range map[string]string{
		"package": c.Package, "version": c.Version, "python_version": c.PythonVersion,
	} {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("%s must not be empty", name)
		}
	}
	return nil
}

// DependencyChangeReport contains releases across one version range.
type DependencyChangeReport struct {
	Package     string
	FromVersion string
	ToVersion   string
	Releases    []PackageRelease
}

// Validate checks report identity and package consistency.
func (r DependencyChangeReport) Validate() error {
	for name, value := range map[string]string{
		"package": r.Package, "from_version": r.FromVersion, "to_version": r.ToVersion,
	} {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("%s must not be empty", name)
		}
	}
	for _, release := range r.Releases {
		if release.Package != r.Package {
			return fmt.Errorf("dependency change releases must match the report package")
		}
	}
	return nil
}

// Source reads package releases, compatibility, and reported changes.
type Source interface {
	ListReleases(context.Context, string, bool, int) ([]PackageRelease, error)
	CheckCompatibility(context.Context, string, string, string) (PackageCompatibility, error)
	ListChanges(context.Context, string, string, string) (DependencyChangeReport, error)
}
