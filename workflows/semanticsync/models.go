// Package semanticsync imports Researcher's published Semantic Layer snapshot.
package semanticsync

import (
	"encoding/json"
	"time"
)

const (
	bundleFormat         = "research-system-openlineage-bundle/v2"
	graphFormat          = "q2-openlineage-graph/v2"
	semanticLayerFormat  = "q2-openlineage-semantic-layer/v2"
	semanticCorpusFormat = "q2-openlineage-semantic-corpus/v2"
	semanticFacetName    = "q2_semanticMeaning"
	baseFacetSchema      = "https://raw.githubusercontent.com/OpenLineage/OpenLineage/1.49.0/spec/OpenLineage.json#/$defs/BaseFacet"
)

type bundleDocument struct {
	BundleID              string          `json:"bundleId"`
	Format                string          `json:"format"`
	GeneratedAt           time.Time       `json:"generatedAt"`
	LogicalGraph          graphDocument   `json:"logicalGraph"`
	LogicalGroups         json.RawMessage `json:"logicalGroups"`
	RawGraph              json.RawMessage `json:"rawGraph"`
	SchemaDefinitionCount int             `json:"schemaDefinitionCount"`
	SourceManifest        json.RawMessage `json:"sourceManifest"`
}

type graphDocument struct {
	Format      string           `json:"format"`
	Fingerprint string           `json:"fingerprint"`
	Manifest    map[string]any   `json:"manifest"`
	Nodes       []map[string]any `json:"nodes"`
	Edges       []map[string]any `json:"edges"`
}

type generationManifest struct {
	BundleID                   string    `json:"bundle_id"`
	CreatedAt                  time.Time `json:"created_at"`
	Effort                     string    `json:"effort"`
	GenerationID               string    `json:"generation_id"`
	Model                      string    `json:"model"`
	RequestCount               int       `json:"request_count"`
	RequestsSHA256             string    `json:"requests_sha256"`
	RuntimeConfigurationSHA256 string    `json:"runtime_configuration_sha256"`
	SchemaVersion              string    `json:"schema_version"`
}

type semanticRequest struct {
	RequestID      string          `json:"requestId"`
	BundleID       string          `json:"bundleId"`
	NodeID         string          `json:"nodeId"`
	LineageNodeKey string          `json:"lineageNodeKey"`
	PromptVersion  string          `json:"promptVersion"`
	PromptSHA256   string          `json:"promptSha256"`
	Prompt         string          `json:"prompt"`
	EvidenceSHA256 string          `json:"evidenceSha256"`
	Evidence       json.RawMessage `json:"evidence"`
}

type semanticResponse struct {
	BusinessContext string `json:"business_context"`
	Description     string `json:"description"`
	NodeID          string `json:"node_id"`
}

type semanticEntry struct {
	SemanticEntryID string `json:"semanticEntryId"`
	LineageNodeKey  string `json:"lineageNodeKey"`
	Authority       string `json:"authority"`
	Revision        int    `json:"revision"`
	Description     string `json:"description"`
	BusinessContext string `json:"businessContext"`
	Producer        string `json:"producer"`
	PromptVersion   string `json:"promptVersion"`
	PromptSHA256    string `json:"promptSha256"`
	EvidenceSHA256  string `json:"evidenceSha256"`
	CreatedAt       string `json:"createdAt"`
}

type semanticFacet struct {
	Producer              string          `json:"_producer"`
	SchemaURL             string          `json:"_schemaURL"`
	FacetType             string          `json:"facetType"`
	SemanticCorpusVersion string          `json:"semanticCorpusVersion"`
	Status                string          `json:"status"`
	Entries               []semanticEntry `json:"entries"`
}

type outputDocument struct {
	Format   string           `json:"format"`
	Manifest map[string]any   `json:"manifest"`
	Nodes    []map[string]any `json:"nodes"`
	Edges    []map[string]any `json:"edges"`
}

// Receipt reports the exact Researcher snapshot selected by one sync.
type Receipt struct {
	BundleID     string `json:"bundle_id"`
	GenerationID string `json:"generation_id"`
	Model        string `json:"model"`
	NodeCount    int    `json:"node_count"`
	EdgeCount    int    `json:"edge_count"`
	Output       string `json:"output"`
	DryRun       bool   `json:"dry_run"`
}
