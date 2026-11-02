package lineagecheck

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os/exec"
	"sort"
	"strconv"
	"strings"
	"time"
)

const snapshotFormat = "q2-lineage-snapshot/v1"
const extractorVersion = "q2-reviewed-contracts-literal-schema/v1"

// Build verifies source evidence at pinned commits and materializes schemas.
// Checkout roots are caller-supplied and are never embedded in the artifact.
func Build(ctx context.Context, manifest Manifest, roots map[string]string) (Snapshot, error) {
	if err := ctx.Err(); err != nil {
		return Snapshot{}, err
	}
	content, err := json.Marshal(manifest)
	if err != nil {
		return Snapshot{}, err
	}
	var m Manifest
	if err := Decode(content, &m); err != nil {
		return Snapshot{}, err
	}
	commits := map[string]string{}
	for _, r := range m.Repositories {
		if !commitPattern.MatchString(r.Commit) || r.Name == "" || commits[r.Name] != "" {
			return Snapshot{}, fmt.Errorf("repository %q needs a unique name and full commit", r.Name)
		}
		if roots[r.Name] == "" {
			return Snapshot{}, fmt.Errorf("provide checkout root for repository %s", r.Name)
		}
		commits[r.Name] = r.Commit
	}
	cache := map[Evidence][]byte{}
	read := func(e Evidence) ([]byte, error) {
		if b, ok := cache[e]; ok {
			return b, nil
		}
		repos := map[string]bool{}
		for name := range commits {
			repos[name] = true
		}
		if err := validateEvidence([]Evidence{e}, repos); err != nil {
			return nil, err
		}
		object := commits[e.Repository] + ":" + e.Path
		b, err := gitBlob(ctx, roots[e.Repository], object)
		if err != nil {
			return nil, err
		}
		if digest(b) != e.SHA256 {
			return nil, fmt.Errorf("source evidence changed for %s:%s at %s; review the source and update its contract and SHA256", e.Repository, e.Path, commits[e.Repository])
		}
		cache[e] = b
		return b, nil
	}
	for i := range m.Datasets {
		d := &m.Datasets[i]
		for _, e := range d.Evidence {
			if _, err := read(e); err != nil {
				return Snapshot{}, err
			}
		}
		if d.Schema != nil {
			b, err := read(d.Schema.Evidence)
			if err != nil {
				return Snapshot{}, err
			}
			fields, err := ExtractSchema(b, d.Schema.Class, d.Schema.Major)
			if err != nil {
				return Snapshot{}, fmt.Errorf("dataset %s: %w", d.ID, err)
			}
			// Explicit fields supplement source schemas, e.g. writer-added DatePartition.
			d.Fields = append(fields, d.Fields...)
		}
	}
	for _, j := range m.Jobs {
		for _, e := range j.Evidence {
			if _, err := read(e); err != nil {
				return Snapshot{}, err
			}
		}
	}
	if err := Validate(m); err != nil {
		return Snapshot{}, err
	}
	canonicalize(&m)
	s := Snapshot{Format: snapshotFormat, Extractor: extractorVersion, Manifest: m}
	s.ID = snapshotID(s)
	return s, nil
}

func gitBlob(ctx context.Context, root, object string) ([]byte, error) {
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	size, err := exec.CommandContext(ctx, "git", "-C", root, "cat-file", "-s", object).Output()
	if err != nil {
		return nil, fmt.Errorf("read pinned source %s: %w", object, err)
	}
	n, err := strconv.Atoi(strings.TrimSpace(string(size)))
	if err != nil || n < 0 || n > maxDocumentBytes {
		return nil, fmt.Errorf("source %s exceeds lineage source size limit", object)
	}
	b, err := exec.CommandContext(ctx, "git", "-C", root, "cat-file", "blob", object).Output()
	if err != nil {
		return nil, fmt.Errorf("read pinned source %s: %w", object, err)
	}
	return b, nil
}

func digest(b []byte) string { sum := sha256.Sum256(b); return hex.EncodeToString(sum[:]) }

func snapshotID(s Snapshot) string {
	s.ID = ""
	b, _ := json.Marshal(s)
	return digest(b)
}

// ValidateSnapshot checks the content digest and all structural contracts.
func ValidateSnapshot(s Snapshot) error {
	if s.Format != snapshotFormat || s.Extractor != extractorVersion || s.ID != snapshotID(s) {
		return fmt.Errorf("unsupported or corrupt lineage snapshot %q", s.ID)
	}
	return Validate(s.Manifest)
}

func canonicalize(m *Manifest) {
	sort.Slice(m.Repositories, func(i, j int) bool { return m.Repositories[i].Name < m.Repositories[j].Name })
	sort.Slice(m.Datasets, func(i, j int) bool { return m.Datasets[i].ID < m.Datasets[j].ID })
	sort.Slice(m.Jobs, func(i, j int) bool { return m.Jobs[i].ID < m.Jobs[j].ID })
	sort.Strings(m.Unresolved)
	for i := range m.Datasets {
		d := &m.Datasets[i]
		sort.Slice(d.Fields, func(i, j int) bool { return d.Fields[i].Name < d.Fields[j].Name })
		sort.Strings(d.Keys)
		sortEvidence(d.Evidence)
	}
	for i := range m.Jobs {
		j := &m.Jobs[i]
		sort.Strings(j.Outputs)
		sort.Strings(j.After)
		sortEvidence(j.Evidence)
		sort.Slice(j.Inputs, func(a, b int) bool { return j.Inputs[a].Dataset < j.Inputs[b].Dataset })
		for k := range j.Inputs {
			sort.Strings(j.Inputs[k].Fields)
			sort.Strings(j.Inputs[k].Keys)
		}
		sort.Slice(j.Dependencies, func(a, b int) bool { return refKey(j.Dependencies[a].Output) < refKey(j.Dependencies[b].Output) })
		for k := range j.Dependencies {
			sort.Slice(j.Dependencies[k].Inputs, func(a, b int) bool { return refKey(j.Dependencies[k].Inputs[a]) < refKey(j.Dependencies[k].Inputs[b]) })
		}
	}
}

func refKey(r FieldRef) string { return r.Dataset + "\x00" + r.Field }
func sortEvidence(e []Evidence) {
	sort.Slice(e, func(i, j int) bool {
		return e[i].Repository+"/"+e[i].Path+e[i].SHA256 < e[j].Repository+"/"+e[j].Path+e[j].SHA256
	})
}
