package dipipelines

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// LoadBoundarySuite loads the declared batches with their recorded byte digests.
func LoadBoundarySuite(dir string) (BoundarySuite, error) {
	var suite BoundarySuite
	b, err := boundedBoundaryFile(filepath.Join(dir, "suite.json"), 64<<20)
	if err != nil {
		return suite, err
	}
	if err := json.Unmarshal(b, &suite); err != nil {
		return suite, err
	}
	if suite.Format != "q2-boundary-suite/v1" || suite.ScenarioLimit != 10 || !commitRE.MatchString(suite.Commit) || len(suite.Cases) > 0 {
		return suite, fmt.Errorf("require a versioned source-pinned boundary suite with separate batches")
	}
	for _, job := range suite.Jobs {
		if len(job.Scenarios) > 10 {
			return suite, fmt.Errorf("job %s exceeds ten scenarios", job.EntryPoint)
		}
	}
	for _, job := range suite.LogicalJobs {
		if len(job.Scenarios) > 10 {
			return suite, fmt.Errorf("logical job %s exceeds ten scenarios", job.ID)
		}
	}
	for _, batch := range suite.CaseBatches {
		if !safePath(batch.Path) || !strings.HasPrefix(batch.Path, "cases/") || batch.Count < 1 || batch.Count > 100 {
			return suite, fmt.Errorf("invalid comparison batch declaration")
		}
		b, err := boundedBoundaryFile(filepath.Join(dir, batch.Path), 16<<20)
		if err != nil {
			return suite, err
		}
		if hash(b) != batch.SHA256 {
			return suite, fmt.Errorf("comparison batch %s digest mismatch", batch.Path)
		}
		var cases []ComparisonCase
		if err := json.Unmarshal(b, &cases); err != nil {
			return suite, err
		}
		if len(cases) != batch.Count {
			return suite, fmt.Errorf("comparison batch count mismatch")
		}
		suite.Cases = append(suite.Cases, cases...)
		if len(suite.Cases) > 50000 {
			return suite, fmt.Errorf("suite exceeds 50000 clause cases")
		}
	}
	if err := validatePropertyReplay(suite); err != nil {
		return suite, err
	}
	return suite, nil
}

func boundedBoundaryFile(path string, limit int64) ([]byte, error) {
	info, err := os.Stat(path)
	if err != nil {
		return nil, err
	}
	if info.Size() > limit {
		return nil, fmt.Errorf("boundary artifact %s exceeds %d bytes", path, limit)
	}
	return os.ReadFile(path)
}
