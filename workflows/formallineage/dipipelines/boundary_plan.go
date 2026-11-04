package dipipelines

import (
	"context"
	"encoding/json"
	"fmt"
	"sort"
	"strings"

	"github.com/jeisenman/q2_bench/workflows/lineage"
	sitter "github.com/tree-sitter/go-tree-sitter"
)

// PlanBoundariesGit audits every catalogued job and every semantic graph job.
// The graph's di-pipelines pin must exactly match the source inventory pin.
func PlanBoundariesGit(ctx context.Context, root string, inventory Inventory, graphBytes []byte) (BoundarySuite, error) {
	report := BoundarySuite{Format: "q2-boundary-suite/v1", Commit: inventory.Commit, GraphSHA256: hash(graphBytes), ScenarioLimit: 10, Jobs: []BoundaryJob{}, LogicalJobs: []LogicalBoundary{}, Cases: []ComparisonCase{}, Status: "blocked"}
	report.Procedures = map[string]BoundaryCheck{}
	for _, family := range boundaryFamilies {
		report.Procedures[family] = scenarioCheck(BoundaryClause{}, family)
	}
	graph, err := lineage.ParseGraph(graphBytes)
	if err != nil {
		return report, err
	}
	if err := validateBoundaryPin(graph.Manifest, inventory); err != nil {
		return report, err
	}
	report.GraphID, _ = graph.Manifest["graphId"].(string)
	if semantic, ok := graph.Manifest["semanticLayer"].(map[string]any); ok {
		report.GenerationID, _ = semantic["generationId"].(string)
	}
	jobs := map[string]*BoundaryJob{}
	get := func(name string) *BoundaryJob {
		if jobs[name] == nil {
			jobs[name] = &BoundaryJob{EntryPoint: name, LineageIDs: []string{}, UnitIDs: []string{}, Copies: []CopyTarget{}, Sources: []Source{}, Clauses: []BoundaryClause{}, Scenarios: []BoundaryScenario{}, Gaps: []string{}, Status: "blocked"}
		}
		return jobs[name]
	}
	for _, n := range graph.Nodes {
		if n.Kind != "job" {
			continue
		}
		logical := LogicalBoundary{ID: n.ID, Implementations: []string{}, Scope: "di-pipelines", Status: "blocked"}
		transforms, _ := n.Data["transformations"].([]any)
		for _, raw := range transforms {
			t, ok := raw.(map[string]any)
			if !ok {
				return report, fmt.Errorf("job %s has malformed transformation", n.ID)
			}
			entry, _ := t["implementation"].(string)
			if entry == "" {
				entry = "unresolved:" + n.ID
			}
			logical.Implementations = append(logical.Implementations, entry)
			j := get(entry)
			j.LineageIDs = append(j.LineageIDs, n.ID)
		}
		logical.Implementations = sortedUnique(logical.Implementations)
		if len(logical.Implementations) == 0 {
			logical.Scope = "orchestration_or_unresolved"
		}
		report.LogicalJobs = append(report.LogicalJobs, logical)
	}
	for _, file := range inventory.Files {
		if file.ParseStatus != "parsed" {
			get("unparsed:" + file.Source.Path).Gaps = append(get("unparsed:"+file.Source.Path).Gaps, file.Error)
		}
		for _, u := range file.Units {
			name := u.EntryPoint
			if name == "" {
				name = "dynamic:" + u.ID
			}
			j := get(name)
			j.UnitIDs = append(j.UnitIDs, u.ID)
			j.Copies = append(j.Copies, u.Copies...)
			for _, d := range u.Unresolved {
				j.Gaps = append(j.Gaps, fmt.Sprintf("unit %s:%d: %s", u.Task, d.Line, d.Message))
			}
		}
		// Include implementation classes with no literal OperatorFactory reference.
		module := moduleFromPath(file.Source.Path)
		for _, method := range file.Methods {
			parts := strings.Split(method.Function, ".")
			if module != "" && len(parts) == 2 && in(parts[1], "run", "_run") {
				get(module + "." + parts[0])
			}
		}
	}
	r := interfaceResolver{ctx: ctx, root: root, commit: inventory.Commit, modules: map[string]*parsedModule{}}
	defer func() {
		for _, m := range r.modules {
			m.tree.Close()
		}
	}()
	clauses := map[string][]BoundaryClause{}
	cases := map[string]ComparisonCase{}
	names := []string{}
	for name := range jobs {
		names = append(names, name)
	}
	sort.Strings(names)
	for _, name := range names {
		if err := ctx.Err(); err != nil {
			return report, err
		}
		job := jobs[name]
		job.LineageIDs = sortedUnique(job.LineageIDs)
		job.UnitIDs = sortedUnique(job.UnitIDs)
		modules, gaps := boundaryClosure(&r, name)
		job.Gaps = append(job.Gaps, gaps...)
		for _, m := range modules {
			job.Sources = append(job.Sources, m.source)
			if _, exists := clauses[m.source.Path]; !exists {
				found := extractBoundaryClauses(m)
				for i := range found {
					generated, reason := clauseCases(ctx, m, found[i])
					found[i].Blocked = reason
					found[i].Mutations = fixtureMutations(ctx, generated)
					found[i].Findings = boundaryImpossibleFindings(generated)
					for _, c := range generated {
						found[i].CaseIDs = append(found[i].CaseIDs, c.ID)
						cases[c.ID] = c
					}
				}
				clauses[m.source.Path] = found
			}
			job.Clauses = append(job.Clauses, clauses[m.source.Path]...)
			for _, c := range clauses[m.source.Path] {
				job.ClauseIDs = append(job.ClauseIDs, c.ID)
			}
		}
		job.Gaps = append(job.Gaps, "Conservative module closure includes potentially unused helpers; dynamic dispatch, external frameworks, schemas, complete input fixtures, and effect oracles require review. Isolated clause tests are not whole-job tests.")
		job.Gaps = sortedUnique(job.Gaps)
		planJobScenarios(job)
		report.Jobs = append(report.Jobs, *job)
	}
	for _, c := range cases {
		report.Cases = append(report.Cases, c)
	}
	paths := []string{}
	for path := range clauses {
		paths = append(paths, path)
	}
	sort.Strings(paths)
	for _, path := range paths {
		report.Clauses = append(report.Clauses, clauses[path]...)
	}
	for i := range report.LogicalJobs {
		logical := &report.LogicalJobs[i]
		for _, family := range boundaryFamilies {
			implementations := []string{}
			for _, entry := range logical.Implementations {
				for _, scenario := range jobs[entry].Scenarios {
					if scenario.ID == family {
						implementations = append(implementations, entry)
					}
				}
			}
			if len(implementations) > 0 || (len(logical.Implementations) == 0 && in(family, "branches", "effects")) {
				logical.Scenarios = append(logical.Scenarios, LogicalScenario{ID: family, Title: scenarioTitles[family], Implementations: implementations, Status: "planned_not_executed"})
			}
		}
	}
	sort.Slice(report.Cases, func(i, j int) bool { return report.Cases[i].ID < report.Cases[j].ID })
	return report, nil
}

