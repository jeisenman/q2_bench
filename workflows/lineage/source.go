package lineage

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

const (
	// GraphPathEnv selects the generated lineage artifact.
	GraphPathEnv = "LINEAGE_GRAPH_PATH"
	// DefaultGraphPath is the local artifact used when no path is configured.
	DefaultGraphPath = "var/lineage/di-pipelines.json"
)

// QuerySource reads immutable graph versions for lineage queries.
type QuerySource interface {
	Latest(context.Context) (Graph, error)
	History(context.Context, int) ([]Graph, error)
}

// JSONSource reads a generated graph artifact from local storage.
type JSONSource struct {
	Path string
}

// NewJSONSource creates a source for one explicit artifact path.
func NewJSONSource(path string) (JSONSource, error) {
	path = strings.TrimSpace(path)
	if path == "" {
		return JSONSource{}, fmt.Errorf("lineage graph path must not be empty")
	}
	return JSONSource{Path: filepath.Clean(path)}, nil
}

// JSONSourceFromEnvironment creates a source from LINEAGE_GRAPH_PATH.
func JSONSourceFromEnvironment() (JSONSource, error) {
	path := strings.TrimSpace(os.Getenv(GraphPathEnv))
	if path == "" {
		path = DefaultGraphPath
	}
	return NewJSONSource(path)
}

// Latest loads the configured graph artifact.
func (s JSONSource) Latest(ctx context.Context) (Graph, error) {
	content, err := s.read(ctx)
	if err != nil {
		return Graph{}, err
	}
	graph, err := ParseGraph(content)
	if err != nil {
		return Graph{}, fmt.Errorf("read lineage graph %s: %w", s.Path, err)
	}
	return graph, nil
}

// History returns the local artifact as the only available graph version.
func (s JSONSource) History(ctx context.Context, limit int) ([]Graph, error) {
	if limit < 1 {
		return nil, fmt.Errorf("lineage history limit must be at least 1")
	}
	graph, err := s.Latest(ctx)
	if err != nil {
		return nil, err
	}
	return []Graph{graph}, nil
}

func (s JSONSource) read(ctx context.Context) ([]byte, error) {
	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	default:
	}
	content, err := os.ReadFile(s.Path)
	if err != nil {
		return nil, fmt.Errorf(
			"lineage graph artifact %s is unavailable: %w",
			s.Path,
			err,
		)
	}
	return content, nil
}
