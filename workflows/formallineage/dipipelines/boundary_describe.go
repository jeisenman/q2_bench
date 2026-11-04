package dipipelines

import (
	"encoding/json"
	"fmt"
	"strings"

	sitter "github.com/tree-sitter/go-tree-sitter"
)

func describeBoundary(n *sitter.Node, source []byte, kind string) []string {
	if kind == "comparison" {
		parts := children(n)
		if len(parts) != 2 {
			return []string{"Exercise every comparison in the chain independently, including equality and null operands; resolve Python versus Spark evaluation before running."}
		}
		operator := strings.TrimSpace(string(source[parts[0].EndByte():parts[1].StartByte()]))
		messages := []string{fmt.Sprintf("Exercise both outcomes of `%s` and null/unknown operands; preserve the source operator `%s`.", n.Utf8Text(source), operator)}
		for _, operand := range parts {
			c := compiler{source: source, names: map[string]Kind{}}
			value, err := c.lower(operand)
			if err != nil {
				continue
			}
			literal, ok := expressionLiteral(value)
			if !ok {
				continue
			}
			if primitive, candidates := domainAround(literal); primitive != "" {
				encoded, _ := json.Marshal(candidates)
				messages = append(messages, fmt.Sprintf("For literal %s use %s candidates %s plus null. Numeric candidates include adjacent representable values as well as ±1; verify the actual field's type and unit before binding.", operand.Utf8Text(source), primitive, encoded))
			}
		}
		if len(messages) == 1 {
			messages = append(messages, "The boundary depends on another field, parameter, or derived expression: bind that value and test equality, one unit before/after, and null on each side independently.")
		}
		return messages
	}
	if n.Kind() == "call" {
		args := n.ChildByFieldName("arguments").Utf8Text(source)
		switch kind {
		case "filter":
			return []string{"For predicate " + args + ", make each atomic condition decide the result independently; cover the full Boolean truth table where bounded, with true, false, and null. Keep preceding pipeline filters satisfied so these rows reach this clause."}
		case "join":
			return []string{"For join arguments " + args + ", test exact matches, each missing side, null keys, one mismatched composite-key component, 1:many and many:many matches, both empty sides, and conflicting non-key columns. Verify the actual declared mode; dynamic key/mode expressions remain unresolved."}
		case "drop":
			return []string{"For drop arguments " + args + ", distinguish Spark column drop from Pandas row/index drop using the actual receiver type. Include present and absent labels, duplicates, null values, and unrelated fields; verify rows and exact schema."}
		case "dropna":
			return []string{"For dropna arguments " + args + ", test every combination of nulls in the declared subset, all fields present, blank strings, zero, and empty input. Check `how`, `thresh`, and subset semantics; null and NaN need separate profiles."}
		}
	}
	switch kind {
	case "branch", "control":
		return []string{"Reach each true/false/exception/exit path independently, hold earlier guards valid, and check both emitted outputs and intentional skips. Loops require empty, singleton, and repeated iterations."}
	case "window_or_cast":
		return []string{"Test exact ordering/window/cast boundaries, nulls, malformed values, equal sort keys, a separate partition, and empty input. Verify timezone, rank/row_number tie policy, inclusive endpoints, and ANSI mode from the source context."}
	case "unclassified_call":
		return []string{"Resolve this call's implementation, receiver type, inputs, side effects, and return contract before creating an expected result. Its mere presence in a scenario is not executed coverage."}
	default:
		return []string{"Bind this exact source operation to its documented scenario procedures, using declared field types and inputs. Retain unsupported paths as blocked checks until concrete fixtures and an independent expected result exist."}
	}
}
