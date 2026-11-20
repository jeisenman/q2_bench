package main

import "fmt"

func verifyValidationChain(root string, t target, r result, effective []byte, row *nodeRow) error {
	if r.InitialResultSHA == "" {
		if r.ValidationContract != "" {
			return fmt.Errorf("validation contract lacks initial result pin")
		}
		return nil
	}
	if r.ValidationContract != "audit-body-identity-and-code-format/v2" {
		return fmt.Errorf("unsupported artifact validation correction")
	}
	rel := t.Directory + "/result.initial.json"
	original, err := pinned(root, pin{Path: rel, SHA256: r.InitialResultSHA})
	if err != nil {
		return err
	}
	var initial result
	if err := decode(original, &initial); err != nil {
		return err
	}
	if err := checkResultMetadata(initial, t, effective); err != nil {
		return err
	}
	if initial.Status != "failed" || initial.Error != r.InitialValidationError || initial.RawSHA != r.RawSHA || initial.RequestSHA != r.RequestSHA || initial.Started != r.Started || initial.Completed != r.Completed || initial.InitialResultSHA != "" {
		return fmt.Errorf("initial-result correction provenance differs from emitted attempt")
	}
	correctionPath := t.Directory + "/validation-v2.json"
	raw, exists, err := optional(root, correctionPath)
	if err != nil || !exists {
		return fmt.Errorf("artifact-only validation correction record missing")
	}
	var record struct {
		NodeID          string `json:"node_id"`
		Contract        string `json:"validation_contract"`
		InitialSHA      string `json:"initial_result_sha256"`
		RawSHA          string `json:"raw_output_sha256"`
		DraftSHA        string `json:"draft_sha256"`
		AdditionalCalls *int   `json:"additional_model_calls"`
		ValuesEdited    *bool  `json:"definition_values_edited"`
		Status          string `json:"status"`
		Error           string `json:"error"`
	}
	if err := decode(raw, &record); err != nil {
		return err
	}
	expected := "accepted"
	if r.Status == "failed" {
		expected = "held"
	}
	if record.NodeID != t.NodeID || record.Contract != r.ValidationContract || record.InitialSHA != r.InitialResultSHA || record.RawSHA != r.RawSHA || record.DraftSHA != r.DraftSHA || record.AdditionalCalls == nil || *record.AdditionalCalls != 0 || record.ValuesEdited == nil || *record.ValuesEdited || record.Status != expected || record.Error != r.Error {
		return fmt.Errorf("artifact-only correction hash/status/zero-call assertion mismatch")
	}
	row.ValidationContract = r.ValidationContract
	row.InitialValidationError = r.InitialValidationError
	row.Files["initial-result"] = rel
	row.ObservedHashes["initial-result"] = digest(original)
	row.Files["validation-v2"] = correctionPath
	row.ObservedHashes["validation-v2"] = digest(raw)
	return nil
}
