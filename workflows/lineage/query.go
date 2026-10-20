package lineage

import (
	"context"
	"fmt"
	"sort"
	"strings"
)

const (
	defaultSearchLimit    = 20
	maxSearchLimit        = 100
	defaultTraversalDepth = 1
	maxTraversalDepth     = 10
	defaultTraversalLimit = 100
	maxTraversalLimit     = 500
	defaultHistoryLimit   = 20
	maxHistoryLimit       = 100
)

// Direction identifies which side of a node to traverse.
type Direction string

const (
	// Upstream follows edge targets to their sources.
	Upstream Direction = "upstream"
	// Downstream follows edge sources to their targets.
	Downstream Direction = "downstream"
)

// SearchResult contains deterministic dataset matches.
type SearchResult struct {
	Graph Graph
	Nodes []Node
}

// TraversalResult contains a bounded graph walk.
type TraversalResult struct {
	Graph     Graph
	Root      Node
	Direction Direction
	Depth     int
	Nodes     []Node
	Edges     []Edge
	Truncated bool
}

// Revision records one graph version's node state.
type Revision struct {
	Graph       Graph
	ChangeType  string
	Node        *Node
	ContentHash string
}

// Service validates and executes read-only lineage queries.
type Service struct {
	source QuerySource
}

// NewService creates a query service over one graph source.
func NewService(source QuerySource) (*Service, error) {
	if source == nil {
		return nil, fmt.Errorf("lineage query source must not be nil")
	}
	return &Service{source: source}, nil
}

// SearchDatasets finds datasets by identity, fields, or synchronized meaning.
func (s *Service) SearchDatasets(
	ctx context.Context,
	query string,
	limit int,
) (SearchResult, error) {
	query = strings.TrimSpace(query)
	if query == "" {
		return SearchResult{}, fmt.Errorf("query must not be empty")
	}
	if limit == 0 {
		limit = defaultSearchLimit
	}
	if err := bounded("limit", limit, maxSearchLimit); err != nil {
		return SearchResult{}, err
	}
	graph, err := s.source.Latest(ctx)
	if err != nil {
		return SearchResult{}, err
	}
	needle := strings.ToLower(query)
	matches := make([]Node, 0)
	for _, node := range graph.Nodes {
		if node.Kind == "dataset" && nodeMatches(node, needle) {
			matches = append(matches, node)
		}
	}
	sort.Slice(matches, func(i, j int) bool {
		left, right := searchKey(matches[i], needle), searchKey(matches[j], needle)
		if left.rank != right.rank {
			return left.rank < right.rank
		}
		return matches[i].ID < matches[j].ID
	})
	if len(matches) > limit {
		matches = matches[:limit]
	}
	return SearchResult{Graph: graph, Nodes: matches}, nil
}

// Traverse performs a bounded upstream or downstream graph walk.
func (s *Service) Traverse(
	ctx context.Context,
	nodeID string,
	direction Direction,
	depth, limit int,
) (TraversalResult, error) {
	nodeID = strings.TrimSpace(nodeID)
	if nodeID == "" {
		return TraversalResult{}, fmt.Errorf("node_id must not be empty")
	}
	if direction != Upstream && direction != Downstream {
		return TraversalResult{}, fmt.Errorf("direction must be upstream or downstream")
	}
	if depth == 0 {
		depth = defaultTraversalDepth
	}
	if limit == 0 {
		limit = defaultTraversalLimit
	}
	if err := bounded("depth", depth, maxTraversalDepth); err != nil {
		return TraversalResult{}, err
	}
	if err := bounded("limit", limit, maxTraversalLimit); err != nil {
		return TraversalResult{}, err
	}
	graph, err := s.source.Latest(ctx)
	if err != nil {
		return TraversalResult{}, err
	}
	nodes := make(map[string]Node, len(graph.Nodes))
	for _, node := range graph.Nodes {
		nodes[node.ID] = node
	}
	root, ok := nodes[nodeID]
	if !ok {
		return TraversalResult{}, fmt.Errorf("lineage node does not exist: %s", nodeID)
	}
	reached, edges, truncated := walk(graph.Edges, nodeID, direction, depth, limit)
	resultNodes := make([]Node, 0, len(reached))
	for id := range reached {
		resultNodes = append(resultNodes, nodes[id])
	}
	sort.Slice(resultNodes, func(i, j int) bool { return resultNodes[i].ID < resultNodes[j].ID })
	sort.Slice(edges, func(i, j int) bool { return edges[i].ID < edges[j].ID })
	return TraversalResult{
		Graph: graph, Root: root, Direction: direction, Depth: depth,
		Nodes: resultNodes, Edges: edges, Truncated: truncated,
	}, nil
}

// TransformationDetails returns one complete stored node.
func (s *Service) TransformationDetails(
	ctx context.Context,
	nodeID string,
) (Graph, Node, error) {
	nodeID = strings.TrimSpace(nodeID)
	if nodeID == "" {
		return Graph{}, Node{}, fmt.Errorf("node_id must not be empty")
	}
	graph, err := s.source.Latest(ctx)
	if err != nil {
		return Graph{}, Node{}, err
	}
	for _, node := range graph.Nodes {
		if node.ID == nodeID {
			return graph, node, nil
		}
	}
	return Graph{}, Node{}, fmt.Errorf("lineage node does not exist: %s", nodeID)
}