func validateBoundaryPin(manifest map[string]any, inventory Inventory) error {
	if inventory.Format != "q2-formal-inventory/v1" || !commitRE.MatchString(inventory.Commit) {
		return fmt.Errorf("boundary suite requires a versioned, source-pinned inventory")
	}
	pins, _ := manifest["sourceRepositories"].([]any)
	count := 0
	for _, raw := range pins {
		pin, _ := raw.(map[string]any)
		if pin["repository"] == "di-pipelines" {
			count++
			if pin["commitSha"] != inventory.Commit {
				return fmt.Errorf("semantic graph di-pipelines pin %v differs from inventory %s", pin["commitSha"], inventory.Commit)
			}
		}
	}
	if count != 1 {
		return fmt.Errorf("semantic graph requires exactly one di-pipelines source pin")
	}
	return nil
}

func boundaryClosure(r *interfaceResolver, entry string) ([]*parsedModule, []string) {
	index := strings.LastIndex(entry, ".")
	if index < 1 {
		return nil, []string{"No qualified di-pipelines implementation: " + entry}
	}
	seen := map[string]bool{}
	modules := []*parsedModule{}
	gaps := []string{}
	var visit func(string)
	visit = func(module string) {
		if seen[module] {
			return
		}
		seen[module] = true
		m, err := r.load(module)
		if err != nil {
			gaps = append(gaps, module+": "+err.Error())
			return
		}
		modules = append(modules, m)
		imports := boundaryImports(m)
		refs := []string{}
		var walk func(*sitter.Node)
		walk = func(n *sitter.Node) {
			if n.Kind() == "module" {
				for _, c := range children(n) {
					if in(c.Kind(), "function_definition", "class_definition", "decorated_definition") {
						walk(c)
					}
				}
				return
			}
			if n.Kind() == "call" {
				f := n.ChildByFieldName("function")
				name := f.Utf8Text(m.content)
				parts := strings.Split(name, ".")
				if qualified := imports[parts[0]]; qualified != "" {
					if len(parts) > 1 {
						if len(parts) > 2 {
							qualified += "." + strings.Join(parts[1:len(parts)-1], ".")
						}
						refs = append(refs, qualified)
					} else if split := strings.LastIndex(qualified, "."); split > 0 {
						refs = append(refs, qualified[:split])
					}
				}
			}
			if n.Kind() == "class_definition" {
				for _, base := range children(n.ChildByFieldName("superclasses")) {
					if qualified := imports[base.Utf8Text(m.content)]; qualified != "" {
						if split := strings.LastIndex(qualified, "."); split > 0 {
							refs = append(refs, qualified[:split])
						}
					}
				}
			}
			for _, c := range children(n) {
				walk(c)
			}
		}
		walk(m.tree.RootNode())
		for _, ref := range sortedUnique(refs) {
			if _, err := modulePath(ref); err == nil {
				if _, err := r.load(ref); err != nil {
					// An imported class used as Class.method lives in its parent
					// module; an imported module used as module.function does not.
					if split := strings.LastIndex(ref, "."); split > 0 {
						if parent, err := r.load(ref[:split]); err == nil && classNode(parent, ref[split+1:]) != nil {
							visit(ref[:split])
							continue
						}
					}
				}
				visit(ref)
			} else if strings.HasPrefix(ref, "di_pyjobs") {
				gaps = append(gaps, "External framework requires its own pinned behavioral contract: "+ref)
			} else if strings.HasPrefix(ref, ".") {
				gaps = append(gaps, "Relative import requires package resolution: "+ref)
			}
		}
	}
	visit(entry[:index])
	if len(modules) > 0 && classNode(modules[0], entry[index+1:]) == nil {
		gaps = append(gaps, "Implementation class absent at source pin: "+entry)
	}
	sort.Slice(modules, func(i, j int) bool { return modules[i].source.Path < modules[j].source.Path })
	return modules, gaps
}

