// Package discovery inventories cross-runtime source without executing it.
package discovery

import (
	"context"
	"fmt"
	"path"
	"sort"
	"strings"

	"github.com/jeisenman/q2_bench/workflows/formallineage/model"
	"github.com/jeisenman/q2_bench/workflows/formallineage/source"
	"github.com/jeisenman/q2_bench/workflows/formallineage/syntax"
	sitter "github.com/tree-sitter/go-tree-sitter"
)

// Parse binds syntax-derived declarations to one immutable source receipt.
func Parse(ctx context.Context, project, repository string, receipt model.Source, content []byte) (model.ParsedFile, error) {
	actual, err := source.Receipt(receipt.Commit, receipt.Path, content)
	if err != nil || actual != receipt || project == "" || repository == "" {
		return model.ParsedFile{}, fmt.Errorf("provide project, repository and matching immutable source receipt")
	}
	language, runtime, err := sourceLanguage(receipt.Path)
	if err != nil {
		return model.ParsedFile{}, err
	}
	tree, err := syntax.Parse(ctx, language, content)
	if err != nil {
		return model.ParsedFile{}, err
	}
	defer tree.Close()
	result := model.ParsedFile{Format: "q2-formal-source-catalog/v1", Project: project, Repository: repository, Source: receipt, Runtime: runtime,
		Declarations: []model.Declaration{}, ModuleCalls: []model.Operation{}, Imports: []string{}, Status: "unknown",
		Unresolved: []string{"Imports, receivers, overloads, control flow and effects need semantic resolution.", "Syntax-derived operations are not executable lowering or runtime-equivalence evidence."}}
	nodes, snippets, operations := 0, 0, 0
	moduleDependencies := []string{}
	var walk func(*sitter.Node, string, int, int) error
	walk = func(n *sitter.Node, prefix string, owner, depth int) error {
		if err := ctx.Err(); err != nil {
			return err
		}
		nodes++
		if nodes > 200000 || depth > 128 {
			return fmt.Errorf("source discovery exceeds 200000 nodes or depth 128")
		}
		kind := n.Kind()
		if isImport(kind) {
			result.Imports = append(result.Imports, n.Utf8Text(content))
		}
		if isScope(kind) {
			if name := n.ChildByFieldName("name"); name != nil {
				prefix += name.Utf8Text(content) + "."
			}
		}
		if isMethod(kind) {
			name := n.ChildByFieldName("name")
			if name != nil {
				if len(result.Declarations) >= 5000 {
					return fmt.Errorf("source discovery exceeds 5000 declarations")
				}
				declaration, err := unknownDeclaration(receipt, prefix+name.Utf8Text(content), runtime, span(n))
				if err != nil {
					return err
				}
				result.Declarations = append(result.Declarations, declaration)
				owner = len(result.Declarations) - 1
				prefix += name.Utf8Text(content) + "."
			}
		}
		if op, dependency, ok := operation(n, content); ok {
			operations++
			snippets += len(op.Expression)
			if operations > 20000 || snippets > 4<<20 {
				return fmt.Errorf("source discovery exceeds 20000 operations or 4 MiB of source snippets")
			}
			if owner < 0 {
				result.ModuleCalls = append(result.ModuleCalls, op)
				if dependency != "" {
					moduleDependencies = append(moduleDependencies, dependency)
				}
			} else {
				result.Declarations[owner].Operations = append(result.Declarations[owner].Operations, op)
				if dependency != "" {
					result.Declarations[owner].Dependencies = append(result.Declarations[owner].Dependencies, dependency)
				}
			}
		}
		for i := uint(0); i < n.NamedChildCount(); i++ {
			if err := walk(n.NamedChild(i), prefix, owner, depth+1); err != nil {
				return err
			}
		}
		return nil
	}
	prefix := ""
	// C# file-scoped namespaces are siblings of their declarations in the AST.
	for i := uint(0); i < tree.RootNode().NamedChildCount(); i++ {
		n := tree.RootNode().NamedChild(i)
		if n.Kind() == "file_scoped_namespace_declaration" {
			if name := n.ChildByFieldName("name"); name != nil {
				prefix = name.Utf8Text(content) + "."
			}
		}
	}
	if err := walk(tree.RootNode(), prefix, -1, 0); err != nil {
		return model.ParsedFile{}, err
	}
	if language == syntax.Python {
		result.Runtime = pythonRuntime(result.Imports)
	}
	if len(result.ModuleCalls) > 0 {
		module, err := unknownDeclaration(receipt, "<module>", result.Runtime, model.Span{EndByte: uint(len(content)), Line: 1})
		if err != nil {
			return model.ParsedFile{}, err
		}
		module.Operations = result.ModuleCalls
		module.Dependencies = moduleDependencies
		result.Declarations = append(result.Declarations, module)
	}
	for i := range result.Declarations {
		d := &result.Declarations[i]
		d.Runtime = result.Runtime
		d.Method.Profile = string(result.Runtime) + "/unbound/v1"
		d.Method.ID, err = model.MethodID(d.Method)
		if err != nil {
			return model.ParsedFile{}, err
		}
		d.Dependencies = unique(d.Dependencies)
	}
	result.Imports = unique(result.Imports)
	return result, nil
}

func sourceLanguage(file string) (syntax.Language, model.Runtime, error) {
	switch path.Ext(file) {
	case ".py":
		return syntax.Python, model.PythonUnbound, nil
	case ".cs":
		return syntax.CSharp, model.DotNet, nil
	case ".ts":
		return syntax.TypeScript, model.TypeScript, nil
	case ".tsx":
		return syntax.TSX, model.TypeScript, nil
	default:
		return "", "", fmt.Errorf("unsupported source extension for %s", file)
	}
}

func unknownDeclaration(receipt model.Source, name string, runtime model.Runtime, location model.Span) (model.Declaration, error) {
	method := model.Method{Format: model.Format, Profile: string(runtime) + "/unbound/v1", Source: receipt, Function: name, Status: "unknown",
		Parameters: []model.Parameter{}, Steps: []model.Step{}, Diagnostics: []model.Diagnostic{{Line: location.Line,
			Message: fmt.Sprintf("Runtime lowering and parameter bindings unresolved for declaration at bytes %d:%d.", location.StartByte, location.EndByte)}}}
	var err error
	method.ID, err = model.MethodID(method)
	return model.Declaration{Method: method, Runtime: runtime, Span: location, Operations: []model.Operation{}, Dependencies: []string{}}, err
}

func unique(values []string) []string {
	seen := map[string]bool{}
	result := []string{}
	for _, value := range values {
		if !seen[value] {
			seen[value] = true
			result = append(result, value)
		}
	}
	sort.Strings(result)
	return result
}

func pythonRuntime(imports []string) model.Runtime {
	pandas, spark := false, false
	for _, declaration := range imports {
		for _, word := range strings.Fields(declaration) {
			pandas = pandas || strings.Trim(word, ",") == "pandas" || strings.HasPrefix(word, "pandas.")
			spark = spark || strings.Trim(word, ",") == "pyspark" || strings.HasPrefix(word, "pyspark.")
		}
	}
	if pandas && !spark {
		return model.Pandas
	}
	if spark && !pandas {
		return model.PySpark
	}
	return model.PythonUnbound
}
