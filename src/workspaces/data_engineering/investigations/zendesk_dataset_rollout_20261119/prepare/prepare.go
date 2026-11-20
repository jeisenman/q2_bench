package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/jeisenman/q2_bench/src/workspaces/data_engineering/investigations/zendesk_dataset_rollout_20261119/contract"
)

type fileRecord struct {
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
}
type targetRecord struct {
	NodeID     string                `json:"node_id"`
	ArtifactID string                `json:"artifact_id"`
	Directory  string                `json:"directory"`
	Files      map[string]fileRecord `json:"files"`
}
type runManifest struct {
	SelectedCount int    `json:"selected_count"`
	Generation    string `json:"source_generation"`
	Bundle        string `json:"source_bundle"`
	Prompt        struct {
		Version string `json:"version"`
		SHA     string `json:"sha256"`
		Path    string `json:"path"`
	} `json:"prompt"`
	Sources             map[string]fileRecord `json:"sources"`
	Corpus              map[string]string     `json:"corpus_hashes"`
	Preparation         string                `json:"preparation_contract"`
	Retrieval           string                `json:"retrieval_contract"`
	MaxInputBytes       int                   `json:"maximum_input_bytes"`
	MaxEstimatedTokens  int                   `json:"maximum_estimated_input_tokens"`
	Targets             []targetRecord        `json:"targets"`
	CallerPolicy        *policyRecord         `json:"caller_policy,omitempty"`
	ContextProjection   policyRecord          `json:"evidence_context_projection"`
	ModelCapacity       fileRecord            `json:"model_capacity"`
	CapacityObservation fileRecord            `json:"model_capacity_observation"`
	Statistics          preparationStats      `json:"statistics"`
}
type preparedInput struct {
	Target            modelTarget                `json:"target"`
	Definition        definition                 `json:"definition"`
	Technical         map[string]json.RawMessage `json:"technical_evidence"`
	CallerPolicy      *policyRecord              `json:"caller_policy,omitempty"`
	PreparationStatus string                     `json:"preparation_status"`
	ContextProjection contextProvenance          `json:"evidence_context_projection"`
	Zendesk           struct {
		SnapshotID string  `json:"snapshot_id"`
		Chunks     []chunk `json:"chunks"`
	} `json:"zendesk_evidence"`
}
type preflightFailure struct {
	NodeID string `json:"node_id"`
	Error  string `json:"error"`
}
type preparationStats struct {
	MaxInputBytes  int `json:"max_input_bytes"`
	ZeroCandidates int `json:"zero_candidate_targets"`
	PendingCleanup int `json:"pending_single_luna_cleanup"`
}

func validateInputBound(b, prompt []byte) error {
	if len(b) > maximumInputBytes {
		return fmt.Errorf("input is %d bytes; capacity-backed maximum is %d; evidence was not truncated", len(b), maximumInputBytes)
	}
	// UTF-8 byte count / 3 is an explicit conservative operational estimate, not tokenizer proof.
	estimate := (len(b) + len(prompt) + 2) / 3
	if estimate > maximumEstimatedTokens {
		return fmt.Errorf("estimated input plus prompt is %d tokens (ceil UTF-8 bytes/3); capacity-backed maximum is %d; evidence was not truncated", estimate, maximumEstimatedTokens)
	}
	return nil
}

