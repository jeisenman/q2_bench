package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

// revalidateHeld changes artifact validation only; raw model text and inputs stay unchanged.
func revalidateHeld(root string, m manifest) error {
	accepted, held := 0, 0
	for _, t := range m.Targets {
		dir, e := resolve(root, t.Directory)
		if e != nil {
			return e
		}
		resultPath := filepath.Join(dir, "result.json")
		originalBytes, e := os.ReadFile(resultPath)
		if e != nil {
			return fmt.Errorf("all model attempts must finish before revalidation: %w", e)
		}
		var r result
		if e = json.Unmarshal(originalBytes, &r); e != nil {
			return e
		}
		if r.Status != "failed" {
			continue
		}
		if r.NodeID != t.NodeID || r.Passes != 1 || r.PromptSHA != promptSHA || r.CallerPolicySHA != approvedPolicySHA {
			return fmt.Errorf("held result provenance mismatch: %s", t.NodeID)
		}
		if r.ValidationContract != "" {
			return fmt.Errorf("held result already revalidated; no repeated artifact loop: %s", t.NodeID)
		}
		raw, e := os.ReadFile(filepath.Join(dir, "model-output.txt"))
		if e != nil {
			held++
			continue
		}
		if digest(raw) != r.RawSHA {
			return fmt.Errorf("raw output hash changed: %s", t.NodeID)
		}
		input, e := pinned(root, t.Files.Input)
		if e != nil {
			return e
		}
		prepared, e := pinned(root, t.Files.Prepared)
		if e != nil {
			return e
		}
		before, e := pinned(root, t.Files.Before)
		if e != nil {
			return e
		}
		var prep struct {
			Status string `json:"status"`
		}
		prepBytes, e := pinned(root, t.Files.Preparation)
		if e != nil {
			return e
		}
		if e = json.Unmarshal(prepBytes, &prep); e != nil {
			return e
		}
		normalized, note := normalizeOutput(raw)
		draft, citations, validationErr := validateDefinition(normalized, prepared, input, t.NodeID, prep.Status == "pending_single_luna_cleanup")
		initialPath := filepath.Join(dir, "result.initial.json")
		f, e := os.OpenFile(initialPath, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
		if e != nil {
			return e
		}
		_, e = f.Write(originalBytes)
		closeErr := f.Close()
		if e != nil {
			return e
		}
		if closeErr != nil {
			return closeErr
		}
		r.InitialResultSHA = digest(originalBytes)
		r.InitialValidationError = r.Error
		r.ValidationContract = "audit-body-identity-and-code-format/v2"
		record := map[string]any{"node_id": t.NodeID, "validation_contract": r.ValidationContract, "initial_result_sha256": r.InitialResultSHA, "raw_output_sha256": r.RawSHA, "additional_model_calls": 0, "definition_values_edited": false, "rule_change": "Permit removal of redundant node-ID echoes/audit relationship metadata under approved cleanup; preserve technical code content regardless of Markdown code-span boundaries."}
		if validationErr != nil {
			r.Error = validationErr.Error()
			record["status"] = "held"
			record["error"] = r.Error
			held++
		} else {
			var original, base, edited definition
			if e = json.Unmarshal(before, &original); e != nil {
				return e
			}
			if e = json.Unmarshal(prepared, &base); e != nil {
				return e
			}
			if e = json.Unmarshal(draft, &edited); e != nil {
				return e
			}
			f, e := os.OpenFile(filepath.Join(dir, "draft.json"), os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
			if e != nil {
				return e
			}
			_, e = f.Write(draft)
			closeErr := f.Close()
			if e != nil {
				return e
			}
			if closeErr != nil {
				return closeErr
			}
			r.Status = "changed"
			if original == edited {
				r.Status = "unchanged"
			}
			r.ModelChanged = base != edited
			r.AuditCleanupChanged = original != base
			r.Error = ""
			r.DraftSHA = digest(draft)
			r.Cited = citations
			r.Normalization = note
			r.NewArticleURLs = []string{}
			originalURLs := urls(base.Description + "\n" + base.BusinessContext)
			added := map[string]bool{}
			for _, c := range citations {
				if !originalURLs[c.URL] && !added[c.URL] {
					r.NewArticleURLs = append(r.NewArticleURLs, c.URL)
					added[c.URL] = true
				}
			}
			record["status"] = "accepted"
			record["draft_sha256"] = r.DraftSHA
			accepted++
		}
		if e = writeJSON(filepath.Join(dir, "validation-v2.json"), record); e != nil {
			return e
		}
		if e = writeJSON(resultPath, r); e != nil {
			return e
		}
	}
	fmt.Printf("Artifact-only revalidation: %d accepted; %d held; zero additional model calls.\n", accepted, held)
	return nil
}
