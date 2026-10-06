package agents

import (
	"fmt"
	"sort"
	"strings"
	"sync"
)

// Factory builds one dependency-injected agent.
type Factory func() Agent

// Registry stores unique named agent factories.
type Registry struct {
	mu        sync.RWMutex
	factories map[string]Factory
}

// NewRegistry creates an empty registry.
func NewRegistry() *Registry {
	return &Registry{factories: make(map[string]Factory)}
}

// Register adds a unique agent factory.
func (r *Registry) Register(name string, factory Factory) error {
	if strings.TrimSpace(name) == "" {
		return fmt.Errorf("agent name must not be empty")
	}
	if factory == nil {
		return fmt.Errorf("agent factory must not be nil")
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	if _, exists := r.factories[name]; exists {
		return fmt.Errorf("agent %q is already registered", name)
	}
	r.factories[name] = factory
	return nil
}

// Create builds a named agent.
func (r *Registry) Create(name string) (Agent, error) {
	r.mu.RLock()
	factory, exists := r.factories[name]
	r.mu.RUnlock()
	if !exists {
		names := r.Names()
		available := "none"
		if len(names) > 0 {
			available = strings.Join(names, ", ")
		}
		return nil, fmt.Errorf("unknown agent %q; available agents: %s", name, available)
	}
	return factory(), nil
}

// Names returns registered names in deterministic order.
func (r *Registry) Names() []string {
	r.mu.RLock()
	defer r.mu.RUnlock()
	names := make([]string, 0, len(r.factories))
	for name := range r.factories {
		names = append(names, name)
	}
	sort.Strings(names)
	return names
}
