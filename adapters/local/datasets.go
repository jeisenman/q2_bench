// Package local contains deterministic local infrastructure adapters.
package local

import (
	"context"
	"fmt"

	"github.com/jeisenman/q2_bench/domain"
)

// DatasetProvider serves immutable records from an in-memory mapping.
type DatasetProvider struct {
	Datasets map[string][]domain.Attributes
}

// FetchRecords returns records matching every equality filter.
func (p DatasetProvider) FetchRecords(
	_ context.Context,
	dataset string,
	filters domain.Attributes,
	limit int,
) ([]domain.Attributes, error) {
	if limit < 1 {
		return nil, fmt.Errorf("limit must be at least 1")
	}
	records := p.Datasets[dataset]
	matches := make([]domain.Attributes, 0, min(limit, len(records)))
	required := attributesMap(filters)
	for _, record := range records {
		if matchesAttributes(attributesMap(record), required) {
			matches = append(matches, cloneAttributes(record))
			if len(matches) == limit {
				break
			}
		}
	}
	return matches, nil
}

func attributesMap(attributes domain.Attributes) map[string]any {
	values := make(map[string]any, len(attributes))
	for _, attribute := range attributes {
		values[attribute.Name] = attribute.Value
	}
	return values
}

func matchesAttributes(record, filters map[string]any) bool {
	for key, expected := range filters {
		if record[key] != expected {
			return false
		}
	}
	return true
}

func cloneAttributes(attributes domain.Attributes) domain.Attributes {
	return append(domain.Attributes(nil), attributes...)
}
