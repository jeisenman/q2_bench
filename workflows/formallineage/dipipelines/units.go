package dipipelines

import (
	"fmt"
	"sort"

	sitter "github.com/tree-sitter/go-tree-sitter"
)

// CopyTarget is an output declaration attached to its producer transformation.
// Literal declarations do not establish runtime path resolution or copy success.
type CopyTarget struct {
	Task       string            `json:"task"`
	EntryPoint string            `json:"entrypoint"`
	Arguments  map[string]string `json:"arguments"`
	Conditions []string          `json:"conditions"`
}

// JobUnit groups one transformation invocation with its downstream basic copies.
type JobUnit struct {
	ID              string            `json:"id"`
	Source          Source            `json:"source"`
	Function        string            `json:"function"`
	Task            string            `json:"task"`
	EntryPoint      string            `json:"entrypoint"`
	Arguments       map[string]string `json:"arguments"`
	Copies          []CopyTarget      `json:"copies"`
	Conditions      []string          `json:"conditions"`
	Unresolved      []Diagnostic      `json:"unresolved"`
	PredictionReady bool              `json:"prediction_ready"`
}

type taskDeclaration struct {
	variable, name, entry string
	args                  map[string]string
	conditions            []string
	diagnostics           []Diagnostic
	line                  int
}

func extractUnits(root *sitter.Node, b []byte, source Source) []JobUnit {
	defs := map[string][]*sitter.Node{}
	functions(root, b, "", defs)
	names := []string{}
	for name := range defs {
		names = append(names, name)
	}
	sort.Strings(names)
	units := []JobUnit{}
	for _, name := range names {
		for _, f := range defs[name] {
			units = append(units, unitsInFunction(f, b, source, name)...)
		}
	}
	return units
}

