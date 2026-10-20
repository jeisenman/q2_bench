package semanticsync

import (
	"bufio"
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/google/uuid"
)

const maxJSONLRowBytes = 16 << 20

// Sync validates and stages one complete Researcher Semantic Layer snapshot.
func Sync(inputs Inputs, outputPath string, dryRun bool) (Receipt, error) {
	manifest, err := loadGenerationManifest(inputs.GenerationManifestPath)
	if err != nil {
		return Receipt{}, err
	}
	bundle, err := loadBundle(inputs.BundlePath)
	if err != nil {
		return Receipt{}, err
	}
	if manifest.BundleID != bundle.BundleID {
		return Receipt{}, fmt.Errorf("generation bundle %s does not match bundle %s", manifest.BundleID, bundle.BundleID)
	}
	if err := verifyFileSHA256(inputs.RequestsPath, manifest.RequestsSHA256); err != nil {
		return Receipt{}, err
	}
	requests, err := loadRequests(inputs.RequestsPath, bundle.BundleID)
	if err != nil {
		return Receipt{}, err
	}
	responses, err := loadResponses(inputs.ResponsesPath)
	if err != nil {
		return Receipt{}, err
	}
	if len(requests) != manifest.RequestCount || len(responses) != manifest.RequestCount {
		return Receipt{}, fmt.Errorf(
			"semantic generation requires %d rows; found %d requests and %d responses",
			manifest.RequestCount,
			len(requests),
			len(responses),
		)
	}
	if err := decorateNodes(bundle.LogicalGraph.Nodes, bundle, manifest, requests, responses); err != nil {
		return Receipt{}, err
	}
	manifestDocument := bundle.LogicalGraph.Manifest
	manifestDocument["semanticLayer"] = semanticManifest(bundle, manifest, requests)
	output := outputDocument{
		Format: semanticLayerFormat, Manifest: manifestDocument,
		Nodes: bundle.LogicalGraph.Nodes, Edges: bundle.LogicalGraph.Edges,
	}
	encoded, err := json.MarshalIndent(output, "", "  ")
	if err != nil {
		return Receipt{}, fmt.Errorf("encode synchronized semantic graph: %w", err)
	}
	encoded = append(encoded, '\n')
	selectedOutput := filepath.Clean(strings.TrimSpace(outputPath))
	if selectedOutput == "." {
		return Receipt{}, fmt.Errorf("semantic sync output path must not be empty")
	}
	if !dryRun {
		if err := writeAtomic(selectedOutput, encoded); err != nil {
			return Receipt{}, err
		}
	}
	return Receipt{
		BundleID: bundle.BundleID, GenerationID: manifest.GenerationID,
		Model: manifest.Model, NodeCount: len(bundle.LogicalGraph.Nodes),
		EdgeCount: len(bundle.LogicalGraph.Edges), Output: selectedOutput, DryRun: dryRun,
	}, nil
}

func loadBundle(path string) (bundleDocument, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return bundleDocument{}, fmt.Errorf("read Researcher lineage bundle %s: %w", path, err)
	}
	var bundle bundleDocument
	if err := decodeStrict(content, &bundle); err != nil {
		return bundleDocument{}, fmt.Errorf("decode Researcher lineage bundle %s: %w", path, err)
	}
	if bundle.Format != bundleFormat || bundle.LogicalGraph.Format != graphFormat {
		return bundleDocument{}, fmt.Errorf(
			"unsupported Researcher lineage formats %q and %q",
			bundle.Format,
			bundle.LogicalGraph.Format,
		)
	}
	if bundle.BundleID == "" || len(bundle.LogicalGraph.Nodes) == 0 {
		return bundleDocument{}, fmt.Errorf("Researcher lineage bundle %s is incomplete", path)
	}
	return bundle, nil
}

