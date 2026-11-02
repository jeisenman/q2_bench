package lineagecheck

import (
	"fmt"
	"reflect"
	"sort"
	"strings"
)

// Replacement permits one consumer to change a named input dataset.
type Replacement struct {
	Job             string            `json:"job"`
	From            string            `json:"from"`
	To              string            `json:"to"`
	Fields          map[string]string `json:"fields"`
	HistoryVerified bool              `json:"history_verified"`
	HistoryEvidence string            `json:"history_evidence"`
}

// Policy selects strict additive compatibility or explicit input replacements.
type Policy struct {
	Mode         string        `json:"mode"`
	Replacements []Replacement `json:"replacements"`
}

// Compare checks that an immutable candidate preserves its baseline contracts.
func Compare(base, head Snapshot, p Policy) (Report, error) {
	if err := ValidateSnapshot(base); err != nil {
		return Report{}, err
	}
	if err := ValidateSnapshot(head); err != nil {
		return Report{}, err
	}
	if !contains([]string{"additive", "replacement"}, p.Mode) || p.Mode == "additive" && len(p.Replacements) > 0 {
		return Report{}, fmt.Errorf("policy must be additive or replacement; additive forbids replacement entries")
	}
	r := newReport(head)
	r.BaseID = base.ID
	if base.Manifest.Scope != head.Manifest.Scope || base.Manifest.Profile != head.Manifest.Profile {
		return Report{}, fmt.Errorf("base and head must have identical scope and profile")
	}
	for _, u := range base.Manifest.Unresolved {
		r.add("unknown", "unresolved_baseline", base.ID, u)
	}
	bd, bj := indexes(base.Manifest)
	hd, hj := indexes(head.Manifest)
	allowed := map[string]Replacement{}
	for _, v := range p.Replacements {
		key := v.Job + "\x00" + v.From
		if v.From == v.To || v.From == "" || v.To == "" || v.Job == "" || allowed[key].Job != "" || bj[v.Job].ID == "" || hj[v.Job].ID == "" || bd[v.From].ID == "" || hd[v.To].ID == "" {
			return Report{}, fmt.Errorf("invalid or duplicate replacement for job %s input %s", v.Job, v.From)
		}
		for from, to := range v.Fields {
			if from == "" || to == "" {
				return Report{}, fmt.Errorf("replacement field mappings must be nonempty")
			}
		}
		allowed[key] = v
	}
	used := map[string]bool{}
	for _, old := range base.Manifest.Datasets {
		next, ok := hd[old.ID]
		if !ok {
			r.add("error", "removed_dataset", old.ID, "existing dataset must remain available; retire it in a separate migration after checking all consumers")
			continue
		}
		if old.Major != next.Major || next.Minor < old.Minor || old.Partition != next.Partition || !reflect.DeepEqual(old.Keys, next.Keys) {
			r.add("error", "dataset_contract", old.ID, "major version, keys, or partition changed, or minor version decreased")
		}
		for _, f := range old.Fields {
			nf, ok := field(next, f.Name)
			if !ok || f != nf {
				r.add("error", "field_contract", old.ID+"."+f.Name, "existing field was removed or its type/nullability changed")
			}
		}
	}
	for _, old := range base.Manifest.Jobs {
		next, ok := hj[old.ID]
		if !ok {
			r.add("error", "removed_job", old.ID, "existing producer/consumer job was removed")
			continue
		}
		if old.DAG != next.DAG {
			r.add("error", "job_dag", old.ID, "existing job changed its owning DAG")
		}
		for _, in := range next.Inputs {
			if findInput(old, in.Dataset) != nil {
				continue
			}
			declared := false
			for _, replacement := range p.Replacements {
				if replacement.Job == old.ID && replacement.To == in.Dataset {
					declared = true
				}
			}
			if !declared {
				r.add("unknown", "added_input", old.ID, "new input may affect existing rows and needs a replacement or separately reviewed transformation contract: "+in.Dataset)
			}
		}
		for _, id := range old.Outputs {
			if !contains(next.Outputs, id) {
				r.add("error", "removed_output", old.ID, id)
			}
		}
		if old.Replay != next.Replay {
			r.add("error", "replay_contract", old.ID, "historical replay behavior changed")
		}
		if !old.ColumnsComplete || !next.ColumnsComplete {
			r.add("unknown", "column_coverage", old.ID, "complete column dependencies are required for compatibility certification")
		}
		for _, pre := range old.After {
			if !precedes(hj, pre, old.ID) {
				r.add("error", "lost_ordering", old.ID, "required predecessor lost: "+pre)
			}
		}
		for _, in := range old.Inputs {
			repl, replace := allowed[old.ID+"\x00"+in.Dataset]
			target := in.Dataset
			if replace {
				target = repl.To
				used[old.ID+"\x00"+in.Dataset] = true
				if !repl.HistoryVerified || strings.TrimSpace(repl.HistoryEvidence) == "" {
					r.add("unknown", "replacement_history", old.ID, "replacement historical availability needs verification evidence")
				}
				if findInput(next, in.Dataset) != nil {
					r.add("error", "unused_replacement", old.ID, "declared old input is still consumed")
				}
			}
			ni := findInput(next, target)
			if ni == nil {
				r.add("error", "removed_input", old.ID, in.Dataset+" has no declared compatible successor")
				continue
			}
			if !replace && in.Major != ni.Major {
				r.add("error", "input_version", old.ID, in.Dataset+" major version changed")
			}
			for _, name := range append(append([]string{}, in.Fields...), in.Keys...) {
				mapped := mapField(name, repl)
				f, _ := field(bd[in.Dataset], name)
				nf, exists := field(hd[target], mapped)
				if !exists || f.Type != nf.Type || f.Nullable != nf.Nullable || !contains(append(append([]string{}, ni.Fields...), ni.Keys...), mapped) {
					r.add("error", "incompatible_input_column", old.ID, in.Dataset+"."+name+" is not preserved by "+target+"."+mapped)
				}
			}
			mappedKeys := []string{}
			for _, key := range in.Keys {
				mappedKeys = append(mappedKeys, mapField(key, repl))
			}
			sort.Strings(mappedKeys)
			if !sameStrings(mappedKeys, ni.Keys) {
				r.add("error", "join_keys", old.ID, "replacement does not preserve input join keys for "+in.Dataset)
			}
		}
		compareDependencies(&r, old, next, allowed)
	}
	for key, v := range allowed {
		if !used[key] {
			return Report{}, fmt.Errorf("replacement for %s/%s does not match a baseline input", v.Job, v.From)
		}
	}
	r.finish()
	return r, nil
}