// ChangeHistory returns node changes from newest local graph versions.
func (s *Service) ChangeHistory(
	ctx context.Context,
	nodeID string,
	limit int,
) ([]Revision, error) {
	nodeID = strings.TrimSpace(nodeID)
	if nodeID == "" {
		return nil, fmt.Errorf("node_id must not be empty")
	}
	if limit == 0 {
		limit = defaultHistoryLimit
	}
	if err := bounded("limit", limit, maxHistoryLimit); err != nil {
		return nil, err
	}
	graphs, err := s.source.History(ctx, limit+1)
	if err != nil {
		return nil, err
	}
	revisions := make([]Revision, 0, len(graphs))
	for index, graph := range graphs {
		current := findNode(graph, nodeID)
		var older *Node
		if index+1 < len(graphs) {
			older = findNode(graphs[index+1], nodeID)
		}
		change := classifyChange(current, older)
		if change == "" {
			continue
		}
		revision := Revision{Graph: graph, ChangeType: change, Node: current}
		if current != nil {
			revision.ContentHash = current.ContentHash()
		}
		revisions = append(revisions, revision)
	}
	return revisions, nil
}

type matchKey struct{ rank int }

func nodeMatches(node Node, needle string) bool {
	values := []string{node.ID, node.stringValue("name"), node.stringValue("description")}
	for _, field := range node.sliceValue("fields") {
		if fieldMap, ok := field.(map[string]any); ok {
			if name, ok := fieldMap["name"].(string); ok {
				values = append(values, name)
			}
		}
	}
	values = append(values, semanticValues(node)...)
	terms := strings.Fields(needle)
	combined := strings.ToLower(strings.Join(values, " "))
	for _, term := range terms {
		if !strings.Contains(combined, term) {
			return false
		}
	}
	return len(terms) > 0
}

func semanticValues(node Node) []string {
	facets, _ := node.Data["facets"].(map[string]any)
	meaning, _ := facets["q2_semanticMeaning"].(map[string]any)
	entries, _ := meaning["entries"].([]any)
	values := make([]string, 0, len(entries)*2)
	for _, rawEntry := range entries {
		entry, _ := rawEntry.(map[string]any)
		if description, ok := entry["description"].(string); ok {
			values = append(values, description)
		}
		if context, ok := entry["businessContext"].(string); ok {
			values = append(values, context)
		}
	}
	return values
}

func searchKey(node Node, needle string) matchKey {
	name := strings.ToLower(node.stringValue("name"))
	switch {
	case name == needle || strings.ToLower(node.ID) == needle:
		return matchKey{rank: 0}
	case strings.HasPrefix(name, needle):
		return matchKey{rank: 1}
	case strings.Contains(name, needle):
		return matchKey{rank: 2}
	default:
		return matchKey{rank: 3}
	}
}

func walk(
	edges []Edge,
	root string,
	direction Direction,
	depth, limit int,
) (map[string]struct{}, []Edge, bool) {
	type item struct {
		id    string
		depth int
	}
	adjacency := make(map[string][]struct {
		id   string
		edge Edge
	})
	for _, edge := range edges {
		from, to := edge.Source, edge.Target
		if direction == Upstream {
			from, to = edge.Target, edge.Source
		}
		adjacency[from] = append(adjacency[from], struct {
			id   string
			edge Edge
		}{id: to, edge: edge})
	}
	for key := range adjacency {
		sort.Slice(adjacency[key], func(i, j int) bool {
			if adjacency[key][i].id != adjacency[key][j].id {
				return adjacency[key][i].id < adjacency[key][j].id
			}
			return adjacency[key][i].edge.ID < adjacency[key][j].edge.ID
		})
	}
	reached := make(map[string]struct{})
	selected := make([]Edge, 0)
	queue := []item{{id: root, depth: 0}}
	truncated := false
	for len(queue) > 0 && !truncated {
		current := queue[0]
		queue = queue[1:]
		if current.depth >= depth {
			continue
		}
		for _, next := range adjacency[current.id] {
			if next.id == root {
				continue
			}
			if _, exists := reached[next.id]; exists {
				continue
			}
			if len(reached) >= limit {
				truncated = true
				break
			}
			reached[next.id] = struct{}{}
			selected = append(selected, next.edge)
			queue = append(queue, item{id: next.id, depth: current.depth + 1})
		}
	}
	return reached, selected, truncated
}

func findNode(graph Graph, id string) *Node {
	for index := range graph.Nodes {
		if graph.Nodes[index].ID == id {
			return &graph.Nodes[index]
		}
	}
	return nil
}

func classifyChange(current, older *Node) string {
	switch {
	case current == nil && older == nil:
		return ""
	case current == nil:
		return "removed"
	case older == nil:
		return "created"
	case current.ContentHash() != older.ContentHash():
		return "changed"
	default:
		return ""
	}
}

func bounded(name string, value, maximum int) error {
	if value < 1 || value > maximum {
		return fmt.Errorf("%s must be between 1 and %d", name, maximum)
	}
	return nil
}
