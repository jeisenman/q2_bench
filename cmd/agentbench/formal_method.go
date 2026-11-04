package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"strings"

	formalmethod "github.com/jeisenman/q2_bench/workflows/formallineage/dipipelines"
)

func formalMethodCommand(ctx context.Context, args []string) error {
	if len(args) > 0 && args[0] == "property-suite" {
		return propertySuiteCommand(ctx, args[1:])
	}
	if len(args) > 0 && (args[0] == "boundary-evidence" || args[0] == "boundary-pending") {
		return boundaryEvidenceCommand(ctx, args[1:], args[0] == "boundary-pending")
	}
	if len(args) > 0 && (args[0] == "boundary-suite" || args[0] == "prepare-boundary-comparison") {
		return boundaryCommand(ctx, args)
	}
	if len(args) == 0 {
		return fmt.Errorf("formal-method requires compile, evaluate, inventory, interface or prepare-comparison")
	}
	flags := flag.NewFlagSet("formal-method "+args[0], flag.ContinueOnError)
	root := flags.String("root", "", "source Git checkout")
	commit := flags.String("commit", "", "full source commit")
	path := flags.String("path", "", "relative Python source path")
	function := flags.String("function", "", "qualified function name")
	entrypoint := flags.String("entrypoint", "", "qualified job class for metadata interface")
	inventoryPath := flags.String("inventory", "", "pinned unit inventory JSON")
	tables := flags.String("tables", "", "comma-separated table parameter names")
	method := flags.String("method", "", "compiled method JSON")
	bindings := flags.String("bindings", "", "input tables/scalars JSON")
	casesPath := flags.String("cases", "", "source-pinned case recipes JSON")
	templatePath := flags.String("template", "", "reviewed remote comparison notebook template")
	outputPath := flags.String("output", "", "generated SOURCE notebook path")
	if err := flags.Parse(args[1:]); err != nil {
		return err
	}
	if flags.NArg() != 0 {
		return fmt.Errorf("formal-method rejects positional arguments")
	}
	allowed := map[string][]string{"compile": {"root", "commit", "path", "function", "tables"}, "evaluate": {"method", "bindings"}, "inventory": {"root", "commit"}, "interface": {"root", "commit", "entrypoint"}, "interfaces": {"root", "inventory"}, "prepare-comparison": {"root", "cases", "template", "output"}}
	var invalid error
	flags.Visit(func(f *flag.Flag) {
		found := false
		for _, name := range allowed[args[0]] {
			if name == f.Name {
				found = true
			}
		}
		if !found {
			invalid = fmt.Errorf("--%s is not supported by formal-method %s", f.Name, args[0])
		}
	})
	if invalid != nil {
		return invalid
	}
	var out any
	var unknown bool
	switch args[0] {
	case "interfaces":
		var inventory formalmethod.Inventory
		if err := readFormalJSON(*inventoryPath, &inventory); err != nil {
			return err
		}
		result, err := formalmethod.DescribeInventory(ctx, *root, inventory)
		if err != nil {
			return err
		}
		out = result
		unknown = !result.PredictionReady
	case "interface":
		result, err := formalmethod.DescribeJob(ctx, *root, *commit, *entrypoint)
		if err != nil {
			return err
		}
		out = result
		unknown = !result.PredictionReady
	case "prepare-comparison":
		var recipes []formalmethod.CaseRecipe
		if err := readFormalJSON(*casesPath, &recipes); err != nil {
			return err
		}
		cases, err := formalmethod.CompileCases(ctx, *root, recipes)
		if err != nil {
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
		if err = os.WriteFile(*outputPath, []byte(notebook), 0600); err != nil {
			return err
		}
		out = map[string]any{"output": *outputPath, "cases": len(cases), "source_files": len(payload.Sources)}
	case "compile":
		names := []string{}
		if *tables != "" {
			names = strings.Split(*tables, ",")
		}
		m, err := formalmethod.CompileGit(ctx, *root, *commit, *path, *function, names)
		if err != nil {
			return err
		}
		out = m
		unknown = m.Status != "compiled"
	case "evaluate":
		var m formalmethod.Method
		var b formalmethod.Bindings
		if err := readFormalJSON(*method, &m); err != nil {
			return err
		}
		if err := readFormalJSON(*bindings, &b); err != nil {
			return err
		}
		if len(m.Steps) > 0 && m.Steps[len(m.Steps)-1].Expression.Kind == formalmethod.Tuple {
			result, err := formalmethod.EvaluateOutputs(ctx, m, b)
			if err != nil {
				return err
			}
			out = result
			break
		}
		rows, err := formalmethod.Evaluate(ctx, m, b)
		if err != nil {
			return err
		}
		out = rows
	case "inventory":
		r, err := formalmethod.InventoryGit(ctx, *root, *commit)
		if err != nil {
			return err
		}
		out = r
		unknown = !r.PredictionReady
	default:
		return fmt.Errorf("unsupported formal-method command %s", args[0])
	}
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	if err := enc.Encode(out); err != nil {
		return err
	}
	if unknown {
		return fmt.Errorf("formal-method has unresolved coverage; inspect diagnostics")
	}
	return nil
}

func readFormalJSON(path string, out any) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	info, err := f.Stat()
	if err != nil {
		return err
	}
	if info.Size() > 16<<20 {
		return fmt.Errorf("formal-method JSON exceeds 16 MiB")
	}
	d := json.NewDecoder(io.LimitReader(f, 16<<20))
	d.DisallowUnknownFields()
	if err := d.Decode(out); err != nil {
		return err
	}
	var extra any
	if err := d.Decode(&extra); err != io.EOF {
		return fmt.Errorf("formal-method JSON must contain exactly one value")
	}
	return nil
}
