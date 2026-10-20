package snowflake

import (
	"context"
	"database/sql"
	"fmt"

	"github.com/jeisenman/q2_bench/domain"
	"github.com/jeisenman/q2_bench/ports"
	"github.com/snowflakedb/gosnowflake"
)

const (
	completeSQL            = "SELECT AI_COMPLETE(?, ?) AS completion"
	completeWithOptionsSQL = "SELECT AI_COMPLETE(?, ?, OBJECT_CONSTRUCT('temperature', ?)) AS completion"
	countTokensSQL         = "SELECT SNOWFLAKE.CORTEX.COUNT_TOKENS(?, ?) AS token_count"
)

type rowScanner interface {
	Scan(...any) error
}

type database interface {
	QueryRowContext(context.Context, string, ...any) rowScanner
	Close() error
}

type databaseOpener func(Settings, string) (database, error)

// Cortex runs bounded model inference through Snowflake Cortex.
type Cortex struct {
	settings Settings
	secrets  ports.SecretProvider
	open     databaseOpener
}

// NewCortex constructs a live Cortex adapter with call-time secret resolution.
func NewCortex(settings Settings, secrets ports.SecretProvider) (*Cortex, error) {
	if err := validateSettings(settings); err != nil {
		return nil, err
	}
	if secrets == nil {
		return nil, fmt.Errorf("Snowflake Cortex requires a secret provider")
	}
	return &Cortex{settings: settings, secrets: secrets, open: openDatabase}, nil
}

// Environment returns the Snowflake environment served by this adapter.
func (c *Cortex) Environment() domain.Environment {
	return c.settings.Environment
}

// Complete returns one live Cortex completion.
func (c *Cortex) Complete(
	ctx context.Context,
	request ports.CortexRequest,
) (ports.CortexResponse, error) {
	if err := request.Validate(); err != nil {
		return ports.CortexResponse{}, err
	}
	var completion sql.NullString
	statement := completeSQL
	arguments := []any{request.Model, request.Prompt}
	if request.Temperature != 0 {
		statement = completeWithOptionsSQL
		arguments = append(arguments, request.Temperature)
	}
	if err := c.queryRow(ctx, statement, arguments...).Scan(&completion); err != nil {
		return ports.CortexResponse{}, fmt.Errorf(
			"Cortex %s completion failed: %w",
			c.Environment(),
			err,
		)
	}
	if !completion.Valid || completion.String == "" {
		return ports.CortexResponse{}, fmt.Errorf(
			"Cortex returned no completion for model %q",
			request.Model,
		)
	}
	return ports.CortexResponse{
		Text: completion.String, Model: request.Model,
		Environment: c.Environment(), Recorded: false,
	}, nil
}

// CountTokens returns the Snowflake Cortex tokenizer count without inference.
func (c *Cortex) CountTokens(ctx context.Context, model, text string) (int, error) {
	request := ports.CortexRequest{Model: model, Prompt: text}
	if err := request.Validate(); err != nil {
		return 0, err
	}
	var count int
	if err := c.queryRow(ctx, countTokensSQL, model, text).Scan(&count); err != nil {
		return 0, fmt.Errorf(
			"Cortex %s token count failed: %w",
			c.Environment(),
			err,
		)
	}
	if count < 0 {
		return 0, fmt.Errorf("Cortex returned a negative token count: %d", count)
	}
	return count, nil
}

func (c *Cortex) queryRow(
	ctx context.Context,
	statement string,
	arguments ...any,
) rowScanner {
	return queryRow(ctx, c.settings, c.secrets, c.open, statement, arguments...)
}

func queryRow(
	ctx context.Context,
	settings Settings,
	secrets ports.SecretProvider,
	open databaseOpener,
	statement string,
	arguments ...any,
) rowScanner {
	return deferredRow{
		run: func() (rowScanner, error) {
			secret, err := secrets.GetSecret(ctx, settings.SecretRef)
			if err != nil {
				return nil, err
			}
			connection, err := open(settings, secret)
			if err != nil {
				return nil, err
			}
			return &closingRow{
				row:   connection.QueryRowContext(ctx, statement, arguments...),
				close: connection.Close,
			}, nil
		},
	}
}

type deferredRow struct {
	run func() (rowScanner, error)
}

func (r deferredRow) Scan(destinations ...any) error {
	row, err := r.run()
	if err != nil {
		return err
	}
	return row.Scan(destinations...)
}

type closingRow struct {
	row   rowScanner
	close func() error
}

func (r *closingRow) Scan(destinations ...any) error {
	scanErr := r.row.Scan(destinations...)
	closeErr := r.close()
	if scanErr != nil {
		return scanErr
	}
	return closeErr
}

func openDatabase(settings Settings, secret string) (database, error) {
	config, err := settings.DriverConfig(secret)
	if err != nil {
		return nil, err
	}
	dsn, err := gosnowflake.DSN(&config)
	if err != nil {
		return nil, fmt.Errorf("build Snowflake connection configuration: %w", err)
	}
	connection, err := sql.Open("snowflake", dsn)
	if err != nil {
		return nil, fmt.Errorf("open Snowflake connection: %w", err)
	}
	return &sqlDatabase{DB: connection}, nil
}

type sqlDatabase struct {
	*sql.DB
}

func (d *sqlDatabase) QueryRowContext(
	ctx context.Context,
	statement string,
	arguments ...any,
) rowScanner {
	return d.DB.QueryRowContext(ctx, statement, arguments...)
}

var _ ports.CortexInference = (*Cortex)(nil)
