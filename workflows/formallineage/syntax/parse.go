// Package syntax parses bounded application source using standard grammars.
package syntax

import (
	"context"
	"fmt"
	"time"
	"unsafe"

	sitter "github.com/tree-sitter/go-tree-sitter"
	csharp "github.com/tree-sitter/tree-sitter-c-sharp/bindings/go"
	python "github.com/tree-sitter/tree-sitter-python/bindings/go"
	typescript "github.com/tree-sitter/tree-sitter-typescript/bindings/go"
)

// Language selects a source grammar without assigning runtime semantics.
type Language string

const (
	// Python selects the existing pinned Python grammar.
	Python Language = "python"
	// CSharp selects the C# grammar.
	CSharp Language = "csharp"
	// TypeScript selects the TypeScript grammar.
	TypeScript Language = "typescript"
	// TSX selects TypeScript with JSX syntax.
	TSX Language = "tsx"
)

// Parse returns a caller-owned tree or an explicit syntax/budget error.
func Parse(ctx context.Context, language Language, content []byte) (*sitter.Tree, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	if len(content) > 1<<20 {
		return nil, fmt.Errorf("source exceeds 1 MiB")
	}
	var grammar unsafe.Pointer
	switch language {
	case Python:
		grammar = python.Language()
	case CSharp:
		grammar = csharp.Language()
	case TypeScript:
		grammar = typescript.LanguageTypescript()
	case TSX:
		grammar = typescript.LanguageTSX()
	default:
		return nil, fmt.Errorf("unsupported source language %q", language)
	}
	p := sitter.NewParser()
	defer p.Close()
	if err := p.SetLanguage(sitter.NewLanguage(grammar)); err != nil {
		return nil, err
	}
	deadline := time.Now().Add(5 * time.Second)
	tree := p.ParseWithOptions(func(offset int, _ sitter.Point) []byte {
		if offset >= len(content) {
			return nil
		}
		return content[offset:]
	}, nil, &sitter.ParseOptions{ProgressCallback: func(sitter.ParseState) bool {
		return ctx.Err() != nil || time.Now().After(deadline)
	}})
	if tree == nil {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		return nil, fmt.Errorf("%s parse timed out", language)
	}
	if tree.RootNode().HasError() {
		tree.Close()
		return nil, fmt.Errorf("%s source has syntax errors or missing nodes", language)
	}
	return tree, nil
}