// BoundarySummary returns counts without treating planned scenarios as passes.
func BoundarySummary(s BoundarySuite) map[string]any {
	scenarios := 0
	compiledClauses, killed, survived := 0, 0, 0
	for _, c := range s.Clauses {
		if len(c.CaseIDs) > 0 {
			compiledClauses++
		}
		for _, m := range c.Mutations {
			if m.Status == "killed" {
				killed++
			} else if m.Status == "survived" {
				survived++
			}
		}
	}
	for _, j := range s.Jobs {
		scenarios += len(j.Scenarios)
	}
	result := map[string]any{"status": s.Status, "commit": s.Commit, "logical_jobs": len(s.LogicalJobs), "implementation_jobs": len(s.Jobs), "unique_clauses": len(s.Clauses), "clauses_with_fixtures": compiledClauses, "planned_scenarios": scenarios, "executable_clause_cases": len(s.Cases), "fixture_ir_mutants_killed": killed, "fixture_ir_mutants_survived": survived, "executed_scenarios": 0, "whole_job_passes": 0}
	if s.PropertyConfig != nil {
		generated := 0
		for _, c := range s.Cases {
			if c.Generation != nil {
				generated++
			}
		}
		result["property_config"] = s.PropertyConfig
		result["seeded_property_instances"] = generated
		result["exact_boundary_examples"] = len(s.Cases) - generated
	}
	return result
}

// DecodeBoundaryGraphPin returns the di-pipelines commit from a staged graph.
func DecodeBoundaryGraphPin(content []byte) (string, error) {
	var graph struct {
		Manifest map[string]any `json:"manifest"`
	}
	if err := json.Unmarshal(content, &graph); err != nil {
		return "", err
	}
	pins, _ := graph.Manifest["sourceRepositories"].([]any)
	for _, raw := range pins {
		pin, _ := raw.(map[string]any)
		if pin["repository"] == "di-pipelines" {
			commit, _ := pin["commitSha"].(string)
			if commitRE.MatchString(commit) {
				return commit, nil
			}
		}
	}
	return "", fmt.Errorf("graph has no full di-pipelines commit pin")
}
