package lineagecheck

import (
	"strings"
	"testing"
)

func TestDE3134ReplacementPreservesConsumedIndustryCodeAlias(t *testing.T) {
	m, roots := fixture(t)
	base := built(t, m, roots)
	head := cloneSnapshot(t, base, func(m *Manifest) {
		d := m.Datasets[1]
		d.ID = "primary/metadata"
		m.Datasets = append(m.Datasets, d)
		m.Jobs[0].Inputs[0].Dataset = d.ID
		for i := range m.Jobs[0].Dependencies {
			m.Jobs[0].Dependencies[i].Inputs[0].Dataset = d.ID
		}
	})
	r, err := Compare(base, head, Policy{Mode: "additive"})
	if err != nil || r.Status != "fail" || !hasFinding(r, "removed_input") {
		t.Fatalf("additive = %+v, %v", r, err)
	}
	p := Policy{Mode: "replacement", Replacements: []Replacement{{Job: "derive", From: "primary/supplemental", To: "primary/metadata", HistoryVerified: true, HistoryEvidence: "alpha validation run 123"}}}
	r, err = Compare(base, head, p)
	if err != nil || r.Status != "pass" {
		t.Fatalf("replacement = %+v, %v", r, err)
	}
	p.Replacements[0].HistoryVerified = false
	r, err = Compare(base, head, p)
	if err != nil || r.Status != "unknown" || !hasFinding(r, "replacement_history") {
		t.Fatalf("history = %+v, %v", r, err)
	}
	broken := cloneSnapshot(t, head, func(m *Manifest) {
		for i := range m.Datasets {
			if m.Datasets[i].ID == "primary/metadata" {
				for k := range m.Datasets[i].Fields {
					if m.Datasets[i].Fields[k].Name == "IndustryCode" {
						m.Datasets[i].Fields[k].Type = "IntegerType"
					}
				}
			}
		}
	})
	r, err = Compare(base, broken, p)
	if err != nil || !hasFinding(r, "incompatible_input_column") {
		t.Fatalf("type = %+v, %v", r, err)
	}
}

func TestAdditiveSchemaPreservesExistingColumnsAndOrdering(t *testing.T) {
	m, roots := fixture(t)
	base := built(t, m, roots)
	head := cloneSnapshot(t, base, func(m *Manifest) {
		m.Datasets[0].Fields = append(m.Datasets[0].Fields, Field{"NewColumn", "StringType", true})
		m.Datasets[0].Minor++
		m.Jobs[0].Dependencies = append(m.Jobs[0].Dependencies, Dependency{FieldRef{m.Datasets[0].ID, "NewColumn"}, []FieldRef{}})
	})
	r, err := Compare(base, head, Policy{Mode: "additive"})
	if err != nil || r.Status != "pass" {
		t.Fatalf("additive = %+v, %v", r, err)
	}
	broken := cloneSnapshot(t, base, func(m *Manifest) { m.Datasets[0].Fields[0].Nullable = false })
	r, err = Compare(base, broken, Policy{Mode: "additive"})
	if err != nil || r.Status != "fail" || !hasFinding(r, "field_contract") {
		t.Fatalf("nullable = %+v, %v", r, err)
	}
	_, err = Compare(base, head, Policy{Mode: "anything"})
	if err == nil {
		t.Fatal("invalid policy accepted")
	}
}

func TestValidationRejectsMissingColumnsAndOrderingCycles(t *testing.T) {
	m, _ := fixture(t)
	m.Jobs[0].Inputs[0].Fields = append(m.Jobs[0].Inputs[0].Fields, "Missing")
	if err := Validate(m); err == nil || !strings.Contains(err.Error(), "Missing") {
		t.Fatalf("missing column: %v", err)
	}
	m, _ = fixture(t)
	m.Jobs[0].After = []string{"derive"}
	if err := Validate(m); err == nil {
		t.Fatal("self dependency accepted")
	}
	m, _ = fixture(t)
	m.Jobs[0].Dependencies = m.Jobs[0].Dependencies[:1]
	if err := Validate(m); err == nil {
		t.Fatal("incomplete dependency claim accepted")
	}
	var p Policy
	if err := Decode([]byte(`{"mode":"additive","typo":true}`), &p); err == nil {
		t.Fatal("unknown JSON accepted")
	}
	if err := Decode([]byte(`{"mode":"additive"} {}`), &p); err == nil {
		t.Fatal("trailing JSON accepted")
	}
}

func TestAdditionalJoinInputCannotSilentlyPassAdditiveReview(t *testing.T) {
	m, roots := fixture(t)
	base := built(t, m, roots)
	head := cloneSnapshot(t, base, func(m *Manifest) {
		d := m.Datasets[1]
		d.ID = "primary/extra"
		m.Datasets = append(m.Datasets, d)
		in := m.Jobs[0].Inputs[0]
		in.Dataset = d.ID
		m.Jobs[0].Inputs = append(m.Jobs[0].Inputs, in)
	})
	r, err := Compare(base, head, Policy{Mode: "additive"})
	if err != nil || r.Status != "unknown" || !hasFinding(r, "added_input") {
		t.Fatalf("additional join = %+v, %v", r, err)
	}
}
