package main

import "encoding/json"

const promptSHA = "6c876bc7a89ae483a6cfead9384fb37de14a60069c8e0852e20171616ae62226"
const policySHA = "0b0a9ac8e4ac0d0ab811bdb09955b613bb6d5d0c5c9d3db243a84efcca7acf4f"
const generation = "e020475b-bc7b-40d7-9652-00935e2565fd"
const snapshot = "2026-09-02T205953Z-zendesk-corpus"

type pin struct {
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
}
type policy struct {
	Version string `json:"version"`
	Path    string `json:"path"`
	SHA256  string `json:"sha256"`
}
type target struct {
	NodeID     string         `json:"node_id"`
	ArtifactID string         `json:"artifact_id"`
	Directory  string         `json:"directory"`
	Files      map[string]pin `json:"files"`
}
type manifest struct {
	SelectedCount       int               `json:"selected_count"`
	Generation          string            `json:"source_generation"`
	Bundle              string            `json:"source_bundle"`
	Prompt              policy            `json:"prompt"`
	CallerPolicy        policy            `json:"caller_policy"`
	Sources             map[string]pin    `json:"sources"`
	Corpus              map[string]string `json:"corpus_hashes"`
	Projection          policy            `json:"evidence_context_projection"`
	ModelCapacity       pin               `json:"model_capacity"`
	CapacityObservation pin               `json:"model_capacity_observation"`
	Targets             []target          `json:"targets"`
}
type definition struct {
	Description     string `json:"description"`
	BusinessContext string `json:"business_context"`
	NodeID          string `json:"node_id"`
}
type citation struct {
	ArticleID string `json:"article_id"`
	ChunkID   string `json:"chunk_id"`
	URL       string `json:"url"`
}
type result struct {
	ValidationContract     string           `json:"validation_contract,omitempty"`
	InitialValidationError string           `json:"initial_validation_error,omitempty"`
	InitialResultSHA       string           `json:"initial_result_sha256,omitempty"`
	NodeID                 string           `json:"node_id"`
	Model                  string           `json:"requested_model"`
	PromptVersion          string           `json:"prompt_version"`
	PromptSHA              string           `json:"prompt_sha256"`
	CallerPolicySHA        string           `json:"caller_policy_sha256"`
	EffectivePromptSHA     string           `json:"effective_prompt_sha256"`
	RequestSHA             string           `json:"model_request_sha256"`
	Passes                 int              `json:"edit_passes"`
	Status                 string           `json:"status"`
	Error                  string           `json:"error,omitempty"`
	Started                string           `json:"started_at"`
	Completed              string           `json:"completed_at"`
	InputSHA               string           `json:"input_sha256"`
	BeforeSHA              string           `json:"before_sha256"`
	PreparedSHA            string           `json:"prepared_sha256"`
	RawSHA                 string           `json:"raw_output_sha256,omitempty"`
	DraftSHA               string           `json:"draft_sha256,omitempty"`
	ModelChanged           bool             `json:"model_changed"`
	AuditChanged           bool             `json:"audit_cleanup_changed"`
	NewArticleURLs         []string         `json:"new_article_urls"`
	Cited                  []citation       `json:"cited_chunks"`
	Usage                  map[string]int64 `json:"usage"`
	Published              bool             `json:"published"`
	Approved               bool             `json:"sme_approved"`
}
type input struct {
	Target struct {
		NodeID     string `json:"node_id"`
		Generation string `json:"generation_id"`
	} `json:"target"`
	Definition definition `json:"definition"`
	Zendesk    struct {
		Snapshot string `json:"snapshot_id"`
		Chunks   []struct {
			ID        string      `json:"chunkId"`
			ArticleID json.Number `json:"articleId"`
			URL       string      `json:"url"`
		} `json:"chunks"`
	} `json:"zendesk_evidence"`
}
type nodeRow struct {
	ValidationContract     string            `json:"validation_contract,omitempty"`
	InitialValidationError string            `json:"initial_validation_error,omitempty"`
	NodeID                 string            `json:"node_id"`
	Status                 string            `json:"status"`
	Held                   bool              `json:"held"`
	Error                  string            `json:"error,omitempty"`
	ModelChanged           bool              `json:"model_changed"`
	AuditPrepared          bool              `json:"audit_cleanup_prepared"`
	AuditCleanupChanged    bool              `json:"audit_cleanup_changed"`
	NewArticleURLs         []string          `json:"new_article_urls"`
	Cited                  []citation        `json:"cited_chunks"`
	Files                  map[string]string `json:"files"`
	ObservedHashes         map[string]string `json:"observed_hashes"`
	RawHashVerified        bool              `json:"raw_hash_verified"`
}
type summary struct {
	SourceRepositories        []sourceRepository `json:"source_repository_pins"`
	ReconciledInitialFailures int                `json:"artifact_reconciled_initial_failures"`
	Format                    string             `json:"format"`
	Complete                  bool               `json:"complete"`
	Selected                  int                `json:"selected_count"`
	Counts                    map[string]int     `json:"counts"`
	ModelChanged              int                `json:"model_changed"`
	AuditPrepared             int                `json:"audit_cleanup_prepared"`
	AuditCleanupChanged       int                `json:"audit_cleanup_changed"`
	Model                     string             `json:"requested_model"`
	EditPasses                int                `json:"edit_passes_per_emitted_attempt"`
	ManifestSHA               string             `json:"frozen_manifest_sha256"`
	Pins                      manifest           `json:"frozen_provenance"`
	Corpus                    struct {
		Snapshot     string `json:"snapshot_id"`
		Articles     int    `json:"articles"`
		Chunks       int    `json:"chunks"`
		Verification string `json:"verification"`
	} `json:"corpus"`
	NewArticleURLs      []string         `json:"new_article_urls"`
	Cited               []citation       `json:"cited_article_chunk_candidates"`
	CitationAttribution string           `json:"citation_attribution"`
	Usage               map[string]int64 `json:"usage"`
	SourceGraphChanged  bool             `json:"source_graph_changed"`
	Published           bool             `json:"published"`
	SMEApproved         bool             `json:"sme_approved"`
	Limits              []string         `json:"limits"`
	Nodes               []nodeRow        `json:"nodes"`
}
type sourceRepository struct {
	Repository string `json:"repository"`
	Commit     string `json:"commitSha"`
	Ref        string `json:"sourceRef"`
}
