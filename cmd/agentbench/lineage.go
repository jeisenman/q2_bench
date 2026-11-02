package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strings"

	"github.com/jeisenman/q2_bench/workflows/lineagecheck"
)

type repositoryRoots map[string]string

func (r repositoryRoots) String() string { return "name=checkout" }
func (r repositoryRoots) Set(value string) error {
	name, path, ok := strings.Cut(value, "=")
	if !ok || name == "" || path == "" || r[name] != "" {
		return fmt.Errorf("--repo requires a unique name=checkout path")
	}
	r[name] = path
	return nil
}

func lineageCommand(ctx context.Context, args []string) error {
	if len(args) == 0 {
		return fmt.Errorf("lineage requires build, compare, check-pr, backfill, or show")
	}
	flags := flag.NewFlagSet("lineage "+args[0], flag.ContinueOnError)
	storePath := flags.String("store", lineagecheck.DefaultStorePath, "local immutable snapshot store")
	manifest := flags.String("manifest", "", "reviewed extraction manifest")
	baseID := flags.String("base", "", "baseline snapshot SHA256")
	headID := flags.String("head", "", "candidate snapshot SHA256")
	snapshotID := flags.String("snapshot", "", "snapshot SHA256; latest for show only")
	policyPath := flags.String("policy", "", "policy JSON; default additive")
	planPath := flags.String("plan", "", "source-pinned backfill plan JSON")
	dryRun := flags.Bool("dry-run", false, "build and validate without publishing")
	prRepo := flags.String("repository", "", "PR source repository name")
	prRoot := flags.String("root", "", "PR source checkout")
	baseRef := flags.String("base-ref", "master", "PR destination branch ref")
	headRef := flags.String("head-ref", "HEAD", "PR source branch ref")
	roots := repositoryRoots{}
	flags.Var(roots, "repo", "source checkout name=path; repeat for each source")
	if err := flags.Parse(args[1:]); err != nil {
		return err
	}
	if flags.NArg() != 0 {
		return fmt.Errorf("lineage commands do not accept positional arguments")
	}
	allowed := map[string][]string{
		"build":    {"store", "manifest", "repo", "dry-run"},
		"compare":  {"store", "base", "head", "policy"},
		"check-pr": {"store", "base", "head", "policy", "repository", "root", "base-ref", "head-ref"},
		"backfill": {"store", "snapshot", "plan"},
		"show":     {"store", "snapshot"},
	}
	var flagError error
	flags.Visit(func(f *flag.Flag) {
		for _, name := range allowed[args[0]] {
			if name == f.Name {
				return
			}
		}
		flagError = fmt.Errorf("--%s is not supported by lineage %s", f.Name, args[0])
	})
	if flagError != nil {
		return flagError
	}
	store := lineagecheck.Store{Root: *storePath}
	var output any
	var report *lineagecheck.Report
	switch args[0] {
	case "build":
		var recipe lineagecheck.Manifest
		if err := decodeLineageFile(*manifest, &recipe); err != nil {
			return err
		}
		snap, err := lineagecheck.Build(ctx, recipe, roots)
		if err != nil {
			return err
		}
		if !*dryRun {
			if err := store.Save(ctx, snap); err != nil {
				return err
			}
		}
		output = map[string]any{"snapshot_id": snap.ID, "scope": snap.Manifest.Scope, "datasets": len(snap.Manifest.Datasets), "jobs": len(snap.Manifest.Jobs), "unresolved": snap.Manifest.Unresolved, "dry_run": *dryRun}
	case "compare", "check-pr":
		if *baseID == "" || *headID == "" {
			return fmt.Errorf("comparison requires explicit --base and --head snapshot IDs")
		}
		base, err := store.Load(ctx, *baseID)
		if err != nil {
			return err
		}
		head, err := store.Load(ctx, *headID)
		if err != nil {
			return err
		}
		p := lineagecheck.Policy{Mode: "additive"}
		if *policyPath != "" {
			if err := decodeLineageFile(*policyPath, &p); err != nil {
				return err
			}
		}
		var result lineagecheck.Report
		if args[0] == "check-pr" {
			result, err = lineagecheck.CheckPR(ctx, base, head, p, lineagecheck.PRScope{Repository: *prRepo, Root: *prRoot, BaseRef: *baseRef, HeadRef: *headRef})
		} else {
			result, err = lineagecheck.Compare(base, head, p)
		}
		if err != nil {
			return err
		}
		output = result
		report = &result
	case "backfill":
		if *snapshotID == "" {
			return fmt.Errorf("backfill requires an explicit --snapshot ID")
		}
		snap, err := store.Load(ctx, *snapshotID)
		if err != nil {
			return err
		}
		var plan lineagecheck.BackfillPlan
		if err := decodeLineageFile(*planPath, &plan); err != nil {
			return err
		}
		result, err := lineagecheck.CheckBackfill(snap, plan)
		if err != nil {
			return err
		}
		output = result
		report = &result
	case "show":
		snap, err := store.Load(ctx, *snapshotID)
		if err != nil {
			return err
		}
		output = snap
	default:
		return fmt.Errorf("unsupported lineage command %q", args[0])
	}
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(output); err != nil {
		return err
	}
	if report != nil && report.Status != "pass" {
		return fmt.Errorf("lineage check %s; inspect the JSON findings", report.Status)
	}
	return nil
}

func decodeLineageFile(path string, target any) error {
	if path == "" {
		return fmt.Errorf("lineage input file path is required")
	}
	b, err := lineagecheck.ReadFile(path)
	if err != nil {
		return err
	}
	return lineagecheck.Decode(b, target)
}
