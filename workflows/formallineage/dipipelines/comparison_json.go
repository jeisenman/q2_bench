package dipipelines

import "bytes"

// floatJSON preserves the sign of zero when CPython decodes JSON numbers.
// encoding/json emits -0 for a negative float64 zero; CPython treats that
// spelling as integer zero. -0.0 retains its IEEE-754 sign without rounding.
func floatJSON(content []byte) []byte {
	var out bytes.Buffer
	inString, escaped := false, false
	for i := 0; i < len(content); i++ {
		c := content[i]
		if inString {
			out.WriteByte(c)
			if escaped {
				escaped = false
			} else if c == '\\' {
				escaped = true
			} else if c == '"' {
				inString = false
			}
			continue
		}
		if c == '"' {
			inString = true
			out.WriteByte(c)
			continue
		}
		if c == '-' && i+1 < len(content) && content[i+1] == '0' && (i+2 == len(content) || jsonDelimiter(content[i+2])) {
			out.WriteString("-0.0")
			i++
			continue
		}
		out.WriteByte(c)
	}
	return out.Bytes()
}

func jsonDelimiter(c byte) bool {
	return c == ',' || c == ']' || c == '}' || c == ' ' || c == '\n' || c == '\r' || c == '\t'
}
