package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strconv"
	"strings"

	"github.com/jeisenman/q2_bench/workflows/formalmethod"
)

func propertySuiteCommand(ctx context.Context, args []string) error {
	flags := flag.NewFlagSet("formal-method property-suite", flag.ContinueOnError)
	suitePath := flags.String("suite", "", "source-pinned boundary suite directory")
	output := flags.String("output", "", "property suite directory")
	seedsText := flags.String("seeds", "1,42,20261102", "comma-separated reproducible unsigned seeds")
	samples := flags.Int("samples", 32, "additional sample rows per input table per seed")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if flags.NArg() != 0 || *suitePath == "" || *output == "" || *suitePath == *output {
		return fmt.Errorf("provide --suite and a different --output directory without positional arguments")
	}
	config := formalmethod.PropertyConfig{SamplesPerTable: *samples}
	for _, value := range strings.Split(*seedsText, ",") {
		seed, err := strconv.ParseUint(strings.TrimSpace(value), 10, 64)
		if err != nil {
			return fmt.Errorf("invalid property seed %q: %w", value, err)
		}
		config.Seeds = append(config.Seeds, seed)
	}
	suite, err := formalmethod.LoadBoundarySuite(*suitePath)
	if err != nil {
		return err
	}
	generated, err := formalmethod.GeneratePropertySuite(ctx, suite, config)
	if err != nil {
		return err
	}
	if err := formalmethod.WriteBoundarySuite(*output, generated); err != nil {
		return err
	}
	return json.NewEncoder(os.Stdout).Encode(map[string]any{
		"output": *output, "boundary_examples": len(suite.Cases),
		"seeded_property_instances": len(generated.Cases) - len(suite.Cases),
		"seeds":                     config.Seeds, "additional_rows_per_table": config.SamplesPerTable,
		"property":         "go_spark_output_bag_and_columns_equivalence",
		"execution_status": "unexecuted", "whole_job_passes": 0,
	})
}
