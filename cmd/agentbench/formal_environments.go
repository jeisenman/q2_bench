package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"

	"github.com/jeisenman/q2_bench/workflows/formallineage/projects"
)

func formalEnvironmentsCommand(args []string) error {
	if args[0] == "environments" {
		if len(args) != 1 {
			return fmt.Errorf("environments accepts no arguments")
		}
		return writeLineageJSON("", projects.Environments())
	}
	flags := flag.NewFlagSet("formal-lineage check-environments", flag.ContinueOnError)
	file := flags.String("bindings", "", "JSON array of provider-observed environment bindings")
	output := flags.String("output", "", "optional compatibility report JSON")
	if err := flags.Parse(args[1:]); err != nil {
		return err
	}
	if flags.NArg() != 0 || *file == "" {
		return fmt.Errorf("check-environments requires --bindings and no positional arguments")
	}
	f, err := os.Open(*file)
	if err != nil {
		return err
	}
	defer f.Close()
	info, err := f.Stat()
	if err != nil {
		return err
	}
	if info.Size() > 1<<20 {
		return fmt.Errorf("environment bindings exceed 1 MiB")
	}
	if !info.Mode().IsRegular() {
		return fmt.Errorf("environment bindings must be a regular JSON file")
	}
	decoder := json.NewDecoder(io.LimitReader(f, (1<<20)+1))
	decoder.DisallowUnknownFields()
	var bindings []projects.EnvironmentBinding
	if err := decoder.Decode(&bindings); err != nil {
		return err
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return fmt.Errorf("environment bindings require exactly one JSON document")
	}
	if err := projects.CheckEnvironmentBindings(bindings); err != nil {
		return err
	}
	variables := map[string]map[string]string{}
	for _, binding := range bindings {
		v, err := projects.EnvironmentVariables(binding)
		if err != nil {
			return err
		}
		variables[binding.ProfileID] = v
	}
	return writeLineageJSON(*output, struct {
		Format           string                       `json:"format"`
		Compatible       bool                         `json:"bindings_compatible"`
		RuntimeValidated bool                         `json:"runtime_validated"`
		Variables        map[string]map[string]string `json:"private_environment_variables"`
		Note             string                       `json:"note"`
	}{"q2-formal-environment-bindings/v1", true, false, variables, "Compatibility of supplied metadata only; provider identity, full dependencies and original-source execution require separate evidence."})
}
