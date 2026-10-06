// Command agentbench is the Go-first CLI for the Q2 agent SDK.
package main

import (
	"context"
	"fmt"
	"os"
	"sort"

	"github.com/jeisenman/q2_bench/agents"
)

const version = "0.1.0"

func main() {
	if err := run(context.Background(), os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run(_ context.Context, arguments []string) error {
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
	default:
		return fmt.Errorf("unsupported agentbench command %q", arguments[0])
	}
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
  agentbench version

Go owns provider-neutral contracts, deterministic agents, memory, Airflow,
OMS, Resource Discovery, production-support policy, and MCP APIs.
Databricks execution is available through the remote-data MCP server.
`)
}