func loadRequests(path, bundleID string) (map[string]semanticRequest, error) {
	requests := make(map[string]semanticRequest)
	var promptVersion, promptSHA256 string
	err := scanJSONL(path, func(content []byte) error {
		var request semanticRequest
		if err := decodeStrict(content, &request); err != nil {
			return err
		}
		if request.RequestID == "" || request.BundleID != bundleID || request.NodeID == "" ||
			request.LineageNodeKey == "" ||
			request.PromptVersion == "" || request.PromptSHA256 == "" || request.EvidenceSHA256 == "" {
			return fmt.Errorf("semantic request is incomplete or targets another bundle")
		}
		if promptVersion == "" {
			promptVersion, promptSHA256 = request.PromptVersion, request.PromptSHA256
		} else if request.PromptVersion != promptVersion || request.PromptSHA256 != promptSHA256 {
			return fmt.Errorf("semantic requests contain inconsistent prompt contracts")
		}
		if _, exists := requests[request.NodeID]; exists {
			return fmt.Errorf("semantic requests repeat node %s", request.NodeID)
		}
		requests[request.NodeID] = request
		return nil
	})
	if err != nil {
		return nil, fmt.Errorf("load semantic requests %s: %w", path, err)
	}
	return requests, nil
}

func verifyFileSHA256(path, expected string) error {
	content, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("read semantic requests for digest verification %s: %w", path, err)
	}
	actual := fmt.Sprintf("%x", sha256.Sum256(content))
	if actual != expected {
		return fmt.Errorf("semantic requests digest mismatch: got %s, want %s", actual, expected)
	}
	return nil
}

func loadResponses(path string) (map[string]semanticResponse, error) {
	responses := make(map[string]semanticResponse)
	err := scanJSONL(path, func(content []byte) error {
		var response semanticResponse
		if err := decodeStrict(content, &response); err != nil {
			return err
		}
		if response.NodeID == "" || strings.TrimSpace(response.Description) == "" ||
			strings.TrimSpace(response.BusinessContext) == "" {
			return fmt.Errorf("semantic response is incomplete")
		}
		if _, exists := responses[response.NodeID]; exists {
			return fmt.Errorf("semantic responses repeat node %s", response.NodeID)
		}
		responses[response.NodeID] = response
		return nil
	})
	if err != nil {
		return nil, fmt.Errorf("load semantic responses %s: %w", path, err)
	}
	return responses, nil
}

func scanJSONL(path string, visit func([]byte) error) error {
	file, err := os.Open(path)
	if err != nil {
		return err
	}
	defer file.Close()
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 64*1024), maxJSONLRowBytes)
	line := 0
	for scanner.Scan() {
		line++
		content := bytes.TrimSpace(scanner.Bytes())
		if len(content) == 0 {
			return fmt.Errorf("line %d is blank", line)
		}
		if err := visit(content); err != nil {
			return fmt.Errorf("line %d: %w", line, err)
		}
	}
	if err := scanner.Err(); err != nil {
		return err
	}
	if line == 0 {
		return fmt.Errorf("file is empty")
	}
	return nil
}

func decorateNodes(
	nodes []map[string]any,
	bundle bundleDocument,
	generation generationManifest,
	requests map[string]semanticRequest,
	responses map[string]semanticResponse,
) error {
	known := make(map[string]struct{}, len(nodes))
	for _, node := range nodes {
		nodeID, ok := node["id"].(string)
		if !ok || nodeID == "" {
			return fmt.Errorf("logical graph contains a node without an id")
		}
		kind, ok := node["kind"].(string)
		if !ok || (kind != "dataset" && kind != "job") {
			return fmt.Errorf("logical node %s has unsupported kind", nodeID)
		}
		request, requestOK := requests[nodeID]
		response, responseOK := responses[nodeID]
		if !requestOK || !responseOK {
			return fmt.Errorf("logical node %s lacks complete semantic meaning", nodeID)
		}
		facets, err := nodeFacets(node, nodeID)
		if err != nil {
			return err
		}
		facets[semanticFacetName] = semanticFacet{
			Producer:  "https://github.com/precisionlender/researcher",
			SchemaURL: baseFacetSchema, FacetType: semanticFacetType(kind),
			SemanticCorpusVersion: semanticCorpusFormat, Status: "available",
			Entries: []semanticEntry{{
				SemanticEntryID: semanticEntryID(bundle.BundleID, nodeID),
				LineageNodeKey:  request.LineageNodeKey, Authority: "generated", Revision: 1,
				Description: response.Description, BusinessContext: response.BusinessContext,
				Producer: generation.Model, PromptVersion: request.PromptVersion,
				PromptSHA256: request.PromptSHA256, EvidenceSHA256: request.EvidenceSHA256,
				CreatedAt: generation.CreatedAt.UTC().Format("2006-01-02T15:04:05.999999Z"),
			}},
		}
		node["facets"] = facets
		known[nodeID] = struct{}{}
	}
	for nodeID := range requests {
		if _, ok := known[nodeID]; !ok {
			return fmt.Errorf("semantic request targets unknown logical node %s", nodeID)
		}
	}
	for nodeID := range responses {
		if _, ok := known[nodeID]; !ok {
			return fmt.Errorf("semantic response targets unknown logical node %s", nodeID)
		}
	}
	return nil
}