func unitsInFunction(f *sitter.Node, b []byte, source Source, function string) []JobUnit {
	tasks := map[string]taskDeclaration{}
	edges := map[string][]string{}
	var walk func(*sitter.Node, []string)
	walk = func(n *sitter.Node, conditions []string) {
		if n.Kind() == "function_definition" || n.Kind() == "class_definition" {
			return
		}
		if in(n.Kind(), "if_statement", "elif_clause", "else_clause", "for_statement", "while_statement", "try_statement", "except_clause") {
			description := n.Kind()
			if condition := n.ChildByFieldName("condition"); condition != nil {
				description += " " + condition.Utf8Text(b)
			}
			conditions = append(append([]string{}, conditions...), description)
		}
		if n.Kind() == "assignment" {
			left, right := n.ChildByFieldName("left"), n.ChildByFieldName("right")
			if left != nil && left.Kind() == "identifier" {
				if factory := findFactory(right, b); factory != nil {
					t := taskDeclaration{variable: left.Utf8Text(b), args: map[string]string{}, line: int(n.StartPosition().Row) + 1, conditions: conditions}
					for _, arg := range children(factory.ChildByFieldName("arguments")) {
						if arg.Kind() != "keyword_argument" {
							continue
						}
						key := arg.ChildByFieldName("name").Utf8Text(b)
						value := arg.ChildByFieldName("value")
						switch key {
						case "job_name", "job_reference":
							text, err := pythonString(value.Utf8Text(b))
							if err != nil {
								t.diagnostics = append(t.diagnostics, Diagnostic{Line: t.line, Message: "dynamic " + key})
								continue
							}
							if key == "job_name" {
								t.name = text
							} else {
								t.entry = text
							}
						case "override_activity_args":
							if value.Kind() != "dictionary" {
								t.diagnostics = append(t.diagnostics, Diagnostic{Line: t.line, Message: "dynamic activity arguments"})
								continue
							}
							for _, pair := range children(value) {
								if pair.Kind() != "pair" {
									t.diagnostics = append(t.diagnostics, Diagnostic{Line: t.line, Message: "expanded activity arguments"})
									continue
								}
								k, err := pythonString(pair.ChildByFieldName("key").Utf8Text(b))
								if err != nil {
									t.diagnostics = append(t.diagnostics, Diagnostic{Line: t.line, Message: "dynamic activity key"})
									continue
								}
								v, err := pythonString(pair.ChildByFieldName("value").Utf8Text(b))
								if err != nil {
									t.diagnostics = append(t.diagnostics, Diagnostic{Line: t.line, Message: "dynamic activity value " + k})
									continue
								}
								t.args[k] = v
							}
						}
					}
					if _, exists := tasks[t.variable]; exists {
						t.diagnostics = append(t.diagnostics, Diagnostic{Line: t.line, Message: "conditional or repeated task assignment"})
					}
					tasks[t.variable] = t
				}
			}
		}
		if n.Kind() == "binary_operator" {
			left, right := n.ChildByFieldName("left"), n.ChildByFieldName("right")
			operator := n.ChildByFieldName("operator")
			if left != nil && right != nil && operator != nil && in(operator.Utf8Text(b), "<<", ">>") {
				a, okA := taskNames(left, b)
				z, okZ := taskNames(right, b)
				if okA && okZ {
					if operator.Utf8Text(b) == "<<" {
						a, z = z, a
					}
					for _, from := range a {
						edges[from] = append(edges[from], z...)
					}
				}
			}
		}
		for _, x := range children(n) {
			walk(x, conditions)
		}
	}
	walk(f.ChildByFieldName("body"), nil)
	names := []string{}
	for name := range tasks {
		names = append(names, name)
	}
	sort.Strings(names)
	result := []JobUnit{}
	claimed := map[string]bool{}
	for _, variable := range names {
		t := tasks[variable]
		if basicCopy(t.entry) {
			continue
		}
		u := JobUnit{ID: hash([]byte(source.Commit + ":" + source.Path + ":" + function + ":" + variable)), Source: source, Function: function, Task: t.name, EntryPoint: t.entry, Arguments: t.args, Conditions: t.conditions, Copies: []CopyTarget{}, Unresolved: append([]Diagnostic{}, t.diagnostics...)}
		seen := map[string]bool{}
		var visit func(string)
		visit = func(from string) {
			if seen[from] {
				return
			}
			seen[from] = true
			for _, next := range edges[from] {
				copy, ok := tasks[next]
				if !ok {
					u.Unresolved = append(u.Unresolved, Diagnostic{Line: t.line, Message: "unresolved downstream task " + next})
					continue
				}
				if basicCopy(copy.entry) {
					claimed[next] = true
					u.Copies = append(u.Copies, CopyTarget{copy.name, copy.entry, copy.args, copy.conditions})
					u.Unresolved = append(u.Unresolved, copy.diagnostics...)
					visit(next)
				}
			}
		}
		visit(variable)
		u.Unresolved = append(u.Unresolved, Diagnostic{Line: t.line, Message: "linked transformation, runner and physical write semantics not compiled"})
		sort.Slice(u.Copies, func(i, j int) bool { return u.Copies[i].Task < u.Copies[j].Task })
		result = append(result, u)
	}
	for _, variable := range names {
		t := tasks[variable]
		if basicCopy(t.entry) && !claimed[variable] {
			result = append(result, JobUnit{ID: hash([]byte(source.Commit + ":" + source.Path + ":" + function + ":" + variable)), Source: source, Function: function, Task: t.name, EntryPoint: t.entry, Arguments: t.args, Copies: []CopyTarget{}, Conditions: t.conditions, Unresolved: []Diagnostic{{Line: t.line, Message: fmt.Sprintf("copy %s has no statically resolved transformation parent", t.name)}}})
		}
	}
	return result
}

func findFactory(n *sitter.Node, b []byte) *sitter.Node {
	if n == nil {
		return nil
	}
	if n.Kind() == "call" {
		f := n.ChildByFieldName("function")
		if f.Kind() == "identifier" && f.Utf8Text(b) == "OperatorFactory" {
			return n
		}
	}
	for _, x := range children(n) {
		if found := findFactory(x, b); found != nil {
			return found
		}
	}
	return nil
}

func taskNames(n *sitter.Node, b []byte) ([]string, bool) {
	if n.Kind() == "identifier" {
		return []string{n.Utf8Text(b)}, true
	}
	if n.Kind() == "list" || n.Kind() == "tuple" {
		out := []string{}
		for _, x := range children(n) {
			v, ok := taskNames(x, b)
			if !ok {
				return nil, false
			}
			out = append(out, v...)
		}
		return out, true
	}
	return nil, false
}

func basicCopy(entry string) bool {
	return in(entry, "datamart.core.standard_jobs.adls_to_adls.AdlsToAdlsCopyApi", "di_pyjobs.job.standard.batch.AdlsToAdlsCopy")
}
