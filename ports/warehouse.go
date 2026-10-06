package ports

import (
	"context"
	"fmt"
	"strconv"
	"strings"

	"github.com/jeisenman/q2_bench/domain"
)

// SQLValue is a provider-neutral scalar returned by warehouse adapters.
type SQLValue any

// Row is one ordered warehouse result row.
type Row []SQLValue

// Column is one result column and its backend-reported type.
type Column struct {
	Name     string
	TypeName string
}

// SQLStatement is a parameterized read-only statement.
type SQLStatement struct {
	Text       string
	Parameters map[string]SQLValue
}

// Validate rejects empty and non-portable SQL.
func (s SQLStatement) Validate() error {
	if strings.TrimSpace(s.Text) == "" {
		return fmt.Errorf("statement text must not be empty")
	}
	return domain.RequirePortable(s.Text)
}

// QueryResult contains rows in a stable backend-independent shape.
type QueryResult struct {
	Columns     []Column
	Rows        []Row
	Environment domain.Environment
}

// ColumnNames returns column names in result order.
func (r QueryResult) ColumnNames() []string {
	names := make([]string, len(r.Columns))
	for index, column := range r.Columns {
		names[index] = column.Name
	}
	return names
}

// AsMaps returns result rows keyed by column name.
func (r QueryResult) AsMaps() ([]map[string]SQLValue, error) {
	names := r.ColumnNames()
	records := make([]map[string]SQLValue, len(r.Rows))
	for rowIndex, row := range r.Rows {
		if len(row) != len(names) {
			return nil, fmt.Errorf(
				"row %d contains %d values for %d columns",
				rowIndex,
				len(row),
				len(names),
			)
		}
		record := make(map[string]SQLValue, len(names))
		for columnIndex, name := range names {
			record[name] = row[columnIndex]
		}
		records[rowIndex] = record
	}
	return records, nil
}

// CoerceValue narrows common driver values to stable cross-backend values.
func CoerceValue(value any) SQLValue {
	switch typed := value.(type) {
	case nil, string, int, int64, float64, bool:
		return typed
	case fmt.Stringer:
		return typed.String()
	case float32:
		return strconv.FormatFloat(float64(typed), 'f', -1, 32)
	default:
		return fmt.Sprint(value)
	}
}

// Warehouse reads and describes one resolved analytics environment.
type Warehouse interface {
	Environment() domain.Environment
	Fetch(context.Context, SQLStatement) (QueryResult, error)
	Tables(context.Context, string) ([]string, error)
	Columns(context.Context, string, string) ([]Column, error)
}
