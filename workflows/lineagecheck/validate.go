package lineagecheck

import (
	"bytes"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"path"
	"regexp"
	"sort"
	"strings"
)

const maxDocumentBytes = 16 << 20

var commitPattern = regexp.MustCompile(`^[a-f0-9]{40}$`)

// Decode reads one bounded contract document and rejects unknown JSON fields.
func Decode(content []byte, target any) error {
	if len(content) > maxDocumentBytes {
		return fmt.Errorf("lineage document exceeds %d bytes", maxDocumentBytes)
	}
	d := json.NewDecoder(bytes.NewReader(content))
	d.DisallowUnknownFields()
	if err := d.Decode(target); err != nil {
		return fmt.Errorf("decode lineage document: %w", err)
	}
	if err := d.Decode(new(any)); err != io.EOF {
		return fmt.Errorf("lineage document must contain exactly one JSON value")
	}
	return nil
}

// Validate checks references, versions, evidence, and dependency coverage.
func Validate(m Manifest) error {
	if len(m.Datasets) > 1000 || len(m.Jobs) > 500 || len(m.Repositories) > 32 || len(m.Unresolved) > 1000 {
		return fmt.Errorf("lineage scope exceeds limits: 1000 datasets, 500 jobs, 32 repositories, 1000 unresolved findings")
	}
	if m.Format != Format || strings.TrimSpace(m.Scope) == "" || strings.TrimSpace(m.Profile) == "" {
		return fmt.Errorf("manifest requires format %s, scope, and profile", Format)
	}
	repos := map[string]bool{}
	for _, r := range m.Repositories {
		if r.Name == "" || repos[r.Name] || !commitPattern.MatchString(r.Commit) {
			return fmt.Errorf("repository %q needs a unique name and full lowercase Git commit", r.Name)
		}
		repos[r.Name] = true
	}
	if len(repos) == 0 || len(m.Datasets) == 0 {
		return fmt.Errorf("manifest requires source repositories and datasets")
	}
	datasets := map[string]Dataset{}
	for _, d := range m.Datasets {
		if len(d.Fields) > 1000 || len(d.Evidence) > 100 {
			return fmt.Errorf("dataset %s exceeds field/evidence limits", d.ID)
		}
		if d.ID == "" || datasets[d.ID].ID != "" || d.Major < 1 || d.Minor < 0 {
			return fmt.Errorf("dataset %q has invalid identity or version", d.ID)
		}
		fields := map[string]bool{}
		for _, f := range d.Fields {
			if f.Name == "" || f.Type == "" || fields[f.Name] {
				return fmt.Errorf("dataset %s has invalid or duplicate field %q", d.ID, f.Name)
			}
			fields[f.Name] = true
		}
		if len(fields) == 0 {
			return fmt.Errorf("dataset %s has no resolved schema", d.ID)
		}
		for _, f := range append(append([]string{}, d.Keys...), d.Partition) {
			if f != "" && !fields[f] {
				return fmt.Errorf("dataset %s references missing key/partition %s", d.ID, f)
			}
		}
		if err := unique(d.Keys); err != nil {
			return fmt.Errorf("dataset %s keys: %w", d.ID, err)
		}
		if err := validateEvidence(d.Evidence, repos); err != nil {
			return fmt.Errorf("dataset %s: %w", d.ID, err)
		}
		if d.Schema != nil {
			if d.Schema.Class == "" || d.Schema.Major != d.Major {
				return fmt.Errorf("dataset %s schema class/version is invalid", d.ID)
			}
			if err := validateEvidence([]Evidence{d.Schema.Evidence}, repos); err != nil {
				return err
			}
		}
		datasets[d.ID] = d
	}
	jobs := map[string]Job{}
	for _, j := range m.Jobs {
		if datasets[j.ID].ID != "" || len(j.Inputs) > 100 || len(j.Dependencies) > 10000 || len(j.Evidence) > 100 {
			return fmt.Errorf("job %s collides with a dataset or exceeds input/dependency/evidence limits", j.ID)
		}
		if j.ID == "" || j.DAG == "" || jobs[j.ID].ID != "" {
			return fmt.Errorf("job %q requires unique identity and DAG", j.ID)
		}
		if err := validateEvidence(j.Evidence, repos); err != nil {
			return fmt.Errorf("job %s: %w", j.ID, err)
		}
		if err := validateReplay(j.Replay); err != nil {
			return fmt.Errorf("job %s: %w", j.ID, err)
		}
		if err := unique(j.Outputs); err != nil || len(j.Outputs) == 0 {
			return fmt.Errorf("job %s requires unique outputs", j.ID)
		}
		inputs := map[string]Input{}
		for _, in := range j.Inputs {
			d, ok := datasets[in.Dataset]
			if !ok || in.Major != d.Major || inputs[in.Dataset].Dataset != "" {
				return fmt.Errorf("job %s input %s is missing, duplicated, or has an incompatible major version", j.ID, in.Dataset)
			}
			if len(in.Fields) == 0 {
				return fmt.Errorf("job %s input %s has no consumed fields", j.ID, in.Dataset)
			}
			if err := unique(in.Fields); err != nil {
				return err
			}
			if err := unique(in.Keys); err != nil {
				return err
			}
			for _, f := range append(append([]string{}, in.Fields...), in.Keys...) {
				if _, ok := field(d, f); !ok {
					return fmt.Errorf("job %s input %s is missing consumed column %s", j.ID, in.Dataset, f)
				}
			}
			inputs[in.Dataset] = in
		}
		for _, id := range j.Outputs {
			if datasets[id].ID == "" {
				return fmt.Errorf("job %s output %s is missing", j.ID, id)
			}
		}
		covered := map[FieldRef]bool{}
		for _, dep := range j.Dependencies {
			if !contains(j.Outputs, dep.Output.Dataset) {
				return fmt.Errorf("job %s dependency references a non-output", j.ID)
			}
			if _, ok := field(datasets[dep.Output.Dataset], dep.Output.Field); !ok || covered[dep.Output] {
				return fmt.Errorf("job %s dependency output is missing or duplicated", j.ID)
			}
			covered[dep.Output] = true
			for _, ref := range dep.Inputs {
				in, ok := inputs[ref.Dataset]
				if !ok || (!contains(in.Fields, ref.Field) && !contains(in.Keys, ref.Field)) {
					return fmt.Errorf("job %s dependency references an undeclared input column %s.%s", j.ID, ref.Dataset, ref.Field)
				}
			}
		}
		if j.ColumnsComplete {
			for _, id := range j.Outputs {
				for _, f := range datasets[id].Fields {
					if !covered[FieldRef{id, f.Name}] {
						return fmt.Errorf("job %s claims complete columns but omits %s.%s", j.ID, id, f.Name)
					}
				}
			}
		}
		jobs[j.ID] = j
	}
	for _, j := range m.Jobs {
		if err := unique(j.After); err != nil {
			return err
		}
		for _, id := range j.After {
			if jobs[id].ID == "" || id == j.ID {
				return fmt.Errorf("job %s has an invalid predecessor %s", j.ID, id)
			}
		}
	}
	return acyclic(jobs)
}

