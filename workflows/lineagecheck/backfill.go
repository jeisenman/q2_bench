package lineagecheck

import (
	"fmt"
	"sort"
	"time"
)

// ReplayRun describes one reviewed DAG task invocation, including disabled work.
type ReplayRun struct {
	ClientID string     `json:"client_id"`
	Job      string     `json:"job"`
	Enabled  bool       `json:"enabled"`
	Reason   string     `json:"reason,omitempty"`
	From     string     `json:"from"`
	Until    string     `json:"until"`
	After    []string   `json:"after"`
	Replay   Replay     `json:"replay"`
	Evidence []Evidence `json:"evidence"`
}

// BackfillPlan binds a repaired column/date scope to a pinned replay graph.
type BackfillPlan struct {
	ClientID   string      `json:"client_id"`
	SnapshotID string      `json:"snapshot_id"`
	Dataset    string      `json:"dataset"`
	Columns    []string    `json:"columns"`
	From       string      `json:"from"`
	Until      string      `json:"until"`
	Runs       []ReplayRun `json:"runs"`
}

// CheckBackfill compares column impact with replay coverage, ordering, and windows.
func CheckBackfill(s Snapshot, p BackfillPlan) (Report, error) {
	if p.ClientID == "" || len(p.Runs) > 500 {
		return Report{}, fmt.Errorf("backfill requires a client ID and at most 500 replay jobs")
	}
	if err := ValidateSnapshot(s); err != nil {
		return Report{}, err
	}
	if p.SnapshotID != s.ID {
		return Report{}, fmt.Errorf("backfill plan must pin the selected snapshot ID")
	}
	datasets, jobs := indexes(s.Manifest)
	root, ok := datasets[p.Dataset]
	if !ok {
		return Report{}, fmt.Errorf("backfill root dataset %q does not exist", p.Dataset)
	}
	from, until, err := dateRange(p.From, p.Until)
	if err != nil {
		return Report{}, err
	}
	columns := p.Columns
	if len(columns) == 0 {
		for _, f := range root.Fields {
			columns = append(columns, f.Name)
		}
	}
	if err := unique(columns); err != nil {
		return Report{}, err
	}
	affected := map[FieldRef]bool{}
	for _, name := range columns {
		if _, ok := field(root, name); !ok {
			return Report{}, fmt.Errorf("backfill column %s.%s does not exist", root.ID, name)
		}
		affected[FieldRef{root.ID, name}] = true
	}
	r := newReport(s)
	required := map[string]bool{}
	changed := true
	for changed {
		changed = false
		for _, j := range s.Manifest.Jobs {
			touched, rowChange := false, false
			for _, in := range j.Inputs {
				for _, f := range in.Fields {
					touched = touched || affected[FieldRef{in.Dataset, f}]
				}
				for _, f := range in.Keys {
					if affected[FieldRef{in.Dataset, f}] {
						touched = true
						rowChange = true
					}
				}
			}
			if !touched {
				continue
			}
			if !required[j.ID] {
				required[j.ID] = true
				if !j.ColumnsComplete {
					r.add("unknown", "column_coverage", j.ID, "column dependencies are incomplete; all outputs are conservatively affected")
				}
			}
			mark := func(ref FieldRef) {
				if !affected[ref] {
					affected[ref] = true
					changed = true
				}
			}
			if !j.ColumnsComplete || rowChange {
				for _, id := range j.Outputs {
					for _, f := range datasets[id].Fields {
						mark(FieldRef{id, f.Name})
					}
				}
			} else {
				for _, dep := range j.Dependencies {
					for _, ref := range dep.Inputs {
						if affected[ref] {
							mark(dep.Output)
							break
						}
					}
				}
			}
		}
	}
	evidence := map[Evidence]bool{}
	for _, j := range s.Manifest.Jobs {
		for _, e := range j.Evidence {
			evidence[e] = true
		}
	}
	runs := map[string]ReplayRun{}
	runJobs := map[string]Job{}
	for _, run := range p.Runs {
		if jobs[run.Job].ID == "" || runs[run.Job].Job != "" {
			return Report{}, fmt.Errorf("unknown or duplicate replay job %q", run.Job)
		}
		if len(run.Evidence) == 0 {
			return Report{}, fmt.Errorf("replay job %s requires source evidence pinned in the snapshot", run.Job)
		}
		for _, e := range run.Evidence {
			if !evidence[e] {
				return Report{}, fmt.Errorf("replay job %s has unpinned source evidence", run.Job)
			}
		}
		if err := unique(run.After); err != nil {
			return Report{}, err
		}
		if run.Enabled {
			if run.Replay.ClientScope == "single_client" && run.ClientID != p.ClientID {
				return Report{}, fmt.Errorf("replay job %s targets a different client", run.Job)
			}
			if err := validateReplay(run.Replay); err != nil {
				return Report{}, err
			}
			if _, _, err := dateRange(run.From, run.Until); err != nil {
				return Report{}, err
			}
		} else if run.Reason == "" {
			return Report{}, fmt.Errorf("disabled replay job %s requires a reason", run.Job)
		}
		runs[run.Job] = run
		runJobs[run.Job] = Job{ID: run.Job, After: run.After}
		if run.Enabled && !required[run.Job] {
			r.add("info", "extra_replay", run.Job, "enabled replay is outside the affected column closure")
		}
	}
	for _, run := range p.Runs {
		for _, id := range run.After {
			if runs[id].Job == "" {
				return Report{}, fmt.Errorf("replay predecessor %s is absent", id)
			}
			if run.Enabled && !runs[id].Enabled {
				r.add("error", "disabled_predecessor", run.Job, "enabled replay depends on a disabled predecessor: "+id)
			}
		}
	}
	if err := acyclic(runJobs); err != nil {
		return Report{}, err
	}
	for _, j := range s.Manifest.Jobs {
		if !required[j.ID] {
			continue
		}
		r.RequiredJobs = append(r.RequiredJobs, j.ID)
		run, exists := runs[j.ID]
		if !exists || !run.Enabled {
			message := "affected job is absent from the replay graph"
			if exists {
				message = "affected job is disabled: " + run.Reason
			}
			r.add("error", "missing_replay", j.ID, message)
			continue
		}
		if run.Replay != j.Replay {
			r.add("error", "replay_contract", j.ID, "mode, UTC window hour, forced replay, schedule override, replace writes, or client scope differs from the required contract")
		}
		rf, ru, _ := dateRange(run.From, run.Until)
		needFrom, needUntil := from, until
		if j.Replay.Mode == "month_end" {
			needFrom = monthEnd(from)
			needUntil = monthEnd(until)
		}
		if !rf.Equal(needFrom) || !ru.Equal(needUntil) {
			r.add("error", "replay_dates", j.ID, "replay dates must match the required historical output date range")
		}
	}
	// Data dependencies also impose ordering even if a manifest omitted After.
	ordering := map[string]Job{}
	for id, j := range jobs {
		j.After = append([]string{}, j.After...)
		ordering[id] = j
	}
	for id, j := range ordering {
		for _, in := range j.Inputs {
			for _, producer := range s.Manifest.Jobs {
				if producer.ID != id && contains(producer.Outputs, in.Dataset) && !contains(j.After, producer.ID) {
					j.After = append(j.After, producer.ID)
				}
			}
		}
		ordering[id] = j
	}
	for _, to := range r.RequiredJobs {
		baselineAncestors := ancestors(ordering, to)
		replayAncestors := ancestors(runJobs, to)
		for _, pre := range r.RequiredJobs {
			if pre == to || !baselineAncestors[pre] || !runs[to].Enabled || !runs[pre].Enabled {
				continue
			}
			if !replayAncestors[pre] {
				r.add("error", "replay_order", to, "must run after affected producer "+pre)
			}
		}
	}
	for ref := range affected {
		r.Affected = append(r.Affected, ref)
	}
	sort.Slice(r.Affected, func(i, j int) bool { return refKey(r.Affected[i]) < refKey(r.Affected[j]) })
	r.finish()
	return r, nil
}

func dateRange(from, until string) (time.Time, time.Time, error) {
	f, err := time.Parse("2006-01-02", from)
	if err != nil {
		return time.Time{}, time.Time{}, fmt.Errorf("from must be an ISO date: %w", err)
	}
	u, err := time.Parse("2006-01-02", until)
	if err != nil || u.Before(f) {
		return time.Time{}, time.Time{}, fmt.Errorf("until must be an ISO date on or after from")
	}
	if u.Sub(f) > 3660*24*time.Hour {
		return time.Time{}, time.Time{}, fmt.Errorf("backfill window exceeds ten years")
	}
	return f, u, nil
}

func monthEnd(d time.Time) time.Time {
	return time.Date(d.Year(), d.Month()+1, 0, 0, 0, 0, 0, time.UTC)
}
