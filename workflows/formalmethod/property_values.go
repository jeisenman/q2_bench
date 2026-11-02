package formalmethod

import (
	"encoding/json"
	"fmt"
	"math"
	"math/rand/v2"
	"regexp"
	"sort"
	"strings"
)

type propertyField struct{ name, kind string }

func (f propertyField) key() string { return f.name + ":" + f.kind }

var propertyDDL = regexp.MustCompile("^\\s*(?:`([^`]+)`|([A-Za-z_][A-Za-z_0-9]*))\\s+(string|double|boolean)\\s*$")

func propertyFields(ddl string) ([]propertyField, error) {
	fields := []propertyField{}
	seen := map[string]bool{}
	for _, part := range strings.Split(ddl, ",") {
		m := propertyDDL.FindStringSubmatch(part)
		if m == nil {
			return nil, fmt.Errorf("property generator requires explicit primitive string/double/boolean Spark fields, got %q", part)
		}
		name := m[1] + m[2]
		if seen[name] || !simpleColumnName(name) {
			return nil, fmt.Errorf("property generator requires unique simple fields: %q", name)
		}
		seen[name] = true
		fields = append(fields, propertyField{name, m[3]})
	}
	return fields, nil
}

func propertyDomains(c ComparisonCase) (map[string][]any, error) {
	domains := map[string][]any{}
	tables := make([]string, 0, len(c.Bindings.Tables))
	for name := range c.Bindings.Tables {
		tables = append(tables, name)
	}
	sort.Strings(tables)
	for _, name := range tables {
		fields, err := propertyFields(c.SparkSchemas[name])
		if err != nil {
			return nil, err
		}
		for _, field := range fields {
			for _, row := range c.Bindings.Tables[name] {
				value, ok := row[field.name]
				if !ok {
					return nil, fmt.Errorf("property fixture lacks field %s.%s", name, field.name)
				}
				if value == nil {
					continue
				}
				valid := false
				switch v := value.(type) {
				case string:
					valid = field.kind == "string"
				case bool:
					valid = field.kind == "boolean"
				case float64:
					valid = field.kind == "double" && !math.IsInf(v, 0) && !math.IsNaN(v)
				}
				if !valid {
					return nil, fmt.Errorf("property fixture field %s.%s disagrees with its primitive schema", name, field.name)
				}
				domains[field.key()] = append(domains[field.key()], value)
			}
		}
	}
	for key, values := range domains {
		seen := map[string]bool{}
		unique := []any{}
		for _, value := range values {
			b, _ := json.Marshal(value)
			if !seen[string(b)] {
				seen[string(b)] = true
				unique = append(unique, value)
			}
		}
		domains[key] = unique
	}
	return domains, nil
}

func sampledPropertyValue(rng *rand.Rand, field propertyField, candidates []any) (any, error) {
	if rng.IntN(8) == 0 {
		return nil, nil
	}
	if len(candidates) > 0 && rng.IntN(2) == 0 {
		return candidates[rng.IntN(len(candidates))], nil
	}
	switch field.kind {
	case "boolean":
		return rng.IntN(2) == 0, nil
	case "double":
		anchor := float64(0)
		if len(candidates) > 0 {
			anchor = candidates[rng.IntN(len(candidates))].(float64)
		}
		value := anchor + (rng.Float64()*2-1)*math.Max(1, math.Min(math.Abs(anchor), 1e9))
		if math.IsInf(value, 0) || math.IsNaN(value) {
			return nil, fmt.Errorf("property sample exceeds the finite numeric profile for %s", field.name)
		}
		return value, nil
	case "string":
		const alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 _%\\\n-"
		b := make([]byte, rng.IntN(17))
		for i := range b {
			b[i] = alphabet[rng.IntN(len(alphabet))]
		}
		return string(b), nil
	}
	return nil, fmt.Errorf("unsupported property field type %s", field.kind)
}
