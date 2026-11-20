package main

import (
	"path/filepath"
	"testing"
)

func TestArtifactOnlyCorrectionChain(t *testing.T) {
	f := synthetic(t)
	f.emit(t, "changed")
	initial := f.result
	initial.Status = "failed"
	initial.Error = "strict initial literal guard"
	initial.DraftSHA = ""
	initial.ModelChanged = false
	initial.Cited = nil
	initial.NewArticleURLs = nil
	initialBytes := encode(t, initial)
	save(t, filepath.Join(f.root, f.target.Directory, "result.initial.json"), initialBytes)
	f.result.InitialResultSHA = digest(initialBytes)
	f.result.InitialValidationError = initial.Error
	f.result.ValidationContract = "audit-body-identity-and-code-format/v2"
	save(t, filepath.Join(f.root, f.target.Directory, "result.json"), encode(t, f.result))
	correction := map[string]any{"node_id": f.target.NodeID, "validation_contract": f.result.ValidationContract, "initial_result_sha256": f.result.InitialResultSHA, "raw_output_sha256": f.result.RawSHA, "draft_sha256": f.result.DraftSHA, "additional_model_calls": 0, "definition_values_edited": false, "status": "accepted"}
	save(t, filepath.Join(f.root, f.target.Directory, "validation-v2.json"), encode(t, correction))
	row, _, err := reconcileTarget(f.root, f.target, f.effective)
	if err != nil || row.ValidationContract == "" || row.Files["initial-result"] == "" || row.Held {
		t.Fatalf("correction chain not reconciled: %+v %v", row, err)
	}
	correction["additional_model_calls"] = 1
	save(t, filepath.Join(f.root, f.target.Directory, "validation-v2.json"), encode(t, correction))
	if _, _, err := reconcileTarget(f.root, f.target, f.effective); err == nil {
		t.Fatal("additional model call accepted")
	}
}

func TestUnchangedValueAccounting(t *testing.T) {
	f := synthetic(t)
	f.edited = f.prepared
	f.result.ModelChanged = false
	f.result.NewArticleURLs = []string{}
	f.result.Cited = []citation{}
	f.emit(t, "unchanged")
	row, _, err := reconcileTarget(f.root, f.target, f.effective)
	if err != nil || row.Status != "unchanged" || row.ModelChanged || row.AuditPrepared {
		t.Fatalf("unchanged accounting differs: %+v %v", row, err)
	}
}
