package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"

	"github.com/jeisenman/q2_bench/workflows/formalmethod"
)

func boundaryCommand(ctx context.Context, args []string) error {
	flags := flag.NewFlagSet("formal-method "+args[0], flag.ContinueOnError)
	root := flags.String("root", "", "di-pipelines Git checkout")
	output := flags.String("output", "", "suite directory or prepared notebook path")
	graphPath, inventoryPath, casesPath, templatePath := new(string), new(string), new(string), new(string)
	if args[0] == "boundary-suite" {
		flags.StringVar(graphPath, "graph", "var/lineage/di-pipelines.json", "validated synchronized semantic graph")
		flags.StringVar(inventoryPath, "inventory", "", "optional inventory at exactly the graph commit")
	} else {
		flags.StringVar(casesPath, "cases", "", "one generated comparison batch")
		flags.StringVar(templatePath, "template", "", "reviewed Databricks comparison template")
	}
	if err := flags.Parse(args[1:]); err != nil {
		return err
	}
	if flags.NArg() != 0 || *root == "" || *output == "" {
		return fmt.Errorf("provide --root and --output; positional arguments are unsupported")
	}
	if args[0] == "prepare-boundary-comparison" {
		var cases []formalmethod.ComparisonCase
		if err := readFormalJSON(*casesPath, &cases); err != nil {
			return err
		}
		payload, err := formalmethod.PrepareComparison(ctx, *root, cases)
		if err != nil {
			return err
		}
		template, err := os.ReadFile(*templatePath)
		if err != nil {
			return err
		}
		notebook, err := payload.Notebook(string(template))
		if err != nil {
			return err
		}
		if err := os.WriteFile(*output, []byte(notebook), 0600); err != nil {
			return err
		}
		return json.NewEncoder(os.Stdout).Encode(map[string]any{"output": *output, "cases": len(cases)})
	}
	graph, err := os.ReadFile(*graphPath)
	if err != nil {
		return err
	}
	var inventory formalmethod.Inventory
	if *inventoryPath != "" {
		err = readFormalJSON(*inventoryPath, &inventory)
	} else {
		var pin string
		pin, err = formalmethod.DecodeBoundaryGraphPin(graph)
		if err == nil {
			inventory, err = formalmethod.InventoryGit(ctx, *root, pin)
		}
	}
	if err != nil {
		return err
	}
	suite, err := formalmethod.PlanBoundariesGit(ctx, *root, inventory, graph)
	if err != nil {
		return err
	}
	if err := formalmethod.WriteBoundarySuite(*output, suite); err != nil {
		return err
	}
	if err := json.NewEncoder(os.Stdout).Encode(formalmethod.BoundarySummary(suite)); err != nil {
		return err
	}
	return fmt.Errorf("boundary suite written; unexecuted scenarios and unresolved jobs block passing")
}