func nodeFacets(node map[string]any, nodeID string) (map[string]any, error) {
	value, exists := node["facets"]
	if !exists || value == nil {
		return map[string]any{}, nil
	}
	facets, ok := value.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("logical node %s facets must be an object", nodeID)
	}
	return facets, nil
}

func semanticFacetType(kind string) string {
	if kind == "dataset" {
		return "Q2SemanticMeaningDatasetFacet"
	}
	return "Q2SemanticMeaningJobFacet"
}

func semanticEntryID(bundleID, nodeID string) string {
	key := fmt.Sprintf("%s:%s:generated:1", bundleID, nodeID)
	return uuid.NewSHA1(uuid.NameSpaceURL, []byte(key)).String()
}

func semanticManifest(
	bundle bundleDocument,
	generation generationManifest,
	requests map[string]semanticRequest,
) map[string]any {
	promptVersions := make([]string, 0, len(requests))
	for _, request := range requests {
		promptVersions = append(promptVersions, request.PromptVersion)
	}
	sort.Strings(promptVersions)
	promptVersion := promptVersions[0]
	return map[string]any{
		"format": semanticLayerFormat, "bundleFormat": bundle.Format,
		"bundleId": bundle.BundleID, "bundleGeneratedAt": bundle.GeneratedAt,
		"semanticCorpusVersion":        semanticCorpusFormat,
		"semanticMeaningPromptVersion": promptVersion,
		"source":                       "researcher", "generationId": generation.GenerationID,
		"generationCreatedAt": generation.CreatedAt, "model": generation.Model,
		"effort": generation.Effort, "requestCount": generation.RequestCount,
		"requestsSha256":             generation.RequestsSHA256,
		"runtimeConfigurationSha256": generation.RuntimeConfigurationSHA256,
	}
}

func writeAtomic(path string, content []byte) error {
	directory := filepath.Dir(path)
	if err := os.MkdirAll(directory, 0o755); err != nil {
		return fmt.Errorf("create semantic sync output directory %s: %w", directory, err)
	}
	file, err := os.CreateTemp(directory, ".semantic-sync-*.json")
	if err != nil {
		return fmt.Errorf("create semantic sync temporary file: %w", err)
	}
	temporary := file.Name()
	defer os.Remove(temporary)
	if err := file.Chmod(0o644); err != nil {
		file.Close()
		return fmt.Errorf("set semantic sync file permissions: %w", err)
	}
	if _, err := file.Write(content); err != nil {
		file.Close()
		return fmt.Errorf("write semantic sync output: %w", err)
	}
	if err := file.Sync(); err != nil {
		file.Close()
		return fmt.Errorf("sync semantic sync output: %w", err)
	}
	if err := file.Close(); err != nil {
		return fmt.Errorf("close semantic sync output: %w", err)
	}
	if err := os.Rename(temporary, path); err != nil {
		return fmt.Errorf("publish semantic sync output %s: %w", path, err)
	}
	return nil
}