func validateEvidence(items []Evidence, repos map[string]bool) error {
	if len(items) == 0 {
		return fmt.Errorf("source evidence is required")
	}
	for _, e := range items {
		decoded, err := hex.DecodeString(e.SHA256)
		if !repos[e.Repository] || e.Path == "" || path.IsAbs(e.Path) || path.Clean(e.Path) != e.Path || e.Path == ".." || strings.HasPrefix(e.Path, "../") || strings.Contains(e.Path, "\\") || err != nil || len(decoded) != 32 {
			return fmt.Errorf("invalid source evidence %s:%s; require repository, relative path, and SHA256", e.Repository, e.Path)
		}
	}
	return nil
}

func validateReplay(r Replay) error {
	if !contains([]string{"partition", "window", "month_end", "cross_client"}, r.Mode) || r.HourUTC < 0 || r.HourUTC > 23 || r.WriteMode != "replace" || !contains([]string{"single_client", "cross_client"}, r.ClientScope) {
		return fmt.Errorf("replay requires a supported mode, UTC hour 0..23, replace writes, and client scope")
	}
	if r.Mode == "cross_client" && r.ClientScope != "cross_client" {
		return fmt.Errorf("cross-client replay mode requires cross-client scope")
	}
	return nil
}

func field(d Dataset, name string) (Field, bool) {
	for _, f := range d.Fields {
		if f.Name == name {
			return f, true
		}
	}
	return Field{}, false
}

func contains(items []string, value string) bool {
	for _, item := range items {
		if item == value {
			return true
		}
	}
	return false
}

func unique(items []string) error {
	seen := map[string]bool{}
	for _, item := range items {
		if item == "" || seen[item] {
			return fmt.Errorf("empty or duplicate value %q", item)
		}
		seen[item] = true
	}
	return nil
}

func acyclic(jobs map[string]Job) error {
	state := map[string]int{}
	var visit func(string) error
	visit = func(id string) error {
		if state[id] == 1 {
			return fmt.Errorf("job ordering cycle at %s", id)
		}
		if state[id] == 2 {
			return nil
		}
		state[id] = 1
		for _, p := range jobs[id].After {
			if err := visit(p); err != nil {
				return err
			}
		}
		state[id] = 2
		return nil
	}
	ids := make([]string, 0, len(jobs))
	for id := range jobs {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	for _, id := range ids {
		if err := visit(id); err != nil {
			return err
		}
	}
	return nil
}
