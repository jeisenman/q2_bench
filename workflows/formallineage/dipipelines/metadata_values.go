package dipipelines

import (
	"fmt"
	"strconv"

	sitter "github.com/tree-sitter/go-tree-sitter"
)

func metadataNumber(caller *parsedModule, n *sitter.Node, owner *parsedModule, class *sitter.Node, qualified string) (int, error) {
	if n.Kind() == "integer" {
		v, err := strconv.Atoi(n.Utf8Text(caller.content))
		if err != nil || v < 0 {
			return 0, fmt.Errorf("invalid metadata version")
		}
		return v, nil
	}
	if n.Kind() == "attribute" {
		object := n.ChildByFieldName("object")
		if object.Kind() == "identifier" && caller.imports[object.Utf8Text(caller.content)] == qualified {
			name := n.ChildByFieldName("attribute").Utf8Text(caller.content)
			v := classConstant(class, name, owner.content)
			if v != nil && v.Kind() == "integer" {
				number, err := strconv.Atoi(v.Utf8Text(owner.content))
				if err == nil && number >= 0 {
					return number, nil
				}
			}
		}
	}
	return 0, fmt.Errorf("metadata version requires a literal or the pinned metadata class constant")
}

func sourceNameDefault(class *sitter.Node, source []byte) string {
	for _, f := range children(class.ChildByFieldName("body")) {
		if f.Kind() != "function_definition" || f.ChildByFieldName("name").Utf8Text(source) != "__init__" {
			continue
		}
		for _, p := range children(f.ChildByFieldName("parameters")) {
			name := p.ChildByFieldName("name")
			value := p.ChildByFieldName("value")
			if name != nil && value != nil && name.Utf8Text(source) == "data_source_name" {
				s, _ := pythonString(value.Utf8Text(source))
				return s
			}
		}
	}
	return ""
}
