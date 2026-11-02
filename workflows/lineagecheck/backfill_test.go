package lineagecheck

import "testing"

func TestUSBankReplayDetectsWindowMonthlyAndDisabledDescendant(t *testing.T) {
	m, roots := fixture(t)
	copy := m.Datasets[1]
	copy.ID = "client/deposits"
	m.Datasets = append(m.Datasets, copy)
	monthly := copy
	monthly.ID = "derived/monthly"
	m.Datasets = append(m.Datasets, monthly)
	for _, spec := range []struct{ id, out, mode string }{{"copy", "client/deposits", "partition"}, {"monthly", "derived/monthly", "month_end"}, {"loc", "derived/loc", "cross_client"}} {
		if spec.id == "loc" {
			d := copy
			d.ID = spec.out
			m.Datasets = append(m.Datasets, d)
		}
		j := Job{ID: spec.id, DAG: "us_bank_replay", Inputs: []Input{{Dataset: "derived/deposits", Major: 3, Fields: []string{"CoreAccountId", "DatePartition", "NaicsCode"}, Keys: []string{"CoreAccountId", "DatePartition"}}}, Outputs: []string{spec.out}, After: []string{"derive"}, ColumnsComplete: true, Replay: m.Jobs[0].Replay, Evidence: m.Jobs[0].Evidence}
		j.Replay.Mode = spec.mode
		if spec.mode == "cross_client" {
			j.Replay.ClientScope = "cross_client"
		}
		for _, name := range []string{"CoreAccountId", "DatePartition", "NaicsCode"} {
			j.Dependencies = append(j.Dependencies, Dependency{FieldRef{spec.out, name}, []FieldRef{{"derived/deposits", name}}})
		}
		m.Jobs = append(m.Jobs, j)
	}
	s := built(t, m, roots)
	p := plan(s)
	p.Runs = nil
	for _, j := range s.Manifest.Jobs {
		run := ReplayRun{ClientID: p.ClientID, Job: j.ID, Enabled: true, From: p.From, Until: p.Until, After: j.After, Replay: j.Replay, Evidence: j.Evidence}
		if j.ID == "monthly" {
			run.From = "2026-01-31"
			run.Until = "2026-02-28"
		}
		p.Runs = append(p.Runs, run)
	}
	r, err := CheckBackfill(s, p)
	if err != nil || r.Status != "pass" || len(r.RequiredJobs) != 4 {
		t.Fatalf("complete = %+v, %v", r, err)
	}
	for i := range p.Runs {
		switch p.Runs[i].Job {
		case "derive":
			p.Runs[i].Replay.HourUTC = 0
			p.Runs[i].Replay.Force = false
		case "monthly":
			p.Runs[i].Until = p.Until
			p.Runs[i].Replay.BypassSchedule = !p.Runs[i].Replay.BypassSchedule
		case "loc":
			p.Runs[i].Enabled = false
			p.Runs[i].Reason = "production DAG remains paused"
		case "copy":
			p.Runs[i].After = nil
		}
	}
	r, err = CheckBackfill(s, p)
	if err != nil || r.Status != "fail" {
		t.Fatalf("incomplete = %+v, %v", r, err)
	}
	for _, code := range []string{"replay_contract", "replay_dates", "missing_replay", "replay_order"} {
		if !hasFinding(r, code) {
			t.Errorf("missing %s: %+v", code, r)
		}
	}
}

func TestBackfillUnknownDependenciesConservativelyPropagate(t *testing.T) {
	m, roots := fixture(t)
	m.Jobs[0].ColumnsComplete = false
	m.Jobs[0].Dependencies = nil
	s := built(t, m, roots)
	p := plan(s)
	r, err := CheckBackfill(s, p)
	if err != nil || r.Status != "unknown" || len(r.Affected) != 4 {
		t.Fatalf("unknown = %+v, %v", r, err)
	}
	p.SnapshotID = "stale"
	if _, err := CheckBackfill(s, p); err == nil {
		t.Fatal("stale plan accepted")
	}
	p = plan(s)
	p.Columns = []string{"Absent"}
	if _, err := CheckBackfill(s, p); err == nil {
		t.Fatal("unknown column accepted")
	}
	p = plan(s)
	p.From = "2026-03-01"
	if _, err := CheckBackfill(s, p); err == nil {
		t.Fatal("reversed dates accepted")
	}
	p = plan(s)
	p.Runs[0].Evidence = nil
	if _, err := CheckBackfill(s, p); err == nil {
		t.Fatal("missing replay evidence accepted")
	}
}

func TestBackfillJoinKeyChangesAffectAllOutputRows(t *testing.T) {
	m, roots := fixture(t)
	s := built(t, m, roots)
	p := plan(s)
	p.Columns = []string{"CoreAccountId"}
	r, err := CheckBackfill(s, p)
	if err != nil || r.Status != "pass" || len(r.Affected) != 4 {
		t.Fatalf("row propagation = %+v, %v", r, err)
	}
	p.Runs = nil
	r, err = CheckBackfill(s, p)
	if err != nil || !hasFinding(r, "missing_replay") {
		t.Fatalf("missing = %+v, %v", r, err)
	}
}
