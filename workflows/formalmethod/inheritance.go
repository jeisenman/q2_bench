package formalmethod

import (
	"fmt"
	"strings"

	sitter "github.com/tree-sitter/go-tree-sitter"
)

func (r *interfaceResolver) parent(m *parsedModule, class *sitter.Node) (*parsedModule, *sitter.Node, error) {
	bases := children(class.ChildByFieldName("superclasses"))
	if len(bases) == 0 {
		return nil, nil, fmt.Errorf("no metadata parent")
	}
	if len(bases) != 1 || bases[0].Kind() != "identifier" {
		return nil, nil, fmt.Errorf("multiple or computed metadata bases require MRO resolution")
	}
	name := bases[0].Utf8Text(m.content)
	if local := classNode(m, name); local != nil {
		return m, local, nil
	}
	qualified := m.imports[name]
	split := strings.LastIndex(qualified, ".")
	if split < 1 {
		return nil, nil, fmt.Errorf("unresolved metadata parent %s", name)
	}
	owner, err := r.load(qualified[:split])
	if err != nil {
		return nil, nil, err
	}
	parent := classNode(owner, qualified[split+1:])
	if parent == nil {
		return nil, nil, fmt.Errorf("metadata parent re-export requires resolution: %s", qualified)
	}
	return owner, parent, nil
}

func (r *interfaceResolver) classValue(m *parsedModule, class *sitter.Node, name string, depth int) (*parsedModule, *sitter.Node, error) {
	if depth > 32 {
		return nil, nil, fmt.Errorf("metadata inheritance exceeds 32 classes")
	}
	if value := classConstant(class, name, m.content); value != nil {
		return m, value, nil
	}
	parent, base, err := r.parent(m, class)
	if err != nil {
		return nil, nil, err
	}
	return r.classValue(parent, base, name, depth+1)
}

func (r *interfaceResolver) schemaOwner(m *parsedModule, class *sitter.Node, major, depth int) (*parsedModule, *sitter.Node, error) {
	if depth > 32 {
		return nil, nil, fmt.Errorf("schema inheritance exceeds 32 classes")
	}
	name := fmt.Sprintf("_schema_v%d", major)
	for _, n := range children(class.ChildByFieldName("body")) {
		if n.Kind() == "decorated_definition" {
			n = n.ChildByFieldName("definition")
		}
		if n.Kind() == "function_definition" && n.ChildByFieldName("name").Utf8Text(m.content) == name {
			return m, class, nil
		}
	}
	parent, base, err := r.parent(m, class)
	if err != nil {
		return nil, nil, err
	}
	return r.schemaOwner(parent, base, major, depth+1)
}
