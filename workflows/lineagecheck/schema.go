package lineagecheck

import (
	"fmt"
	"strconv"
	"strings"
	"unicode"
)

type pyToken struct {
	value    string
	literal  bool
	row, col int
}

// ExtractSchema reads literal primitive StructType schemas without running Python.
// Computed, inherited, nested, or mutated schemas require an explicit reviewed contract.
func ExtractSchema(content []byte, class string, major int) ([]Field, error) {
	if len(content) > maxDocumentBytes {
		return nil, fmt.Errorf("schema source exceeds %d bytes", maxDocumentBytes)
	}
	tokens, err := pythonTokens(string(content))
	if err != nil {
		return nil, err
	}
	start, end := -1, len(tokens)
	for i := 0; i+1 < len(tokens); i++ {
		if tokens[i].value == "class" && tokens[i+1].value == class && !tokens[i].literal {
			if start >= 0 {
				return nil, fmt.Errorf("duplicate schema class %s", class)
			}
			start = i
		}
	}
	if start < 0 {
		return nil, fmt.Errorf("schema class %s not found", class)
	}
	for i := start + 2; i < len(tokens); i++ {
		if tokens[i].row > tokens[start].row && tokens[i].col <= tokens[start].col {
			end = i
			break
		}
	}
	method := fmt.Sprintf("_schema_v%d", major)
	body := []pyToken(nil)
	for i := start; i+1 < end; i++ {
		if tokens[i].value != "def" || tokens[i+1].value != method {
			continue
		}
		if body != nil {
			return nil, fmt.Errorf("duplicate schema method %s", method)
		}
		j := i + 2
		for j < end && tokens[j].value != ":" {
			j++
		}
		k := j + 1
		for k < end && !(tokens[k].row > tokens[i].row && tokens[k].col <= tokens[i].col) {
			k++
		}
		if j < end {
			body = tokens[j+1 : k]
		}
	}
	fail := func() ([]Field, error) {
		return nil, fmt.Errorf("%s.%s must be a literal primitive StructType; use reviewed explicit fields for computed schemas", class, method)
	}
	if len(body) == 0 {
		return fail()
	}
	values := func(ts []pyToken) string {
		a := make([]string, len(ts))
		for i, t := range ts {
			a[i] = t.value
		}
		return strings.Join(a, " ")
	}
	prefix, suffix := 0, 0
	if len(body) > 3 && values(body[:3]) == "_schema = StructType" {
		prefix = 3
		suffix = 2
		if len(body) < 5 || values(body[len(body)-2:]) != "return _schema" {
			return fail()
		}
	} else if len(body) > 2 && values(body[:2]) == "return StructType" {
		prefix = 2
	} else {
		return fail()
	}
	b := body[prefix : len(body)-suffix]
	if len(b) < 4 || values(b[:2]) != "( [" || values(b[len(b)-2:]) != "] )" {
		return fail()
	}
	b = b[2 : len(b)-2]
	fields := []Field{}
	for len(b) > 0 {
		// StructField('name', PrimitiveType(), True),
		if len(b) < 10 || b[0].value != "StructField" || b[1].value != "(" || !b[2].literal || b[3].value != "," || !contains([]string{"StringType", "BooleanType", "DoubleType", "FloatType", "LongType", "IntegerType", "ShortType", "ByteType", "TimestampType", "DateType", "BinaryType"}, b[4].value) || values(b[5:8]) != "( ) ," || !contains([]string{"True", "False"}, b[8].value) || b[9].value != ")" {
			return fail()
		}
		fields = append(fields, Field{Name: b[2].value, Type: b[4].value, Nullable: b[8].value == "True"})
		b = b[10:]
		if len(b) > 0 {
			if b[0].value != "," {
				return fail()
			}
			b = b[1:]
		}
	}
	if len(fields) == 0 {
		return fail()
	}
	return fields, nil
}

// pythonTokens is a bounded lexer for the deliberately restricted schema reader.
func pythonTokens(s string) ([]pyToken, error) {
	tokens := []pyToken{}
	row, col := 1, 0
	for i := 0; i < len(s); {
		c := s[i]
		if c == '\n' {
			row++
			col = 0
			i++
			continue
		}
		if c == ' ' || c == '\r' {
			col++
			i++
			continue
		}
		if c == '\t' {
			return nil, fmt.Errorf("schema source uses tabs at line %d; explicit fields required", row)
		}
		if c == '#' {
			for i < len(s) && s[i] != '\n' {
				i++
				col++
			}
			continue
		}
		t := pyToken{row: row, col: col}
		if c == '\'' || c == '"' {
			quote := c
			triple := i+2 < len(s) && s[i+1] == c && s[i+2] == c
			width := 1
			if triple {
				width = 3
			}
			i += width
			col += width
			var value strings.Builder
			closed := false
			for i < len(s) {
				if s[i] == quote && (!triple || i+2 < len(s) && s[i+1] == quote && s[i+2] == quote) {
					i += width
					col += width
					closed = true
					break
				}
				if s[i] == '\\' {
					if i+1 >= len(s) {
						break
					}
					switch s[i+1] {
					case '\\', '\'', '"':
						value.WriteByte(s[i+1])
					default:
						value.WriteByte('\\')
						value.WriteByte(s[i+1])
					}
					i += 2
					col += 2
					continue
				}
				if s[i] == '\n' {
					if !triple {
						return nil, fmt.Errorf("unterminated schema string at line %d", row)
					}
					row++
					col = 0
				} else {
					col++
				}
				value.WriteByte(s[i])
				i++
			}
			if !closed {
				return nil, fmt.Errorf("unterminated schema string at line %d", t.row)
			}
			t.value = value.String()
			t.literal = true
		} else if unicode.IsLetter(rune(c)) || c == '_' || c >= '0' && c <= '9' {
			start := i
			for i < len(s) && (unicode.IsLetter(rune(s[i])) || s[i] == '_' || s[i] >= '0' && s[i] <= '9') {
				i++
				col++
			}
			t.value = s[start:i]
		} else {
			t.value = string(c)
			i++
			col++
		}
		tokens = append(tokens, t)
		if len(tokens) > 1000000 {
			return nil, fmt.Errorf("schema token limit exceeded: %s", strconv.Itoa(len(tokens)))
		}
	}
	return tokens, nil
}