func compareDependencies(r *Report, old, next Job, replacements map[string]Replacement) {
	for _, dep := range old.Dependencies {
		var candidate *Dependency
		for i := range next.Dependencies {
			if next.Dependencies[i].Output == dep.Output {
				candidate = &next.Dependencies[i]
				break
			}
		}
		if candidate == nil {
			r.add("error", "lost_column_lineage", old.ID, dep.Output.Dataset+"."+dep.Output.Field)
			continue
		}
		mapped := make([]FieldRef, 0, len(dep.Inputs))
		for _, ref := range dep.Inputs {
			if v, ok := replacements[old.ID+"\x00"+ref.Dataset]; ok {
				ref = FieldRef{v.To, mapField(ref.Field, v)}
			}
			mapped = append(mapped, ref)
		}
		sort.Slice(mapped, func(i, j int) bool { return refKey(mapped[i]) < refKey(mapped[j]) })
		if !reflect.DeepEqual(mapped, candidate.Inputs) && !(len(mapped) == 0 && len(candidate.Inputs) == 0) {
			r.add("error", "changed_column_lineage", old.ID, "unapproved dependency change for "+dep.Output.Dataset+"."+dep.Output.Field)
		}
	}
}

func mapField(name string, r Replacement) string {
	if mapped, ok := r.Fields[name]; ok {
		return mapped
	}
	return name
}
func findInput(j Job, id string) *Input {
	for i := range j.Inputs {
		if j.Inputs[i].Dataset == id {
			return &j.Inputs[i]
		}
	}
	return nil
}
func indexes(m Manifest) (map[string]Dataset, map[string]Job) {
	ds := map[string]Dataset{}
	js := map[string]Job{}
	for _, d := range m.Datasets {
		ds[d.ID] = d
	}
	for _, j := range m.Jobs {
		js[j.ID] = j
	}
	return ds, js
}
func newReport(s Snapshot) Report {
	r := Report{Scope: s.Manifest.Scope, HeadID: s.ID, Affected: []FieldRef{}, RequiredJobs: []string{}, Findings: []Finding{}}
	for _, u := range s.Manifest.Unresolved {
		r.add("unknown", "unresolved_source", s.ID, u)
	}
	return r
}
func precedes(jobs map[string]Job, from, to string) bool {
	return ancestors(jobs, to)[from]
}

func ancestors(jobs map[string]Job, to string) map[string]bool {
	seen := map[string]bool{}
	queue := append([]string{}, jobs[to].After...)
	for len(queue) > 0 {
		id := queue[0]
		queue = queue[1:]
		if seen[id] {
			continue
		}
		seen[id] = true
		queue = append(queue, jobs[id].After...)
	}
	return seen
}
func sameStrings(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}