func prepare(c config) (err error) {
	policy, policyErr := selectedPolicy(c.cleanupPolicy)
	if policyErr != nil {
		return policyErr
	}
	for name, path := range map[string]string{"graph": c.graph, "staged": c.staged, "requests": c.requests, "responses": c.responses, "corpus": c.corpus, "prompt": c.prompt, "output": c.output, "model-capacity": c.modelCapacity} {
		if strings.TrimSpace(path) == "" {
			return fmt.Errorf("--%s is required", name)
		}
	}
	if _, e := os.Lstat(c.output); e == nil {
		return fmt.Errorf("output already exists: %s", c.output)
	} else if !os.IsNotExist(e) {
		return e
	}
	paths := map[string]string{"graph": c.graph, "staged": c.staged, "requests": c.requests, "responses": c.responses, "prompt": c.prompt, "generation_manifest": filepath.Join(filepath.Dir(c.responses), "manifest.json")}
	paths["model_capacity"] = c.modelCapacity
	if c.generationManifest != "" {
		paths["generation_manifest"] = c.generationManifest
	}
	blobs := map[string][]byte{}
	for name, path := range paths {
		b, e := read(path)
		if e != nil {
			return e
		}
		blobs[name] = b
	}
	if digest(blobs["prompt"]) != expectedPrompt {
		return fmt.Errorf("prompt 2.0.0 digest mismatch")
	}
	if digest(blobs["graph"]) != expectedGraph {
		return fmt.Errorf("frozen graph digest mismatch")
	}
	if digest(blobs["model_capacity"]) != expectedCapacityRecord {
		return fmt.Errorf("pinned model-capacity record digest mismatch")
	}
	capacity, capacityErr := loadCapacity(blobs["model_capacity"])
	if capacityErr != nil {
		return capacityErr
	}
	if digest(blobs["requests"]) != expectedRequests {
		return fmt.Errorf("published request file digest mismatch")
	}
	var generation struct {
		ID          string `json:"generation_id"`
		Bundle      string `json:"bundle_id"`
		RequestsSHA string `json:"requests_sha256"`
		Count       int    `json:"request_count"`
		Schema      string `json:"schema_version"`
	}
	if e := decode(blobs["generation_manifest"], &generation); e != nil {
		return e
	}
	if generation.ID != expectedGeneration || generation.RequestsSHA != expectedRequests || generation.Schema != "1.0" {
		return fmt.Errorf("published generation manifest pin mismatch")
	}
	var graph contract.Graph
	if e := decode(blobs["graph"], &graph); e != nil {
		return fmt.Errorf("decode frozen graph: %w", e)
	}
	var staged stagedDocument
	if e := decode(blobs["staged"], &staged); e != nil {
		return e
	}
	if generation.Bundle != staged.Manifest.Semantic.Bundle || generation.Count != staged.Manifest.Semantic.Count {
		return fmt.Errorf("generation and staged manifest disagree")
	}
	requests, rawRequests, e := lines(blobs["requests"], func(r request) string { return r.NodeID })
	if e != nil {
		return e
	}
	responses, rawResponses, e := lines(blobs["responses"], func(d definition) string { return d.NodeID })
	if e != nil {
		return e
	}
	targets, e := selectTargets(graph, staged, requests, responses, digest(blobs["staged"]), 553)
	if e != nil {
		return e
	}
	corpus, e := loadCorpus(c.corpus, 396, 3404)
	if e != nil {
		return e
	}
	manifest := runManifest{SelectedCount: 553, Generation: expectedGeneration, Bundle: generation.Bundle, Sources: map[string]fileRecord{}, Corpus: corpus.hashes, Preparation: "audit-only-sentence/v1; exact removed byte spans; ambiguous or mixed evidence fails preflight", Retrieval: "bm25-title-heading-v1; full corpus; 4 articles/12 complete chunks maximum; verified original chunks retained", MaxInputBytes: capacity.MaximumBytes, MaxEstimatedTokens: capacity.MaximumTokens, Targets: []targetRecord{}}
	manifest.Prompt.Version = "2.0.0"
	manifest.Prompt.SHA = expectedPrompt
	manifest.Prompt.Path = "sources/prompt.md"
	manifest.CallerPolicy = policy
	manifest.ContextProjection = policyRecord{Version: contextVersion, Path: "sources/evidence-context-projection.md", SHA256: contextPolicySHA}
	files := map[string][]byte{}
	files[manifest.ContextProjection.Path] = contextPolicy
	if policy != nil {
		files[policy.Path] = callerPolicy
	}
	for name, b := range blobs {
		extension := filepath.Ext(paths[name])
		rel := filepath.ToSlash(filepath.Join("sources", name+extension))
		files[rel] = b
		manifest.Sources[name] = fileRecord{Path: rel, SHA256: digest(b)}
	}
	manifest.ModelCapacity = manifest.Sources["model_capacity"]
	observationBytes, err := formatted(capacity.Observation)
	if err != nil {
		return err
	}
	observationPath := "sources/model_capacity_observation.json"
	files[observationPath] = observationBytes
	manifest.CapacityObservation = fileRecord{Path: observationPath, SHA256: digest(observationBytes)}
	failures := []preflightFailure{}
	definitions := map[string]definition{}
	changes := map[string]preparationRecord{}
	measurements := componentMeasurements{}
	for _, t := range targets {
		d := responses[t.NodeID]
		var keys map[string]json.RawMessage
		if e := decode(rawResponses[t.NodeID], &keys); e != nil {
			return e
		}
		if len(keys) != 3 || keys["description"] == nil || keys["business_context"] == nil || keys["node_id"] == nil {
			return fmt.Errorf("response does not have exact three-key definition contract: %s", t.NodeID)
		}
		cleaned, preparation, err := prepareDefinition(d, c.cleanupPolicy)
		if err != nil {
			failures = append(failures, preflightFailure{NodeID: t.NodeID, Error: err.Error()})
			continue
		}
		definitions[t.NodeID] = cleaned
		changes[t.NodeID] = preparation
		if preparation.Status == "pending_single_luna_cleanup" {
			manifest.Statistics.PendingCleanup++
		}
	}
	if len(failures) > 0 {
		return writePreflight(c.output, failures)
	}
	for _, t := range targets {
		d, cleaned, preparation := responses[t.NodeID], definitions[t.NodeID], changes[t.NodeID]
		request := requests[t.NodeID]
		original, err := originalChunks(request.Evidence["zendeskContext"], corpus)
		if err != nil {
			return fmt.Errorf("%s: %w", t.NodeID, err)
		}
		candidates, retrieval := retrieve(t, cleaned, corpus, original)
		if len(candidates) == 0 {
			manifest.Statistics.ZeroCandidates++
		}
		if len(candidates) > 12 || len(retrieval.ArticleIDs) > 4 {
			return fmt.Errorf("%s: verified original evidence exceeds 12 chunks or 4 articles; no truncation", t.NodeID)
		}
		id := digest([]byte(t.NodeID))
		dir := "nodes/" + id
		fullTargetBytes, err := formatted(t)
		if err != nil {
			return err
		}
		technical, projection, err := projectTechnical(request.Evidence, fileRecord{Path: dir + "/target.json", SHA256: digest(fullTargetBytes)}, fileRecord{Path: dir + "/original-request.json", SHA256: digest(rawRequests[t.NodeID])})
		if err != nil {
			return fmt.Errorf("%s: %w", t.NodeID, err)
		}
		input := preparedInput{Target: thinTarget(t), Definition: cleaned, Technical: technical, ContextProjection: projection}
		input.CallerPolicy = policy
		input.PreparationStatus = preparation.Status
		input.Zendesk.SnapshotID = expectedCorpus
		input.Zendesk.Chunks = candidates
		record := targetRecord{NodeID: t.NodeID, ArtifactID: id, Directory: dir, Files: map[string]fileRecord{}}
		objects := map[string]any{"target": t, "before": d, "prepared": cleaned, "input": input, "retrieval": retrieval, "preparation": preparation}
		for name, obj := range objects {
			b, e := formatted(obj)
			if e != nil {
				return e
			}
			if name == "input" {
				if c.measureComponents {
					if err := measurements.add(input, b); err != nil {
						return err
					}
				}
				if len(b) > manifest.Statistics.MaxInputBytes {
					manifest.Statistics.MaxInputBytes = len(b)
				}
				context := blobs["prompt"]
				if policy != nil {
					context = append(append([]byte{}, context...), callerPolicy...)
				}
				if e := validateInputBound(b, context); e != nil {
					failures = append(failures, preflightFailure{NodeID: t.NodeID, Error: e.Error()})
				}
			}
			rel := dir + "/" + name + ".json"
			files[rel] = b
			record.Files[name] = fileRecord{Path: rel, SHA256: digest(b)}
		}
		for name, b := range map[string][]byte{"original-request": rawRequests[t.NodeID], "original-response": rawResponses[t.NodeID]} {
			rel := dir + "/" + name + ".json"
			files[rel] = b
			record.Files[name] = fileRecord{Path: rel, SHA256: digest(b)}
		}
		manifest.Targets = append(manifest.Targets, record)
	}
	if c.measureComponents {
		return measurements.print(failures, manifest.Statistics)
	}
	if len(failures) > 0 {
		return writeBoundReport(c.output, failures, manifest.Statistics)
	}
	b, e := formatted(manifest)
	if e != nil {
		return e
	}
	files["manifest.json"] = b
	// No output directory exists until every target and bound has passed.
	if e := os.Mkdir(c.output, 0700); e != nil {
		return fmt.Errorf("create new output exclusively: %w", e)
	}
	defer func() {
		if err != nil {
			_ = os.RemoveAll(c.output)
		}
	}()
	names := []string{}
	for name := range files {
		names = append(names, name)
	}
	sort.Strings(names)
	for _, name := range names {
		path := filepath.Join(c.output, filepath.FromSlash(name))
		if e := os.MkdirAll(filepath.Dir(path), 0700); e != nil {
			return e
		}
		if e := os.WriteFile(path, files[name], 0600); e != nil {
			return e
		}
	}
	return nil
}

func writePreflight(output string, failures []preflightFailure) error {
	b, e := formatted(struct {
		Status   string             `json:"status"`
		Failures []preflightFailure `json:"failures"`
	}{"blocked_unsafe_audit_cleanup", failures})
	if e != nil {
		return e
	}
	path := output + ".preflight.json"
	f, e := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if e != nil {
		return fmt.Errorf("cleanup blocked for %d targets; cannot create report: %w", len(failures), e)
	}
	_, writeErr := f.Write(b)
	closeErr := f.Close()
	if writeErr != nil {
		return writeErr
	}
	if closeErr != nil {
		return closeErr
	}
	return fmt.Errorf("cleanup blocked for %d targets; review exact ambiguities in %s; no run prepared", len(failures), path)
}
