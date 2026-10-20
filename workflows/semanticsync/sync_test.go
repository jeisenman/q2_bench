package semanticsync

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestSyncDecoratesCompleteGraphAndWritesAtomically(t *testing.T) {
	root, generation := semanticFixture(t, false)
	inputs, err := InputsForGeneration(root, generation)
	if err != nil {
		t.Fatal(err)
	}
	output := filepath.Join(t.TempDir(), "lineage", "semantic.json")
	receipt, err := Sync(inputs, output, false)
	if err != nil {
		t.Fatal(err)
	}
	if receipt.NodeCount != 1 || receipt.DryRun {
		t.Fatalf("receipt = %#v", receipt)
	}
	content, err := os.ReadFile(output)
	if err != nil {
		t.Fatal(err)
	}
	var document outputDocument
	if err := json.Unmarshal(content, &document); err != nil {
		t.Fatal(err)
	}
	facets := document.Nodes[0]["facets"].(map[string]any)
	meaning := facets[semanticFacetName].(map[string]any)
	if meaning["status"] != "available" {
		t.Fatalf("meaning = %#v", meaning)
	}
	metadata := document.Manifest["semanticLayer"].(map[string]any)
	if metadata["bundleId"] != "11111111-1111-1111-1111-111111111111" {
		t.Fatalf("semantic metadata = %#v", metadata)
	}
}

func TestSyncRejectsIncompleteSemanticCoverage(t *testing.T) {
	root, generation := semanticFixture(t, true)
	inputs, err := InputsForGeneration(root, generation)
	if err != nil {
		t.Fatal(err)
	}
	_, err = Sync(inputs, filepath.Join(t.TempDir(), "output.json"), true)
	if err == nil || !strings.Contains(err.Error(), "lacks complete semantic meaning") {
		t.Fatalf("error = %v", err)
	}
}

func TestDiscoverLatestSelectsNewestCompleteGeneration(t *testing.T) {
	root, older := semanticFixture(t, false)
	newer := filepath.Join(root, "runs", "lineage", "generations", "newer")
	if err := os.MkdirAll(newer, 0o755); err != nil {
		t.Fatal(err)
	}
	copyFile(t, filepath.Join(older, "responses.jsonl"), filepath.Join(newer, "responses.jsonl"))
	writeFile(t, filepath.Join(newer, "manifest.json"), strings.ReplaceAll(
		generationJSON,
		`"2026-10-16T18:35:09Z"`,
		`"2026-10-17T18:35:09Z"`,
	))
	inputs, err := DiscoverLatest(root)
	if err != nil {
		t.Fatal(err)
	}
	if filepath.Dir(inputs.GenerationManifestPath) != newer {
		t.Fatalf("generation = %s, want %s", filepath.Dir(inputs.GenerationManifestPath), newer)
	}
}

func semanticFixture(t *testing.T, missingResponse bool) (string, string) {
	t.Helper()
	root := t.TempDir()
	bundleID := "11111111-1111-1111-1111-111111111111"
	generation := filepath.Join(root, "runs", "lineage", "generations", "generation")
	response := `{"business_context":"Used by portfolio reporting.","description":"Prepared delivery data.","node_id":"dataset:delivery"}` + "\n"
	if missingResponse {
		response = `{"business_context":"Other.","description":"Other.","node_id":"dataset:other"}` + "\n"
	}
	writeFile(t, filepath.Join(generation, "responses.jsonl"), response)
	request := `{"requestId":"request","bundleId":"11111111-1111-1111-1111-111111111111","nodeId":"dataset:delivery","lineageNodeKey":"node-key","promptVersion":"prompt-v1","promptSha256":"prompt-sha","prompt":"prompt","evidenceSha256":"evidence-sha","evidence":{}}` + "\n"
	writeFile(t, filepath.Join(root, "runs", "lineage", "semantic", bundleID, "requests.jsonl"), request)
	requestDigest := fmt.Sprintf("%x", sha256.Sum256([]byte(request)))
	writeFile(
		t,
		filepath.Join(generation, "manifest.json"),
		strings.ReplaceAll(generationJSON, "REQUESTS_SHA256", requestDigest),
	)
	writeFile(
		t,
		filepath.Join(root, "runs", "lineage", "graphs", bundleID, "bundle.json"),
		`{"bundleId":"11111111-1111-1111-1111-111111111111","format":"research-system-openlineage-bundle/v2","generatedAt":"2026-10-16T17:08:17Z","logicalGraph":{"format":"q2-openlineage-graph/v2","fingerprint":"fingerprint","manifest":{"graphId":"graph"},"nodes":[{"id":"dataset:delivery","kind":"dataset","name":"delivery","facets":{}}],"edges":[]},"logicalGroups":[],"rawGraph":{},"schemaDefinitionCount":0,"sourceManifest":{}}`,
	)
	return root, generation
}

const generationJSON = `{
  "bundle_id": "11111111-1111-1111-1111-111111111111",
  "created_at": "2026-10-16T18:35:09Z",
  "effort": "medium",
  "generation_id": "22222222-2222-2222-2222-222222222222",
  "model": "openai.test",
  "request_count": 1,
  "requests_sha256": "REQUESTS_SHA256",
  "runtime_configuration_sha256": "runtime-sha",
  "schema_version": "1.0"
}`

func writeFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
}

func copyFile(t *testing.T, source, target string) {
	t.Helper()
	content, err := os.ReadFile(source)
	if err != nil {
		t.Fatal(err)
	}
	writeFile(t, target, string(content))
}
