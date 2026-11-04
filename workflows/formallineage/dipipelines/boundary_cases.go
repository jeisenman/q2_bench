package dipipelines

import (
	"context"
	"fmt"
	"strings"

	sitter "github.com/tree-sitter/go-tree-sitter"
)

func boundaryAdapter(expression string, params []string) string {
	return "from pyspark.sql import functions as F\nfrom pyspark.sql.types import StringType\ndef boundary_clause(" + strings.Join(params, ", ") + "):\n    return " + strings.ReplaceAll(expression, "\n", "\n    ") + "\n"
}

func clauseCases(ctx context.Context, module *parsedModule, clause BoundaryClause) ([]ComparisonCase, string) {
	if !in(clause.Kind, "filter", "join", "dropna", "drop", "projection") {
		return nil, "Source-specific input/schema, control-flow, or effect oracle not bound."
	}
	var node *sitter.Node
	var find func(*sitter.Node)
	find = func(n *sitter.Node) {
		if n.StartByte() == clause.StartByte && n.EndByte() == clause.EndByte && n.Kind() == "call" {
			node = n
			return
		}
		if n.StartByte() <= clause.StartByte && n.EndByte() >= clause.EndByte {
			for _, x := range children(n) {
				find(x)
			}
		}
	}
	find(module.tree.RootNode())
	if node == nil {
		return nil, "Clause is not a complete call."
	}
	f := node.ChildByFieldName("function")
	if f.Kind() != "attribute" || f.ChildByFieldName("object").Kind() != "identifier" {
		return nil, "Receiver needs prior transformations or dynamic resolution."
	}
	receiver := f.ChildByFieldName("object").Utf8Text(module.content)
	if in(receiver, "self", "F", "spark", "pd") {
		return nil, "Receiver is not an explicitly bound synthetic relation."
	}
	// F is copied into the adapter only if the original module binds it to Spark.
	if strings.Contains(clause.Expression, "F.") && !semanticBindings(module.tree.RootNode(), module.content)["F"] {
		return nil, "Original F namespace is not verified as pyspark.sql.functions."
	}
	if boundaryShadowed(node, module.content) {
		return nil, "An enclosing function shadows a Spark semantic name; original binding is unresolved."
	}
	params := []string{receiver}
	if clause.Kind == "join" {
		args := children(node.ChildByFieldName("arguments"))
		if len(args) == 0 || args[0].Kind() != "identifier" || args[0].Utf8Text(module.content) == receiver {
			return nil, "Join requires two separately bound relation identifiers."
		}
		params = append(params, args[0].Utf8Text(module.content))
	}
	adapter, literals := literalClauseAdapter(module, node, params)
	source := Source{Commit: module.source.Commit, Path: "__boundary__/" + clause.ID + ".py", SHA256: hash([]byte(adapter))}
	method, err := Compile([]byte(adapter), source, "boundary_clause", params)
	if err != nil {
		return nil, err.Error()
	}
	if method.Status != "compiled" {
		return nil, fmt.Sprintf("Independent clause compiler: %v", method.Diagnostics)
	}
	var bindings []Bindings
	var schemas map[string]string
	switch clause.Kind {
	case "filter":
		bindings, schemas, err = filterBoundaryBindings(method, receiver)
	case "join":
		bindings, schemas, err = joinBoundaryBindings(method, params)
	case "dropna":
		bindings, schemas, err = dropnaBoundaryBindings(method, receiver)
	case "drop":
		bindings, schemas, err = dropBoundaryBindings(method, receiver)
	case "projection":
		bindings, schemas, err = projectionBoundaryBindings(method, receiver)
	}
	if err != nil {
		return nil, err.Error()
	}
	result := []ComparisonCase{}
	observedColumns := []string{}
	if method.Steps[0].Expression.Op == "withColumn" {
		if value, ok := expressionLiteral(method.Steps[0].Expression.Args[1]); ok {
			if name, yes := value.(string); yes {
				observedColumns = append(observedColumns, name)
			}
		}
	}
	for i, b := range bindings {
		if _, err := EvaluateOutputs(ctx, method, b); err != nil {
			return nil, "Independent clause prediction: " + err.Error()
		}
		result = append(result, ComparisonCase{ID: fmt.Sprintf("clause:%s:%d", clause.ID, i), Method: method, Bindings: b, SparkSchemas: schemas, Clause: &ClauseEvidence{Source: module.source, StartByte: clause.StartByte, EndByte: clause.EndByte, Adapter: adapter, Literals: literals}, ObserveColumns: observedColumns})
	}
	return result, "Only isolated relation semantics tested; upstream reachability, declared types, missing-column errors, and full job remain unverified."
}

func prepareClause(ctx context.Context, root string, c ComparisonCase, p *ComparisonPayload) error {
	evidence := c.Clause
	key := evidence.Source.Commit + ":" + evidence.Source.Path
	b := []byte(p.Sources[key])
	if len(b) == 0 {
		var err error
		b, err = readGit(ctx, root, evidence.Source.Commit, evidence.Source.Path)
		if err != nil {
			return err
		}
	}
	if hash(b) != evidence.Source.SHA256 || evidence.EndByte > uint(len(b)) || evidence.StartByte >= evidence.EndByte {
		return fmt.Errorf("case %s has invalid original clause evidence", c.ID)
	}
	params := []string{}
	for _, a := range c.Method.Parameters {
		if a.Kind != Table {
			return fmt.Errorf("clause adapters accept only explicitly bound tables")
		}
		params = append(params, a.Name)
	}
	tree, err := parse(b)
	if err != nil {
		return err
	}
	defer tree.Close()
	node := clauseNode(tree.RootNode(), evidence.StartByte, evidence.EndByte)
	if node == nil {
		return fmt.Errorf("clause span is not one original call")
	}
	module := &parsedModule{source: evidence.Source, content: b, tree: tree}
	adapter, literals := literalClauseAdapter(module, node, params)
	if len(literals) != len(evidence.Literals) {
		return fmt.Errorf("clause literal binding receipts differ")
	}
	for i, literal := range literals {
		if literal != evidence.Literals[i] {
			return fmt.Errorf("clause literal binding receipt mismatch")
		}
	}
	if adapter != evidence.Adapter || hash([]byte(adapter)) != c.Method.Source.SHA256 || c.Method.Source.Commit != evidence.Source.Commit {
		return fmt.Errorf("case %s clause adapter does not match original source", c.ID)
	}
	compiled, err := Compile([]byte(adapter), c.Method.Source, "boundary_clause", params)
	if err != nil || compiled.Status != "compiled" || compiled.ID != c.Method.ID {
		return fmt.Errorf("case %s clause method does not match compiled adapter", c.ID)
	}
	p.Sources[evidence.Source.Commit+":"+evidence.Source.Path] = string(b)
	p.Sources[c.Method.Source.Commit+":"+c.Method.Source.Path] = adapter
	return nil
}
