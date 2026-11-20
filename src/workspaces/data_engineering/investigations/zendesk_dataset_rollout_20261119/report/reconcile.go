package main

import (
	"bytes"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

func checkResultMetadata(r result, t target, effective []byte) error {
	if r.NodeID != t.NodeID || r.Model != "gpt-6-luna" || r.PromptVersion != "2.0.0" || r.PromptSHA != promptSHA || r.CallerPolicySHA != policySHA || r.Passes != 1 || r.EffectivePromptSHA != digest(effective) || r.InputSHA != t.Files["input"].SHA256 || r.BeforeSHA != t.Files["before"].SHA256 || r.PreparedSHA != t.Files["prepared"].SHA256 || r.Published || r.Approved {
		return fmt.Errorf("attempt/result identity, pass count, pins or offline status mismatch: %s", t.NodeID)
	}
	if _, err := time.Parse(time.RFC3339Nano, r.Started); err != nil {
		return fmt.Errorf("invalid attempt start time: %s", t.NodeID)
	}
	return nil
}
func optional(root, rel string) ([]byte, bool, error) {
	p, err := artifactPath(root, rel)
	if os.IsNotExist(err) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	b, err := os.ReadFile(p)
	return b, err == nil, err
}

func reconcileTarget(root string, t target, effective []byte) (nodeRow, map[string]int64, error) {
	row := nodeRow{NodeID: t.NodeID, Status: "pending", Held: true, Files: map[string]string{}, ObservedHashes: map[string]string{}, NewArticleURLs: []string{}, Cited: []citation{}}
	blobs := map[string][]byte{}
	for name, p := range t.Files {
		b, err := pinned(root, p)
		if err != nil {
			return row, nil, err
		}
		blobs[name] = b
		row.Files[name] = p.Path
		row.ObservedHashes[name] = digest(b)
	}
	before, err := parseDefinition(blobs["before"], t.NodeID)
	if err != nil {
		return row, nil, err
	}
	prepared, err := parseDefinition(blobs["prepared"], t.NodeID)
	if err != nil {
		return row, nil, err
	}
	row.AuditPrepared = before != prepared
	var payload input
	if err := decode(blobs["input"], &payload); err != nil {
		return row, nil, err
	}
	if payload.Target.NodeID != t.NodeID || payload.Target.Generation != generation || payload.Definition != prepared || payload.Zendesk.Snapshot != snapshot {
		return row, nil, fmt.Errorf("input target/definition/snapshot mismatch %s", t.NodeID)
	}
	var full struct {
		NodeID     string `json:"node_id"`
		Generation string `json:"generation_id"`
	}
	if err := decode(blobs["target"], &full); err != nil {
		return row, nil, err
	}
	if full.NodeID != t.NodeID || full.Generation != generation {
		return row, nil, fmt.Errorf("full target identity/generation mismatch")
	}
	attemptBytes, hasAttempt, err := optional(root, t.Directory+"/attempt.json")
	if err != nil {
		return row, nil, err
	}
	resultBytes, hasResult, err := optional(root, t.Directory+"/result.json")
	if err != nil {
		return row, nil, err
	}
	if !hasAttempt && !hasResult {
		return row, nil, nil
	}
	if !hasAttempt {
		return row, nil, fmt.Errorf("result lacks single-pass attempt marker: %s", t.NodeID)
	}
	var attempt result
	if err := decode(attemptBytes, &attempt); err != nil {
		return row, nil, err
	}
	if err := checkResultMetadata(attempt, t, effective); err != nil {
		return row, nil, err
	}
	row.Files["attempt"] = t.Directory + "/attempt.json"
	row.ObservedHashes["attempt"] = digest(attemptBytes)
	if !hasResult {
		row.Status = "unresolved_attempt"
		row.Error = "An exclusive attempt marker exists without a final result. No retry is authorized by this report."
		return row, nil, nil
	}
	var r result
	if err := decode(resultBytes, &r); err != nil {
		return row, nil, err
	}
	if err := checkResultMetadata(r, t, effective); err != nil {
		return row, nil, err
	}
	if r.Started != attempt.Started {
		return row, nil, fmt.Errorf("result/attempt start differs")
	}
	if _, err := time.Parse(time.RFC3339Nano, r.Completed); err != nil {
		return row, nil, fmt.Errorf("result lacks valid completion time")
	}
	expectedRequest := digest(append(append(append([]byte{}, effective...), []byte("\n\n## Supplied inputs\n\n")...), blobs["input"]...))
	if r.RequestSHA != expectedRequest {
		return row, nil, fmt.Errorf("model request hash mismatch: %s", t.NodeID)
	}
	row.Files["result"] = t.Directory + "/result.json"
	row.ObservedHashes["result"] = digest(resultBytes)
	for _, name := range []string{"model-output.txt", "rawmodel-output.txt"} {
		raw, exists, err := optional(root, t.Directory+"/"+name)
		if err != nil {
			return row, nil, err
		}
		if !exists {
			continue
		}
		if row.Files["raw"] != "" {
			return row, nil, fmt.Errorf("ambiguous raw output files: %s", t.NodeID)
		}
		row.Files["raw"] = t.Directory + "/" + name
		row.ObservedHashes["raw"] = digest(raw)
		if r.RawSHA != "" {
			if digest(raw) != r.RawSHA {
				return row, nil, fmt.Errorf("raw output hash mismatch: %s", t.NodeID)
			}
			row.RawHashVerified = true
		}
	}
	if r.RawSHA != "" && row.Files["raw"] == "" {
		return row, nil, fmt.Errorf("pinned raw output is missing")
	}
	if err := verifyValidationChain(root, t, r, effective, &row); err != nil {
		return row, nil, err
	}
	if r.DraftSHA != "" {
		heldDraft, exists, err := optional(root, t.Directory+"/draft.json")
		if err != nil || !exists || digest(heldDraft) != r.DraftSHA {
			return row, nil, fmt.Errorf("emitted draft output hash mismatch: %s", t.NodeID)
		}
	}
	for name, n := range r.Usage {
		if n < 0 {
			return row, nil, fmt.Errorf("negative token usage %s", name)
		}
	}
	if r.Status == "failed" {
		if r.Error == "" {
			return row, nil, fmt.Errorf("failed result lacks error")
		}
		row.Status = "failed"
		row.Error = r.Error
		return row, r.Usage, nil
	}
	if r.Status != "changed" && r.Status != "unchanged" {
		return row, nil, fmt.Errorf("unknown emitted result status %q", r.Status)
	}
	if r.Error != "" || !row.RawHashVerified || r.DraftSHA == "" {
		return row, nil, fmt.Errorf("successful result lacks verified output pins or has error")
	}
	draftBytes, exists, err := optional(root, t.Directory+"/draft.json")
	if err != nil || !exists {
		return row, nil, fmt.Errorf("successful draft missing: %s", t.NodeID)
	}
	if digest(draftBytes) != r.DraftSHA {
		return row, nil, fmt.Errorf("draft output hash mismatch: %s", t.NodeID)
	}
	draft, err := parseDefinition(draftBytes, t.NodeID)
	if err != nil {
		return row, nil, err
	}
	raw, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(row.Files["raw"])))
	if err != nil {
		return row, nil, err
	}
	normalized := strings.TrimSpace(string(raw))
	if strings.HasPrefix(normalized, "```json\n") && strings.HasSuffix(normalized, "\n```") {
		normalized = strings.TrimSuffix(strings.TrimPrefix(normalized, "```json\n"), "\n```")
	}
	rawDefinition, err := parseDefinition(bytes.TrimSpace([]byte(normalized)), t.NodeID)
	if err != nil || rawDefinition != draft {
		return row, nil, fmt.Errorf("successful draft differs from normalized raw output")
	}
	expectedStatus := "changed"
	if before == draft {
		expectedStatus = "unchanged"
	}
	if r.Status != expectedStatus || r.ModelChanged != (prepared != draft) || r.AuditChanged != (before != prepared) {
		return row, nil, fmt.Errorf("change flags/status disagree with definition values: %s", t.NodeID)
	}
	if err := verifyCitations(payload, prepared, draft, r); err != nil {
		return row, nil, err
	}
	row.Status = r.Status
	row.Held = false
	row.ModelChanged = r.ModelChanged
	row.AuditCleanupChanged = r.AuditChanged
	row.NewArticleURLs = r.NewArticleURLs
	row.Cited = r.Cited
	row.Files["draft"] = t.Directory + "/draft.json"
	row.ObservedHashes["draft"] = digest(draftBytes)
	return row, r.Usage, nil
}
