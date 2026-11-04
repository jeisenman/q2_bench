package dipipelines

import (
	"context"
	"fmt"
	"sort"

	"github.com/jeisenman/q2_bench/workflows/formallineage/syntax"
	sitter "github.com/tree-sitter/go-tree-sitter"
)

type compiler struct {
	names       map[string]Kind
	nodes       int
	source      []byte
	symbols     map[string]bool
	definitions map[string][]*sitter.Node
	chain       []string
	library     map[string]Method
	receipt     Source
	constants   map[string][]*sitter.Node
	assumptions map[string]bool
}

func parse(content []byte) (*sitter.Tree, error) {
	return syntax.Parse(context.Background(), syntax.Python, content)
}

func children(n *sitter.Node) []*sitter.Node {
	var result []*sitter.Node
	if n != nil {
		for i := uint(0); i < n.NamedChildCount(); i++ {
			x := n.NamedChild(i)
			if x.Kind() != "comment" {
				result = append(result, x)
			}
		}
	}
	return result
}

func functions(n *sitter.Node, source []byte, prefix string, result map[string][]*sitter.Node) {
	for _, x := range children(n) {
		if x.Kind() == "decorated_definition" {
			x = x.ChildByFieldName("definition")
		}
		switch x.Kind() {
		case "function_definition":
			name := prefix + x.ChildByFieldName("name").Utf8Text(source)
			result[name] = append(result[name], x)
		case "class_definition":
			functions(x.ChildByFieldName("body"), source, prefix+x.ChildByFieldName("name").Utf8Text(source)+".", result)
		}
	}
}

// Compile lowers a function parsed by the standard Tree-sitter Python grammar.
// Unsupported behavior produces an unknown artifact with no executable steps.
func Compile(content []byte, source Source, function string, tables []string) (Method, error) {
	if source.SHA256 != hash(content) || !commitRE.MatchString(source.Commit) || !safePath(source.Path) {
		return Method{}, fmt.Errorf("source requires matching SHA256, full commit and safe path")
	}
	tree, err := parse(content)
	if err != nil {
		return Method{}, err
	}
	defer tree.Close()
	defs := map[string][]*sitter.Node{}
	functions(tree.RootNode(), content, "", defs)
	if len(defs[function]) != 1 {
		return Method{}, fmt.Errorf("function %q must exist exactly once", function)
	}
	return compileNode(content, source, function, defs[function][0], tables), nil
}

func compileNode(content []byte, source Source, function string, f *sitter.Node, tables []string) Method {
	return compileLinked(content, source, function, f, tables, nil)
}

func compileLinked(content []byte, source Source, function string, f *sitter.Node, tables, chain []string) Method {
	m := Method{Format: Format, Profile: Profile, Function: function, Source: source, Status: "compiled", Steps: []Step{}, Diagnostics: []Diagnostic{}}
	root := f
	for root.Parent() != nil {
		root = root.Parent()
	}
	defs := map[string][]*sitter.Node{}
	functions(root, content, "", defs)
	c := compiler{names: map[string]Kind{}, source: content, symbols: semanticBindings(root, content), definitions: defs, chain: append(append([]string{}, chain...), function), library: map[string]Method{}, receipt: source, constants: moduleConstants(root, content), assumptions: map[string]bool{}}
	unknown := func(n *sitter.Node, message string) {
		m.Diagnostics = append(m.Diagnostics, Diagnostic{Line: int(n.StartPosition().Row) + 1, Message: message})
		m.Status = "unknown"
	}
	for _, a := range children(f.ChildByFieldName("parameters")) {
		identifier := parameterName(a)
		if identifier == nil {
			unknown(a, "defaults and variable arguments require explicit lowering")
			continue
		}
		name := identifier.Utf8Text(content)
		if in(name, "F", "StringType", "str") {
			unknown(a, "parameter shadows a semantic binding")
		}
		c.names[name] = Scalar
		m.Parameters = append(m.Parameters, Parameter{Name: name, Kind: Scalar})
	}
	for _, name := range tables {
		kind, ok := c.names[name]
		if !ok || kind == Table {
			unknown(f, "invalid or duplicate table parameter "+name)
			continue
		}
		c.names[name] = Table
		for i := range m.Parameters {
			if m.Parameters[i].Name == name {
				m.Parameters[i].Kind = Table
			}
		}
	}
	if f.Parent() != nil && f.Parent().Kind() == "decorated_definition" {
		unknown(f, "decorators require explicit lowering")
	}
	returned := false
	for i, s := range children(f.ChildByFieldName("body")) {
		if s.Kind() == "expression_statement" && s.NamedChildCount() == 1 && s.NamedChild(0).Kind() == "string" && i == 0 {
			continue
		}
		if returned {
			unknown(s, "statements after return unsupported")
			continue
		}
		step := Step{Line: int(s.StartPosition().Row) + 1}
		var value *sitter.Node
		switch s.Kind() {
		case "expression_statement":
			if s.NamedChildCount() != 1 || s.NamedChild(0).Kind() != "assignment" {
				unknown(s, "effectful expression requires explicit lowering")
				continue
			}
			a := s.NamedChild(0)
			target := a.ChildByFieldName("left")
			value = a.ChildByFieldName("right")
			if target == nil || value == nil {
				unknown(s, "mutation or destructuring unsupported")
				continue
			}
			if target.Kind() == "identifier" {
				step.Target = target.Utf8Text(content)
			} else if in(target.Kind(), "pattern_list", "tuple_pattern") {
				for _, name := range children(target) {
					if name.Kind() != "identifier" {
						unknown(s, "nested or expanded tuple assignment unsupported")
						continue
					}
					if in(name.Utf8Text(content), "F", "StringType", "str") {
						unknown(s, "tuple target shadows a semantic binding")
					}
					step.Targets = append(step.Targets, name.Utf8Text(content))
				}
			} else {
				unknown(s, "mutation or destructuring unsupported")
				continue
			}
			if in(step.Target, "F", "StringType", "str") {
				unknown(s, "reserved semantic name shadowed")
				continue
			}
		case "return_statement":
			args := children(s)
			if len(args) != 1 {
				unknown(s, "return must have one relation")
				continue
			}
			value = args[0]
			step.Return = true
			returned = true
		default:
			unknown(s, "unsupported statement "+s.Kind())
			continue
		}
		expr, err := c.lower(value)
		if err != nil {
			unknown(s, err.Error())
			continue
		}
		if step.Return && expr.Kind != Table && expr.Kind != Tuple {
			unknown(s, "return must be a relation")
			continue
		}
		step.Expression = expr
		if step.Target != "" && expr.Kind == Tuple {
			unknown(s, "table tuples require explicit unpacking")
			continue
		}
		if len(step.Targets) > 0 {
			if expr.Kind != Tuple || tupleWidth(expr, c.library) != len(step.Targets) {
				unknown(s, "tuple assignment arity mismatch")
				continue
			}
			for _, name := range step.Targets {
				c.names[name] = Table
			}
		}
		if step.Return {
			m.Outputs = outputPorts(expr, c.library)
		}
		if step.Target != "" {
			c.names[step.Target] = expr.Kind
		}
		m.Steps = append(m.Steps, step)
	}
	if !returned {
		unknown(f, "missing return")
	}
	if m.Status != "compiled" {
		m.Steps = []Step{}
		m.Outputs = nil
	}
	for assumption := range c.assumptions {
		m.Assumptions = append(m.Assumptions, assumption)
	}
	sort.Strings(m.Assumptions)
	m.ID = methodID(m)
	m.Library = c.library
	return m
}
