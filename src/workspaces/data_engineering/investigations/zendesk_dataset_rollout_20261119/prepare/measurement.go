package main

import (
	"encoding/json"
	"fmt"
	"os"
	"sort"
)

type byteDistribution struct {
	Median int `json:"median"`
	P95    int `json:"p95"`
	Max    int `json:"max"`
}
type componentMeasurements struct {
	samples              map[string][]int
	largestBytes         int
	largestNode          string
	largestComponents    map[string]int
	largestTechnicalKeys map[string]int
}

func (m *componentMeasurements) add(input preparedInput, b []byte) error {
	if m.samples == nil {
		m.samples = map[string][]int{}
	}
	sizes := map[string]int{}
	for name, value := range map[string]any{"target": input.Target, "definition": input.Definition, "technical_evidence": input.Technical, "zendesk_evidence": input.Zendesk} {
		encoded, err := formatted(value)
		if err != nil {
			return err
		}
		sizes[name] = len(encoded)
		m.samples[name] = append(m.samples[name], len(encoded))
	}
	m.samples["complete_input"] = append(m.samples["complete_input"], len(b))
	if len(b) > m.largestBytes {
		m.largestBytes = len(b)
		m.largestNode = input.Target.NodeID
		m.largestComponents = sizes
		m.largestTechnicalKeys = map[string]int{}
		for name, value := range input.Technical {
			var decoded any
			if err := decode(value, &decoded); err != nil {
				return err
			}
			encoded, err := formatted(decoded)
			if err != nil {
				return err
			}
			m.largestTechnicalKeys[name] = len(encoded)
		}
	}
	return nil
}

func (m componentMeasurements) print(failures []preflightFailure, stats preparationStats) error {
	summary := map[string]byteDistribution{}
	for name, values := range m.samples {
		sort.Ints(values)
		summary[name] = byteDistribution{Median: values[len(values)/2], P95: values[(len(values)*95-1)/100], Max: values[len(values)-1]}
	}
	result := struct {
		Contract             string                      `json:"measurement_contract"`
		Count                int                         `json:"count"`
		Components           map[string]byteDistribution `json:"component_bytes"`
		LargestNode          string                      `json:"largest_node"`
		LargestInputBytes    int                         `json:"largest_input_bytes"`
		LargestComponents    map[string]int              `json:"largest_components"`
		LargestTechnicalKeys map[string]int              `json:"largest_technical_evidence_keys"`
		Statistics           preparationStats            `json:"statistics"`
		BoundFailures        []preflightFailure          `json:"bound_failures"`
	}{"standalone 2-space JSON component bytes; complete input bytes include actual nesting and caller metadata; read-only", len(m.samples["complete_input"]), summary, m.largestNode, m.largestBytes, m.largestComponents, m.largestTechnicalKeys, stats, failures}
	b, err := json.MarshalIndent(result, "", "  ")
	if err != nil {
		return err
	}
	if _, err := fmt.Fprintln(os.Stdout, string(b)); err != nil {
		return err
	}
	return nil
}
