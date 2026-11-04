package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"github.com/jeisenman/q2_bench/workflows/formallineage/calculationengine"
	"github.com/jeisenman/q2_bench/workflows/formallineage/dataingress"
	"github.com/jeisenman/q2_bench/workflows/formallineage/discovery"
	"github.com/jeisenman/q2_bench/workflows/formallineage/model"
	"github.com/jeisenman/q2_bench/workflows/formallineage/projects"
	"github.com/jeisenman/q2_bench/workflows/formallineage/radar"
	"github.com/jeisenman/q2_bench/workflows/formallineage/source"
	"os"
)

func formalLineageCommand(ctx context.Context, args []string) error {
	if len(args) == 0 {
		return fmt.Errorf("formal-lineage requires projects, environments, check-environments, parse, dependencies or di-pipelines")
	}
	if args[0] == "environments" || args[0] == "check-environments" {
		return formalEnvironmentsCommand(args)
	}
	if args[0] == "di-pipelines" {
		return formalMethodCommand(ctx, args[1:])
	}
	if args[0] == "projects" {
		if len(args) != 1 {
			return fmt.Errorf("projects accepts no arguments")
		}
		return writeLineageJSON("", projects.All())
	}
	if args[0] != "parse" && args[0] != "dependencies" {
		return fmt.Errorf("unknown formal-lineage command %q", args[0])
	}
	flags := flag.NewFlagSet("formal-lineage "+args[0], flag.ContinueOnError)
	project := flags.String("project", "", "project ID")
	repository := flags.String("repository", "", "repository name")
	root := flags.String("root", "", "local Git checkout")
	commit := flags.String("commit", "", "full immutable Git commit")
	file := flags.String("path", "", "repository-relative source path")
	output := flags.String("output", "", "optional JSON output file")
	if err := flags.Parse(args[1:]); err != nil {
		return err
	}
	if flags.NArg() != 0 {
		return fmt.Errorf("unexpected positional arguments")
	}
	if args[0] == "dependencies" {
		if *project != "pl-calculation-engine" || (*repository != "" && *repository != "pl-calculation-engine") || *file != "" {
			return fmt.Errorf("dependencies requires pl-calculation-engine project and no --path")
		}
		result, err := calculationengine.InventoryDependencies(ctx, *root, *commit)
		if err != nil {
			return err
		}
		if err := writeLineageJSON(*output, result); err != nil {
			return err
		}
		return fmt.Errorf("inventory written; complete dependency closure is unresolved (see unresolved)")
	}
	if err := projects.Allows(*project, *repository); err != nil {
		return err
	}
	content, err := source.ReadGit(ctx, *root, *commit, *file, 1<<20)
	if err != nil {
		return err
	}
	receipt, err := source.Receipt(*commit, *file, content)
	if err != nil {
		return err
	}
	var result model.ParsedFile
	switch *project {
	case "radar":
		result, err = radar.Parse(ctx, *repository, receipt, content)
	case "data-ingress":
		result, err = dataingress.Parse(ctx, *repository, receipt, content)
	case "pl-calculation-engine":
		result, err = calculationengine.Parse(ctx, *repository, receipt, content)
	case "di-pipelines":
		result, err = discovery.Parse(ctx, *project, *repository, receipt, content)
	default:
		return fmt.Errorf("project parser unavailable")
	}
	if err != nil {
		return err
	}
	if err := writeLineageJSON(*output, result); err != nil {
		return err
	}
	return fmt.Errorf("source catalog written; runtime lowering unresolved; prediction_ready=false")
}

func writeLineageJSON(file string, value any) error {
	b, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	b = append(b, '\n')
	if file == "" {
		_, err = os.Stdout.Write(b)
		return err
	}
	return os.WriteFile(file, b, 0o600)
}
