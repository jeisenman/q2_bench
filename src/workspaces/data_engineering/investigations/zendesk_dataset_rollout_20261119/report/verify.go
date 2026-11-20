package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
)

func digest(b []byte) string { h := sha256.Sum256(b); return hex.EncodeToString(h[:]) }
func decode(b []byte, v any) error {
	d := json.NewDecoder(bytes.NewReader(b))
	d.UseNumber()
	if err := d.Decode(v); err != nil {
		return err
	}
	var extra any
	if err := d.Decode(&extra); err != io.EOF {
		return fmt.Errorf("JSON has trailing content")
	}
	return nil
}
func readJSON(path string, v any) ([]byte, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	return b, decode(b, v)
}
func artifactPath(root, relative string) (string, error) {
	if relative == "" || filepath.IsAbs(relative) {
		return "", fmt.Errorf("artifact path must be relative")
	}
	joined := filepath.Join(root, filepath.FromSlash(relative))
	rel, err := filepath.Rel(root, joined)
	if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(os.PathSeparator)) {
		return "", fmt.Errorf("artifact path escapes run")
	}
	resolved, err := filepath.EvalSymlinks(joined)
	if err != nil {
		return "", err
	}
	resolvedRoot, err := filepath.EvalSymlinks(root)
	if err != nil {
		return "", err
	}
	rel, err = filepath.Rel(resolvedRoot, resolved)
	if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(os.PathSeparator)) {
		return "", fmt.Errorf("artifact symlink escapes run")
	}
	return joined, nil
}
func pinned(root string, p pin) ([]byte, error) {
	path, err := artifactPath(root, p.Path)
	if err != nil {
		return nil, err
	}
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	if digest(b) != p.SHA256 {
		return nil, fmt.Errorf("artifact hash mismatch: %s", p.Path)
	}
	return b, nil
}
func parseDefinition(b []byte, id string) (definition, error) {
	var fields map[string]json.RawMessage
	if err := decode(b, &fields); err != nil {
		return definition{}, err
	}
	if len(fields) != 3 {
		return definition{}, fmt.Errorf("definition must have exactly three string keys")
	}
	for _, key := range []string{"description", "business_context", "node_id"} {
		var value string
		raw, ok := fields[key]
		if !ok || decode(raw, &value) != nil || string(raw) == "null" {
			return definition{}, fmt.Errorf("definition key %s must be text", key)
		}
	}
	var d definition
	if err := decode(b, &d); err != nil {
		return d, err
	}
	if d.NodeID != id {
		return d, fmt.Errorf("definition identity mismatch: %s", id)
	}
	if strings.TrimSpace(d.Description) == "" || strings.TrimSpace(d.BusinessContext) == "" {
		return d, fmt.Errorf("definition text is empty")
	}
	return d, nil
}

func verifyManifest(root string, m manifest, count int) ([]byte, error) {
	if m.SelectedCount != count || len(m.Targets) != count || m.Generation != generation || m.Prompt.Version != "2.0.0" || m.Prompt.SHA256 != promptSHA || m.CallerPolicy.Version != "single-luna-audit-cleanup/1" || m.CallerPolicy.SHA256 != policySHA {
		return nil, fmt.Errorf("manifest scope, generation or policy differs from rollout")
	}
	if m.Sources["graph"].SHA256 != "f5211952368deddeacc47ab989ef6ed8305fd67831ae495a7c4f98bd32ff06f0" || m.Sources["requests"].SHA256 != "3fab405cfee4b55e458bb98810625fddb2228a9496e7ba503ed8c31b77d777f8" {
		return nil, fmt.Errorf("frozen graph or published request root pin differs from selected rollout")
	}
	prompt, err := pinned(root, pin{m.Prompt.Path, m.Prompt.SHA256})
	if err != nil {
		return nil, err
	}
	caller, err := pinned(root, pin{m.CallerPolicy.Path, m.CallerPolicy.SHA256})
	if err != nil {
		return nil, err
	}
	for _, p := range m.Sources {
		if _, err := pinned(root, p); err != nil {
			return nil, err
		}
	}
	for _, p := range []pin{{m.Projection.Path, m.Projection.SHA256}, m.ModelCapacity, m.CapacityObservation} {
		if _, err := pinned(root, p); err != nil {
			return nil, err
		}
	}
	seen := map[string]bool{}
	for _, t := range m.Targets {
		if seen[t.NodeID] || !strings.HasPrefix(t.NodeID, "dataset:") || t.ArtifactID != digest([]byte(t.NodeID)) || t.Directory != "nodes/"+t.ArtifactID {
			return nil, fmt.Errorf("duplicate or malformed target identity %s", t.NodeID)
		}
		seen[t.NodeID] = true
		for _, name := range []string{"input", "before", "prepared", "target", "retrieval", "preparation", "original-request", "original-response"} {
			p, ok := t.Files[name]
			if !ok || p.Path != t.Directory+"/"+name+".json" {
				return nil, fmt.Errorf("missing or mismatched %s pin for %s", name, t.NodeID)
			}
			if _, err := pinned(root, p); err != nil {
				return nil, err
			}
		}
	}
	return append(append(prompt, []byte("\n\n## Explicit caller cleanup policy\n\n")...), caller...), nil
}
