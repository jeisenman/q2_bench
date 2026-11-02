package main

import (
	"encoding/json"
	"fmt"
	"strings"
)

func filterCases(data []byte, stages string) ([]byte, error) {
	var fixture map[string]json.RawMessage
	if err := json.Unmarshal(data, &fixture); err != nil {
		return nil, err
	}
	var cases []json.RawMessage
	if err := json.Unmarshal(fixture["cases"], &cases); err != nil {
		return nil, err
	}
	wanted := make(map[string]bool)
	for _, stage := range strings.Split(stages, ",") {
		if stage == "" {
			return nil, fmt.Errorf("empty stage selector")
		}
		wanted[stage] = false
	}
	var selected []json.RawMessage
	for _, item := range cases {
		var meta struct {
			Stage string `json:"stage"`
		}
		if err := json.Unmarshal(item, &meta); err != nil {
			return nil, err
		}
		if _, ok := wanted[meta.Stage]; ok {
			selected = append(selected, item)
			wanted[meta.Stage] = true
		}
	}
	for stage, found := range wanted {
		if !found {
			return nil, fmt.Errorf("unknown or empty stage: %s", stage)
		}
	}
	encoded, err := json.Marshal(selected)
	if err != nil {
		return nil, err
	}
	fixture["cases"] = encoded
	return json.Marshal(fixture)
}
