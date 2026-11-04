package projects

import (
	"fmt"
	"path"
	"sort"
	"strconv"
	"strings"
)

// EnvironmentBinding records provider-observed runtime identity and private root.
// This local contract checks compatibility; it does not authenticate a provider.
type EnvironmentBinding struct {
	ProfileID   string            `json:"profile_id"`
	Platform    string            `json:"platform"`
	WorkspaceID string            `json:"workspace_id,omitempty"`
	IsolationID string            `json:"isolation_id"`
	Root        string            `json:"root"`
	Versions    map[string]string `json:"versions"`
}

// CheckEnvironmentBindings rejects cross-profile reuse and version mismatch.
// It never allocates compute, installs packages or runs application source.
func CheckEnvironmentBindings(bindings []EnvironmentBinding) error {
	if len(bindings) == 0 || len(bindings) > 16 {
		return fmt.Errorf("provide 1..16 environment bindings")
	}
	profiles := map[string]EnvironmentProfile{}
	for _, profile := range Environments() {
		profiles[profile.ID] = profile
	}
	seen := map[string]bool{}
	for i, b := range bindings {
		p, ok := profiles[b.ProfileID]
		if !ok {
			return fmt.Errorf("unknown environment profile %q", b.ProfileID)
		}
		if seen[b.ProfileID] {
			return fmt.Errorf("duplicate environment profile %q", b.ProfileID)
		}
		seen[b.ProfileID] = true
		if b.Platform != p.Platform || b.WorkspaceID != p.WorkspaceID {
			return fmt.Errorf("%s requires platform %s and workspace %s", p.ID, p.Platform, p.WorkspaceID)
		}
		if strings.TrimSpace(b.IsolationID) == "" || len(b.IsolationID) > 256 {
			return fmt.Errorf("%s requires a bounded provider compute/process isolation ID", p.ID)
		}
		if !path.IsAbs(b.Root) || path.Clean(b.Root) != b.Root || b.Root == "/" || strings.ContainsAny(b.Root, "\x00\n\r\\") {
			return fmt.Errorf("%s requires a canonical absolute private environment root", p.ID)
		}
		names := make([]string, 0, len(p.Versions))
		for name := range p.Versions {
			names = append(names, name)
		}
		sort.Strings(names)
		for _, name := range names {
			required := p.Versions[name]
			if required == "unresolved" {
				return fmt.Errorf("%s %s runtime is unresolved", p.ID, name)
			}
			if !versionMatches(b.Versions[name], required) {
				return fmt.Errorf("%s requires %s %s; observed %q", p.ID, name, required, b.Versions[name])
			}
		}
		for _, prior := range bindings[:i] {
			if prior.Platform == b.Platform && prior.WorkspaceID == b.WorkspaceID && prior.IsolationID == b.IsolationID {
				return fmt.Errorf("%s and %s reuse compute/process isolation %q", prior.ProfileID, b.ProfileID, b.IsolationID)
			}
			if overlaps(prior.Root, b.Root) {
				return fmt.Errorf("%s and %s share or nest environment roots", prior.ProfileID, b.ProfileID)
			}
		}
	}
	return nil
}

func versionMatches(actual, required string) bool {
	for _, c := range actual {
		if (c < '0' || c > '9') && c != '.' {
			return false
		}
	}
	parts := strings.Split(actual, ".")
	if len(parts) != 3 {
		return false
	}
	for _, p := range parts {
		if p == "" {
			return false
		}
	}
	// '+' permits SDK feature-band roll-forward within the pinned major/minor.
	if strings.HasSuffix(required, "+") {
		minimum := strings.Split(strings.TrimSuffix(required, "+"), ".")
		if len(minimum) != 3 || parts[0] != minimum[0] || parts[1] != minimum[1] {
			return false
		}
		patch, err := strconv.Atoi(parts[2])
		floor, floorErr := strconv.Atoi(minimum[2])
		return err == nil && floorErr == nil && patch >= floor
	}
	if strings.HasSuffix(required, ".x") {
		return strings.HasPrefix(actual, strings.TrimSuffix(required, "x"))
	}
	return actual == required
}

func overlaps(a, b string) bool {
	return a == b || strings.HasPrefix(a, b+"/") || strings.HasPrefix(b, a+"/")
}

// EnvironmentVariables returns private cache/install locations for one binding.
// Callers must launch a fresh process with a reviewed environment allowlist;
// setting these variables in a shared Databricks kernel is not compute isolation.
func EnvironmentVariables(binding EnvironmentBinding) (map[string]string, error) {
	if err := CheckEnvironmentBindings([]EnvironmentBinding{binding}); err != nil {
		return nil, err
	}
	root := binding.Root
	result := map[string]string{"TMPDIR": root + "/tmp"}
	switch binding.Platform {
	case "native-dotnet":
		result["DOTNET_CLI_HOME"] = root + "/dotnet-home"
		result["NUGET_PACKAGES"] = root + "/nuget-packages"
		result["NUGET_HTTP_CACHE_PATH"] = root + "/nuget-http-cache"
		result["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1"
	case "native-node":
		result["npm_config_cache"] = root + "/npm-cache"
		result["npm_config_userconfig"] = root + "/npmrc"
	case "ra":
		result["UV_PROJECT_ENVIRONMENT"] = root + "/.venv"
		result["UV_CACHE_DIR"] = root + "/uv-cache"
		result["PIP_CACHE_DIR"] = root + "/pip-cache"
		result["PYTHONNOUSERSITE"] = "1"
	}
	return result, nil
}
