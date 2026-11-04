package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strings"

	formalmethod "github.com/jeisenman/q2_bench/workflows/formallineage/dipipelines"
)

func boundaryEvidenceCommand(ctx context.Context, args []string, pending bool) error {
	flags := flag.NewFlagSet("formal-method boundary-evidence", flag.ContinueOnError)
	dir := flags.String("suite", "", "generated suite directory")
	paths := flags.String("results", "", "comma-separated Jobs API result files; select one observation per case")
	output := flags.String("output", "", "coverage report JSON")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if flags.NArg() != 0 || *dir == "" || *paths == "" || *output == "" {
		return fmt.Errorf("provide --suite, --results, and --output without positional arguments")
	}
	suite, err := formalmethod.LoadBoundarySuite(*dir)
	if err != nil {
		return err
	}
	observations := []formalmethod.ClauseObservation{}
	for _, path := range strings.Split(*paths, ",") {
		info, err := os.Stat(path)
		if err != nil {
			return err
		}
		if info.Size() > 32<<20 {
			return fmt.Errorf("Databricks result exceeds 32 MiB")
		}
		content, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		results, err := formalmethod.DecodeBoundaryObservations(content)
		if err != nil {
			return err
		}
		observations = append(observations, results...)
	}
	if pending {
		cases, err := formalmethod.PendingBoundaryCases(ctx, suite, observations)
		if err != nil {
			return err
		}
		b, err := json.Marshal(cases)
		if err != nil {
			return err
		}
		if err := os.WriteFile(*output, append(b, '\n'), 0600); err != nil {
			return err
		}
		return json.NewEncoder(os.Stdout).Encode(map[string]any{"pending_clause_cases": len(cases), "output": *output})
	}
	report, err := formalmethod.CheckBoundaryEvidence(ctx, suite, observations)
	if err != nil {
		return err
	}
	b, err := json.Marshal(report)
	if err != nil {
		return err
	}
	if err := os.WriteFile(*output, append(b, '\n'), 0600); err != nil {
		return err
	}
	if err := json.NewEncoder(os.Stdout).Encode(map[string]any{"status": report.Status, "expected_clause_cases": report.Expected, "passed_clause_cases": report.Passed, "failed_clause_cases": report.Failed, "unobserved_clause_cases": report.Missing, "historical_failures_outside_current_profile": len(report.Historical), "whole_job_passes": report.WholeJobPasses, "output": *output}); err != nil {
		return err
	}
	return fmt.Errorf("isolated clause evidence recorded; whole-job scenario coverage remains blocked")
}
