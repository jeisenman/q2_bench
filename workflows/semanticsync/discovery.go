package semanticsync

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// Inputs identifies one complete, published Researcher semantic generation.
type Inputs struct {
	BundlePath             string
	RequestsPath           string
	ResponsesPath          string
	GenerationManifestPath string
}

// DiscoverLatest selects the newest complete generation below a Researcher checkout.
func DiscoverLatest(researcherRoot string) (Inputs, error) {
	root := strings.TrimSpace(researcherRoot)
	if root == "" {
		return Inputs{}, fmt.Errorf("researcher root must not be empty")
	}
	pattern := filepath.Join(filepath.Clean(root), "runs", "lineage", "generations", "*", "manifest.json")
	paths, err := filepath.Glob(pattern)
	if err != nil {
		return Inputs{}, fmt.Errorf("discover Researcher semantic generations: %w", err)
	}
	type candidate struct {
		inputs   Inputs
		manifest generationManifest
	}
	candidates := make([]candidate, 0, len(paths))
	for _, path := range paths {
		manifest, loadErr := loadGenerationManifest(path)
		if loadErr != nil {
			return Inputs{}, loadErr
		}
		inputs := pathsForGeneration(filepath.Clean(root), filepath.Dir(path), manifest.BundleID)
		if complete(inputs) {
			candidates = append(candidates, candidate{inputs: inputs, manifest: manifest})
		}
	}
	if len(candidates) == 0 {
		return Inputs{}, fmt.Errorf("no complete Researcher semantic generation found below %s", root)
	}
	sort.Slice(candidates, func(i, j int) bool {
		left, right := candidates[i].manifest, candidates[j].manifest
		if !left.CreatedAt.Equal(right.CreatedAt) {
			return left.CreatedAt.After(right.CreatedAt)
		}
		return left.GenerationID > right.GenerationID
	})
	return candidates[0].inputs, nil
}

// InputsForGeneration resolves one explicitly selected generation directory.
func InputsForGeneration(researcherRoot, generationDirectory string) (Inputs, error) {
	root := strings.TrimSpace(researcherRoot)
	directory := strings.TrimSpace(generationDirectory)
	if root == "" || directory == "" {
		return Inputs{}, fmt.Errorf("researcher root and generation directory must not be empty")
	}
	manifestPath := filepath.Join(filepath.Clean(directory), "manifest.json")
	manifest, err := loadGenerationManifest(manifestPath)
	if err != nil {
		return Inputs{}, err
	}
	inputs := pathsForGeneration(filepath.Clean(root), filepath.Clean(directory), manifest.BundleID)
	if !complete(inputs) {
		return Inputs{}, fmt.Errorf("Researcher semantic generation is incomplete: %s", directory)
	}
	return inputs, nil
}

func pathsForGeneration(root, generationDirectory, bundleID string) Inputs {
	return Inputs{
		BundlePath:             filepath.Join(root, "runs", "lineage", "graphs", bundleID, "bundle.json"),
		RequestsPath:           filepath.Join(root, "runs", "lineage", "semantic", bundleID, "requests.jsonl"),
		ResponsesPath:          filepath.Join(generationDirectory, "responses.jsonl"),
		GenerationManifestPath: filepath.Join(generationDirectory, "manifest.json"),
	}
}

func complete(inputs Inputs) bool {
	for _, path := range []string{
		inputs.BundlePath,
		inputs.RequestsPath,
		inputs.ResponsesPath,
		inputs.GenerationManifestPath,
	} {
		info, err := os.Stat(path)
		if err != nil || !info.Mode().IsRegular() {
			return false
		}
	}
	return true
}

func loadGenerationManifest(path string) (generationManifest, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return generationManifest{}, fmt.Errorf("read generation manifest %s: %w", path, err)
	}
	var manifest generationManifest
	if err := decodeStrict(content, &manifest); err != nil {
		return generationManifest{}, fmt.Errorf("decode generation manifest %s: %w", path, err)
	}
	if manifest.SchemaVersion != "1.0" {
		return generationManifest{}, fmt.Errorf(
			"generation manifest %s has unsupported schema version %q",
			path,
			manifest.SchemaVersion,
		)
	}
	if manifest.BundleID == "" || manifest.GenerationID == "" || manifest.Model == "" ||
		manifest.RequestCount < 1 || manifest.CreatedAt.IsZero() {
		return generationManifest{}, fmt.Errorf("generation manifest %s is incomplete", path)
	}
	return manifest, nil
}

func decodeStrict(content []byte, target any) error {
	decoder := json.NewDecoder(bytes.NewReader(content))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		if err == nil {
			return fmt.Errorf("document contains trailing JSON values")
		}
		return err
	}
	return nil
}
