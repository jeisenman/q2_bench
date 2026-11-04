package dipipelines

import (
	"context"
	"fmt"
	"os/exec"
	"sort"
	"strings"
	"time"

	sitter "github.com/tree-sitter/go-tree-sitter"
)

// FileCoverage retains parse failures instead of excluding files from coverage.
type FileCoverage struct {
	Source      Source    `json:"source"`
	ParseStatus string    `json:"parse_status"`
	Error       string    `json:"error,omitempty"`
	Methods     []Method  `json:"methods"`
	Units       []JobUnit `json:"units"`
}

// Inventory reports every Python job file and compilation attempt in the scope.
type Inventory struct {
	Format          string         `json:"format"`
	Commit          string         `json:"commit"`
	Parser          string         `json:"parser"`
	Scope           []string       `json:"scope"`
	Files           []FileCoverage `json:"files"`
	Compiled        int            `json:"compiled_methods"`
	Unknown         int            `json:"unknown_methods"`
	ParseFailures   int            `json:"parse_failures"`
	PredictionReady bool           `json:"prediction_ready"`
}

// InventoryGit parses every tracked Python file in the job and orchestration
// roots. Copies remain in orchestration scope for subsequent unit grouping.
func InventoryGit(ctx context.Context, root, commit string) (Inventory, error) {
	if root == "" || !commitRE.MatchString(commit) {
		return Inventory{}, fmt.Errorf("provide source checkout and full commit")
	}
	scope := []string{"ds-jobs/src/datascience_jobs/jobs/", "de-jobs/src/datamart/jobs/", "de-jobs/src/datascience/jobs/", "de-jobs/src/datamart/core/standard_jobs/", "ra-jobs/src/rajobs/jobs/", "dags/precisionlender/dags/"}
	r := Inventory{Format: "q2-formal-inventory/v1", Commit: commit, Parser: "tree-sitter-python/v0.25.0;go-tree-sitter/v0.25.0", Scope: scope, Files: []FileCoverage{}}
	gitctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	args := append([]string{"-C", root, "ls-tree", "-r", "--name-only", commit, "--"}, scope...)
	output, err := exec.CommandContext(gitctx, "git", args...).Output()
	if err != nil {
		return r, err
	}
	paths := strings.Split(strings.TrimSpace(string(output)), "\n")
	if len(paths) > 5000 {
		return r, fmt.Errorf("inventory exceeds 5000 files")
	}
	for _, path := range paths {
		if err := ctx.Err(); err != nil {
			return r, err
		}
		if !strings.HasSuffix(path, ".py") {
			continue
		}
		file := FileCoverage{Source: Source{Commit: commit, Path: path}, Methods: []Method{}}
		b, err := readGit(ctx, root, commit, path)
		if err != nil {
			file.ParseStatus = "error"
			file.Error = err.Error()
			r.ParseFailures++
			r.Files = append(r.Files, file)
			continue
		}
		file.Source.SHA256 = hash(b)
		tree, err := parse(b)
		if err != nil {
			file.ParseStatus = "error"
			file.Error = err.Error()
			r.ParseFailures++
			r.Files = append(r.Files, file)
			continue
		}
		file.ParseStatus = "parsed"
		file.Units = extractUnits(tree.RootNode(), b, file.Source)
		defs := map[string][]*sitter.Node{}
		functions(tree.RootNode(), b, "", defs)
		names := []string{}
		for name := range defs {
			names = append(names, name)
		}
		sort.Strings(names)
		for _, name := range names {
			for _, node := range defs[name] {
				m := compileNode(b, file.Source, name, node, inferTables(node, b))
				if len(defs[name]) > 1 {
					m.Status = "unknown"
					m.Steps = []Step{}
					m.Diagnostics = append(m.Diagnostics, Diagnostic{Line: int(node.StartPosition().Row) + 1, Message: "duplicate function identity"})
					m.ID = methodID(m)
				}
				file.Methods = append(file.Methods, m)
				if m.Status == "compiled" {
					r.Compiled++
				} else {
					r.Unknown++
				}
			}
		}
		tree.Close()
		r.Files = append(r.Files, file)
	}
	// Parsing/compiling individual helpers cannot establish linked job readiness.
	r.PredictionReady = false
	return r, nil
}

func inferTables(f *sitter.Node, b []byte) []string {
	params := map[string]bool{}
	for _, a := range children(f.ChildByFieldName("parameters")) {
		identifier := parameterName(a)
		if identifier != nil && identifier.Utf8Text(b) != "self" {
			params[identifier.Utf8Text(b)] = true
		}
	}
	found := map[string]bool{}
	var walk func(*sitter.Node)
	walk = func(n *sitter.Node) {
		if n.Kind() == "call" {
			target := n.ChildByFieldName("function")
			if target != nil && target.Kind() == "attribute" {
				obj := target.ChildByFieldName("object")
				method := target.ChildByFieldName("attribute").Utf8Text(b)
				if obj.Kind() == "identifier" && params[obj.Utf8Text(b)] && in(method, "filter", "where", "drop", "withColumn", "groupBy", "join", "select", "dropna", "withColumnRenamed") {
					found[obj.Utf8Text(b)] = true
				}
				if method == "join" {
					args := children(n.ChildByFieldName("arguments"))
					if len(args) > 0 && args[0].Kind() == "identifier" && params[args[0].Utf8Text(b)] {
						found[args[0].Utf8Text(b)] = true
					}
				}
			}
		}
		for _, x := range children(n) {
			walk(x)
		}
	}
	walk(f.ChildByFieldName("body"))
	result := []string{}
	for name := range found {
		result = append(result, name)
	}
	sort.Strings(result)
	return result
}
