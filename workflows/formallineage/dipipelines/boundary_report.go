package dipipelines

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// WriteBoundarySuite writes reviewable per-job plans and bounded execution batches.
// All files are runtime artifacts; regeneration uses immutable source evidence.
func WriteBoundarySuite(dir string, suite BoundarySuite) error {
	if dir == "" {
		return fmt.Errorf("provide an output directory for the boundary suite")
	}
	for _, sub := range []string{"jobs", "cases"} {
		if err := os.MkdirAll(filepath.Join(dir, sub), 0700); err != nil {
			return err
		}
	}
	index := "# Pipeline boundary suite\n\nSource commit: `" + suite.Commit + "`.\n\nAt most ten scenario families per implementation job. A scenario contains many rows and clause checks. All plans remain blocked until complete job fixtures and effect oracles execute.\n\nThe closure is conservative: unrelated functions in a referenced module can appear. Unresolved and external implementations remain visible.\n\nSee [summary](summary.json), [full machine-readable suite](suite.json), and the per-job index files below.\n\n"
	index += "Start with the [semantic lineage job index](logical-jobs.md); implementation plans also include repository jobs absent from that snapshot.\n\n"
	if suite.PropertyConfig != nil {
		index += fmt.Sprintf("Seeded property: full Go/Spark output row-bag and column-name equivalence. Seeds: `%v`; %d additional rows per input table per seed. Exact boundaries and empty cases remain. Replay is verified when loading. Sampling is not exhaustive and does not certify source business intent.\n\n", suite.PropertyConfig.Seeds, suite.PropertyConfig.SamplesPerTable)
	}
	logicalIndex := "# Semantic lineage job scenarios\n\nEach logical job has at most ten scenarios shared across its implementations. These are planned checks; whole-job execution remains blocked.\n\n"
	for _, job := range suite.LogicalJobs {
		logicalIndex += fmt.Sprintf("- `%s`: %d scenarios; %s. ", job.ID, len(job.Scenarios), job.Scope)
		for _, entry := range job.Implementations {
			logicalIndex += fmt.Sprintf("[%s](jobs/%s.md) ", entry, hash([]byte(entry)))
		}
		logicalIndex += "\n"
	}
	if err := os.WriteFile(filepath.Join(dir, "logical-jobs.md"), []byte(logicalIndex), 0600); err != nil {
		return err
	}
	// Chunk the index to respect the repository's 400-line document bound.
	for offset := 0; offset < len(suite.Jobs); offset += 100 {
		end := min(offset+100, len(suite.Jobs))
		name := fmt.Sprintf("index-%03d.md", offset/100)
		index += fmt.Sprintf("- [Jobs %d–%d](%s)\n", offset+1, end, name)
		page := "# Job plans\n\n"
		for _, job := range suite.Jobs[offset:end] {
			id := hash([]byte(job.EntryPoint))
			page += fmt.Sprintf("- [%s](jobs/%s.md): %d scenarios; %d source clauses; blocked.\n", job.EntryPoint, id, len(job.Scenarios), len(job.Clauses))
			if err := writeBoundaryJSON(filepath.Join(dir, "jobs", id+".json"), job); err != nil {
				return err
			}
			text := jobBoundaryMarkdown(job, id)
			if err := os.WriteFile(filepath.Join(dir, "jobs", id+".md"), []byte(text), 0600); err != nil {
				return err
			}
		}
		if err := os.WriteFile(filepath.Join(dir, name), []byte(page), 0600); err != nil {
			return err
		}
	}
	for offset := 0; offset < len(suite.Cases); offset += 100 {
		end := min(offset+100, len(suite.Cases))
		name := fmt.Sprintf("cases/batch-%03d.json", offset/100)
		encoded, err := json.Marshal(suite.Cases[offset:end])
		if err != nil {
			return err
		}
		encoded = append(encoded, '\n')
		if err := os.WriteFile(filepath.Join(dir, name), encoded, 0600); err != nil {
			return err
		}
		suite.CaseBatches = append(suite.CaseBatches, BoundaryBatch{Path: name, SHA256: hash(encoded), Count: end - offset})
	}
	if err := os.WriteFile(filepath.Join(dir, "README.md"), []byte(index), 0600); err != nil {
		return err
	}
	if err := writeBoundaryJSON(filepath.Join(dir, "summary.json"), BoundarySummary(suite)); err != nil {
		return err
	}
	if err := writeBoundaryJSON(filepath.Join(dir, "clauses.json"), suite.Clauses); err != nil {
		return err
	}
	// Cases are already retained in bounded batch files.
	suite.Cases = nil
	return writeBoundaryJSON(filepath.Join(dir, "suite.json"), suite)
}

func writeBoundaryJSON(path string, value any) error {
	b, err := json.Marshal(value)
	if err != nil {
		return err
	}
	return os.WriteFile(path, append(b, '\n'), 0600)
}

func jobBoundaryMarkdown(job BoundaryJob, id string) string {
	text := "# " + job.EntryPoint + "\n\nStatus: **planned; whole-job execution blocked**.\n\n"
	text += fmt.Sprintf("%d source clauses in %d modules; %d source units; %d semantic lineage jobs; %d attached copy declarations.\n\n", len(job.Clauses), len(job.Sources), len(job.UnitIDs), len(job.LineageIDs), len(job.Copies))
	text += "[Job bindings, clause IDs, and unresolved gaps](" + id + ".json). Resolve IDs in the [shared clause catalog](../clauses.json). Each scenario selects this job's clauses whose `families` includes its `clause_family`. Source modules include conservative helper closure.\n\n"
	if split := strings.LastIndex(job.EntryPoint, "."); split > 0 {
		module := job.EntryPoint[:split]
		shown := 0
		for _, c := range job.Clauses {
			if moduleFromPath(c.Source.Path) != module || !in(c.Kind, "comparison", "filter", "join", "drop", "dropna") || shown >= 10 {
				continue
			}
			if shown == 0 {
				text += "## Examples from this implementation\n\nThese examples supplement the complete shared clause catalog.\n\n"
			}
			expression := strings.Join(strings.Fields(c.Expression), " ")
			if len(expression) > 220 {
				expression = expression[:220] + "… (excerpt)"
			}
			text += fmt.Sprintf("- Line %d: `%s`\n", c.Line, strings.ReplaceAll(expression, "`", "'"))
			shown++
		}
		if shown > 0 {
			text += "\n"
		}
	}
	for i, scenario := range job.Scenarios {
		text += fmt.Sprintf("## %d. %s\n\n", i+1, scenario.Title)
		check := scenarioCheck(BoundaryClause{}, scenario.ID)
		given := strings.TrimPrefix(check.Given, "At :0 (): ")
		text += given + "\n\n" + check.Assert + "\n\n"
		text += fmt.Sprintf("Source-specific checks: %d; additional context checks: %d. Status: %s.\n\n", scenario.ClauseChecks, len(scenario.Checks), scenario.Status)
	}
	return text
}
