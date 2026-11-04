// Command agentbench is the Go-first CLI for the Q2 agent SDK.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"sort"

	"github.com/jeisenman/q2_bench/agents"
	"github.com/jeisenman/q2_bench/workflows/semanticsync"
)

const version = "0.1.0"

func main() {
	if err := run(context.Background(), os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run(ctx context.Context, arguments []string) error {
	if len(arguments) == 0 {
		printHelp()
		return nil
	}
	switch arguments[0] {
	case "help", "-h", "--help":
		printHelp()
		return nil
	case "version", "--version":
		fmt.Println(version)
		return nil
	case "agents":
		return listAgents()
	case "semantic-sync":
		return semanticSync(arguments[1:])
	case "lineage":
		return lineageCommand(ctx, arguments[1:])
	case "formal-method":
		return formalMethodCommand(ctx, arguments[1:])
	case "formal-lineage":
		return formalLineageCommand(ctx, arguments[1:])
	default:
		return fmt.Errorf("unsupported agentbench command %q", arguments[0])
	}
}

func semanticSync(arguments []string) error {
	flags := flag.NewFlagSet("semantic-sync", flag.ContinueOnError)
	flags.SetOutput(os.Stderr)
	researcherRoot := flags.String(
		"researcher-root",
		"../researcher",
		"path to the Researcher checkout",
	)
	generation := flags.String(
		"generation",
		"",
		"explicit Researcher generation directory; defaults to latest complete",
	)
	output := flags.String(
		"output",
		"var/lineage/di-pipelines.json",
		"staged semantic lineage graph",
	)
	dryRun := flags.Bool("dry-run", false, "validate without replacing the staged graph")
	if err := flags.Parse(arguments); err != nil {
		return err
	}
	if flags.NArg() != 0 {
		return fmt.Errorf("semantic-sync does not accept positional arguments")
	}
	var (
		inputs semanticsync.Inputs
		err    error
	)
	if *generation == "" {
		inputs, err = semanticsync.DiscoverLatest(*researcherRoot)
	} else {
		inputs, err = semanticsync.InputsForGeneration(*researcherRoot, *generation)
	}
	if err != nil {
		return err
	}
	receipt, err := semanticsync.Sync(inputs, *output, *dryRun)
	if err != nil {
		return err
	}
	encoded, err := json.Marshal(receipt)
	if err != nil {
		return fmt.Errorf("encode semantic sync receipt: %w", err)
	}
	fmt.Println(string(encoded))
	return nil
}

func listAgents() error {
	registry := agents.NewRegistry()
	factories := map[string]agents.Factory{
		"benchmark-builder":   func() agents.Agent { return agents.NewBenchmarkBuilder() },
		"data-creator":        func() agents.Agent { return agents.NewDataCreator() },
		"data-finder":         func() agents.Agent { return agents.NewDataFinder() },
		"data-insight-triage": func() agents.Agent { return agents.NewDataInsightTriage() },
		"etl":                 func() agents.Agent { return agents.NewETL() },
		"kpo-sizer":           func() agents.Agent { return agents.NewKPOSizer() },
	}
	names := make([]string, 0, len(factories))
	for name := range factories {
		names = append(names, name)
	}
	sort.Strings(names)
	for _, name := range names {
		if err := registry.Register(name, factories[name]); err != nil {
			return err
		}
		agent, err := registry.Create(name)
		if err != nil {
			return err
		}
		definition := agent.Definition()
		fmt.Printf("%s\tv%s\t%s\n", definition.Name, definition.Version, definition.Description)
	}
	return nil
}

func printHelp() {
	fmt.Print(`Manage Q2 data-engineering agents and benchmarks.

Usage:
  agentbench agents
  agentbench formal-method compile|evaluate|inventory [options]
  agentbench formal-lineage projects|parse|dependencies|di-pipelines [options]
  agentbench formal-lineage environments|check-environments [options]
  agentbench lineage build|compare|check-pr|backfill|show [options]
  agentbench semantic-sync [--researcher-root PATH] [--generation PATH]
                           [--output PATH] [--dry-run]
  agentbench version

Go owns provider-neutral contracts, deterministic agents, memory, Airflow,
OMS, Resource Discovery, production-support policy, and MCP APIs.
Databricks execution is available through the remote-data MCP server. The
semantic-sync command stages Researcher's latest complete Semantic Layer
snapshot for the read-only lineage MCP.
`)
}
