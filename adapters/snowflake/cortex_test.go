package snowflake

import (
	"context"
	"database/sql"
	"errors"
	"strings"
	"testing"

	"github.com/jeisenman/q2_bench/domain"
	"github.com/jeisenman/q2_bench/ports"
)

type fakeSecrets struct {
	name string
}

func (f *fakeSecrets) GetSecret(context.Context, string) (string, error) {
	f.name = "requested"
	return "secret", nil
}

type fakeDatabase struct {
	statement string
	arguments []any
	value     any
	err       error
	closed    bool
}

func (f *fakeDatabase) QueryRowContext(
	_ context.Context,
	statement string,
	arguments ...any,
) rowScanner {
	f.statement = statement
	f.arguments = arguments
	return fakeRow{value: f.value, err: f.err}
}

func (f *fakeDatabase) Close() error {
	f.closed = true
	return nil
}

type fakeRow struct {
	value any
	err   error
}

func (f fakeRow) Scan(destinations ...any) error {
	if f.err != nil {
		return f.err
	}
	switch target := destinations[0].(type) {
	case *sql.NullString:
		target.Valid = f.value != nil
		if target.Valid {
			target.String = f.value.(string)
		}
	case *int:
		*target = f.value.(int)
	default:
		return errors.New("unsupported scan destination")
	}
	return nil
}

func cortexSettings() Settings {
	return Settings{
		Environment: domain.EnvironmentDev, Account: "account", User: "user",
		Role: "role", Warehouse: "warehouse", Database: "database", Schema: "schema",
		Authenticator: "snowflake", SecretRef: "snowflake/dev/password",
	}
}

func TestCortexCompleteBindsInputsAndClosesConnection(t *testing.T) {
	fakeDB := &fakeDatabase{value: "answer"}
	secrets := &fakeSecrets{}
	cortex, err := NewCortex(cortexSettings(), secrets)
	if err != nil {
		t.Fatal(err)
	}
	cortex.open = func(Settings, string) (database, error) {
		return fakeDB, nil
	}
	response, err := cortex.Complete(
		context.Background(),
		ports.CortexRequest{Model: "model", Prompt: "prompt"},
	)
	if err != nil {
		t.Fatal(err)
	}
	if response.Text != "answer" || response.Recorded {
		t.Fatalf("response = %#v", response)
	}
	if fakeDB.statement != completeSQL {
		t.Fatalf("statement = %q", fakeDB.statement)
	}
	if len(fakeDB.arguments) != 2 || fakeDB.arguments[0] != "model" {
		t.Fatalf("arguments = %#v", fakeDB.arguments)
	}
	if !fakeDB.closed || secrets.name == "" {
		t.Fatalf("closed = %v, secret lookup = %q", fakeDB.closed, secrets.name)
	}
}

func TestCortexTemperatureUsesBoundOptions(t *testing.T) {
	fakeDB := &fakeDatabase{value: "answer"}
	cortex, err := NewCortex(cortexSettings(), &fakeSecrets{})
	if err != nil {
		t.Fatal(err)
	}
	cortex.open = func(Settings, string) (database, error) {
		return fakeDB, nil
	}
	_, err = cortex.Complete(
		context.Background(),
		ports.CortexRequest{Model: "model", Prompt: "prompt", Temperature: 0.5},
	)
	if err != nil {
		t.Fatal(err)
	}
	if fakeDB.statement != completeWithOptionsSQL || fakeDB.arguments[2] != 0.5 {
		t.Fatalf("query = %q %#v", fakeDB.statement, fakeDB.arguments)
	}
}

func TestCortexWrapsProviderFailureWithEnvironment(t *testing.T) {
	fakeDB := &fakeDatabase{err: errors.New("network down")}
	cortex, err := NewCortex(cortexSettings(), &fakeSecrets{})
	if err != nil {
		t.Fatal(err)
	}
	cortex.open = func(Settings, string) (database, error) {
		return fakeDB, nil
	}
	_, err = cortex.Complete(
		context.Background(),
		ports.CortexRequest{Model: "model", Prompt: "prompt"},
	)
	if err == nil || !strings.Contains(err.Error(), "Cortex dev completion failed") {
		t.Fatalf("err = %v", err)
	}
}

func TestCortexCountsTokens(t *testing.T) {
	fakeDB := &fakeDatabase{value: 3}
	cortex, err := NewCortex(cortexSettings(), &fakeSecrets{})
	if err != nil {
		t.Fatal(err)
	}
	cortex.open = func(Settings, string) (database, error) {
		return fakeDB, nil
	}
	count, err := cortex.CountTokens(context.Background(), "model", "prompt")
	if err != nil {
		t.Fatal(err)
	}
	if count != 3 || fakeDB.statement != countTokensSQL {
		t.Fatalf("count = %d, statement = %q", count, fakeDB.statement)
	}
}
