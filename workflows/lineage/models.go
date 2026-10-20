// Package lineage provides deterministic queries over staged repository graphs.
package lineage

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strings"
)

// Node is one job or dataset from a lineage graph.
type Node struct {
	ID   string
	Kind string
	Data map[string]any
}

// Summary returns the compact representation used by MCP search and traversal.
func (n Node) Summary() map[string]any {
	semanticStatus, _, _ := n.semanticSummary()
	return map[string]any{
		"id":                  n.ID,
		"kind":                n.Kind,
		"namespace":           n.stringValue("namespace"),
		"name":                n.stringValue("name"),
		"description":         n.Data["description"],
		"version":             n.Data["version"],
		"owners":              n.Data["owners"],
		"fieldCount":          len(n.sliceValue("fields")),
		"locationCount":       len(n.sliceValue("locations")),
		"transformationCount": len(n.sliceValue("transformations")),
		"semanticStatus":      semanticStatus,
	}
}

// SearchSummary includes meaning text for a dataset returned by semantic search.
func (n Node) SearchSummary() map[string]any {
	result := n.Summary()
	_, description, businessContext := n.semanticSummary()
	result["semanticDescription"] = description
	result["semanticBusinessContext"] = businessContext
	return result
}

// ContentHash returns the stable hash of the stored node payload.
func (n Node) ContentHash() string {
	encoded, err := json.Marshal(n.Data)
	if err != nil {
		return ""
	}
	sum := sha256.Sum256(encoded)
	return hex.EncodeToString(sum[:])
}

func (n Node) stringValue(key string) string {
	value, _ := n.Data[key].(string)
	return value
}

func (n Node) sliceValue(key string) []any {
	values, _ := n.Data[key].([]any)
	return values
}

func (n Node) semanticSummary() (string, any, any) {
	facets, _ := n.Data["facets"].(map[string]any)
	meaning, _ := facets["q2_semanticMeaning"].(map[string]any)
	status, _ := meaning["status"].(string)
	entries, _ := meaning["entries"].([]any)
	if len(entries) == 0 {
		return status, nil, nil
	}
	entry, _ := entries[0].(map[string]any)
	return status, entry["description"], entry["businessContext"]
}

// Edge is one directed relationship between two graph nodes.
type Edge struct {
	ID     string
	Source string
	Target string
	Kind   string
	Data   map[string]any
}

// Output returns the original edge payload for MCP responses.
func (e Edge) Output() map[string]any {
	return e.Data
}

// Graph is one immutable staged lineage graph version.
type Graph struct {
	Manifest map[string]any
	Nodes    []Node
	Edges    []Edge
}

// ParseGraph decodes and validates one generated lineage artifact.
func ParseGraph(content []byte) (Graph, error) {
	var root map[string]any
	if err := json.Unmarshal(content, &root); err != nil {
		return Graph{}, fmt.Errorf("decode lineage graph: %w", err)
	}
	if root == nil {
		return Graph{}, fmt.Errorf("lineage graph must be a JSON object")
	}
	manifest, ok := root["manifest"].(map[string]any)
	if !ok {
		return Graph{}, fmt.Errorf("lineage graph manifest must be an object")
	}
	rawNodes, ok := root["nodes"].([]any)
	if !ok {
		return Graph{}, fmt.Errorf("lineage graph nodes must be an array")
	}
	rawEdges, ok := root["edges"].([]any)
	if !ok {
		return Graph{}, fmt.Errorf("lineage graph edges must be an array")
	}
	graph := Graph{Manifest: manifest}
	known := make(map[string]struct{}, len(rawNodes))
	for index, raw := range rawNodes {
		data, ok := raw.(map[string]any)
		if !ok {
			return Graph{}, fmt.Errorf("lineage node %d must be an object", index)
		}
		node, err := parseNode(data)
		if err != nil {
			return Graph{}, fmt.Errorf("lineage node %d: %w", index, err)
		}
		if _, exists := known[node.ID]; exists {
			return Graph{}, fmt.Errorf("duplicate lineage node %q", node.ID)
		}
		known[node.ID] = struct{}{}
		graph.Nodes = append(graph.Nodes, node)
	}
	for index, raw := range rawEdges {
		data, ok := raw.(map[string]any)
		if !ok {
			return Graph{}, fmt.Errorf("lineage edge %d must be an object", index)
		}
		edge, err := parseEdge(data)
		if err != nil {
			return Graph{}, fmt.Errorf("lineage edge %d: %w", index, err)
		}
		if _, exists := known[edge.Source]; !exists {
			return Graph{}, fmt.Errorf("lineage edge %q references missing source %q", edge.ID, edge.Source)
		}
		if _, exists := known[edge.Target]; !exists {
			return Graph{}, fmt.Errorf("lineage edge %q references missing target %q", edge.ID, edge.Target)
		}
		graph.Edges = append(graph.Edges, edge)
	}
	return graph, nil
}

func parseNode(data map[string]any) (Node, error) {
	id, err := requiredString(data, "id")
	if err != nil {
		return Node{}, err
	}
	kind, err := requiredString(data, "kind")
	if err != nil {
		return Node{}, err
	}
	if kind != "dataset" && kind != "job" {
		return Node{}, fmt.Errorf("kind must be dataset or job")
	}
	return Node{ID: id, Kind: kind, Data: data}, nil
}

func parseEdge(data map[string]any) (Edge, error) {
	id, err := requiredString(data, "id")
	if err != nil {
		return Edge{}, err
	}
	source, err := requiredString(data, "source")
	if err != nil {
		return Edge{}, err
	}
	target, err := requiredString(data, "target")
	if err != nil {
		return Edge{}, err
	}
	kind, err := requiredString(data, "kind")
	if err != nil {
		return Edge{}, err
	}
	return Edge{ID: id, Source: source, Target: target, Kind: kind, Data: data}, nil
}

func requiredString(data map[string]any, key string) (string, error) {
	value, ok := data[key].(string)
	if !ok || strings.TrimSpace(value) == "" {
		return "", fmt.Errorf("%s must be a non-empty string", key)
	}
	return value, nil
}
