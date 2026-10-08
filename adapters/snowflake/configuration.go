// Package snowflake implements live and recorded Snowflake Cortex adapters.
package snowflake

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/jeisenman/q2_bench/domain"
	"github.com/jeisenman/q2_bench/ports"
	"github.com/snowflakedb/gosnowflake"
)

const (
	defaultAuthenticator = "snowflake"
	defaultLoginTimeout  = 30 * time.Second
)

var requiredSettingSuffixes = []string{
	"ACCOUNT",
	"USER",
	"ROLE",
	"WAREHOUSE",
	"DATABASE",
	"SCHEMA",
}

// Settings contains non-secret connection settings for one Snowflake environment.
type Settings struct {
	Environment   domain.Environment
	Account       string
	User          string
	Role          string
	Warehouse     string
	Database      string
	Schema        string
	Authenticator string
	SecretRef     string
}

// VariableName returns one environment-scoped Snowflake variable name.
func VariableName(environment domain.Environment, suffix string) string {
	return "SNOWFLAKE_" + strings.ToUpper(string(environment)) + "_" + suffix
}

// LoadSettings reads non-secret Snowflake settings and names every missing value.
func LoadSettings(environment domain.Environment) (Settings, error) {
	if environment == domain.EnvironmentSandbox {
		return Settings{}, fmt.Errorf(
			"the sandbox environment replays Cortex recordings and has no Snowflake connection",
		)
	}
	values := make(map[string]string, len(requiredSettingSuffixes))
	missing := make([]string, 0)
	for _, suffix := range requiredSettingSuffixes {
		name := VariableName(environment, suffix)
		value := strings.TrimSpace(os.Getenv(name))
		if value == "" {
			missing = append(missing, name)
		}
		values[suffix] = value
	}
	if len(missing) > 0 {
		return Settings{}, fmt.Errorf(
			"Snowflake %s configuration is incomplete; set: %s",
			environment,
			strings.Join(missing, ", "),
		)
	}
	authenticator := strings.ToLower(strings.TrimSpace(
		os.Getenv(VariableName(environment, "AUTHENTICATOR")),
	))
	if authenticator == "" {
		authenticator = defaultAuthenticator
	}
	if authenticator != "snowflake" && authenticator != "oauth" && authenticator != "pat" {
		return Settings{}, fmt.Errorf(
			"unsupported Snowflake authenticator %q; containerized warehouse-mcp supports snowflake, oauth, or pat",
			authenticator,
		)
	}
	secretRef := strings.TrimSpace(os.Getenv(VariableName(environment, "SECRET_REF")))
	if secretRef == "" {
		secretRef = fmt.Sprintf("snowflake/%s/%s", environment, secretKind(authenticator))
	}
	return Settings{
		Environment: environment, Account: values["ACCOUNT"], User: values["USER"],
		Role: values["ROLE"], Warehouse: values["WAREHOUSE"], Database: values["DATABASE"],
		Schema: values["SCHEMA"], Authenticator: authenticator, SecretRef: secretRef,
	}, nil
}

// DriverConfig builds a Snowflake driver configuration with a call-time secret.
func (s Settings) DriverConfig(secret string) (gosnowflake.Config, error) {
	if strings.TrimSpace(secret) == "" {
		return gosnowflake.Config{}, fmt.Errorf(
			"Snowflake %s %s must not be empty",
			s.Environment,
			secretKind(s.Authenticator),
		)
	}
	config := gosnowflake.Config{
		Account: s.Account, User: s.User, Role: s.Role, Warehouse: s.Warehouse,
		Database: s.Database, Schema: s.Schema, LoginTimeout: defaultLoginTimeout,
		RequestTimeout: defaultLoginTimeout, ClientTimeout: defaultLoginTimeout,
		MaxRetryCount: 2, Application: "q2-warehouse-mcp", DisableTelemetry: true,
		LogQueryText: false, LogQueryParameters: false,
	}
	switch s.Authenticator {
	case "snowflake":
		config.Authenticator = gosnowflake.AuthTypeSnowflake
		config.Password = secret
	case "oauth":
		config.Authenticator = gosnowflake.AuthTypeOAuth
		config.Token = secret
	case "pat":
		config.Authenticator = gosnowflake.AuthTypePat
		config.Token = secret
	default:
		return gosnowflake.Config{}, fmt.Errorf(
			"unsupported Snowflake authenticator %q",
			s.Authenticator,
		)
	}
	return config, nil
}

// EnvironmentSecrets resolves slash-delimited secret references from environment variables.
type EnvironmentSecrets struct{}

// GetSecret returns a secret without retaining it on a settings value.
func (EnvironmentSecrets) GetSecret(_ context.Context, name string) (string, error) {
	variable := strings.NewReplacer("/", "_", "-", "_").Replace(strings.ToUpper(name))
	value := strings.TrimSpace(os.Getenv(variable))
	if value == "" {
		return "", fmt.Errorf("secret %q is not set; export %s", name, variable)
	}
	return value, nil
}

func secretKind(authenticator string) string {
	if authenticator == "snowflake" {
		return "password"
	}
	return "token"
}

func validateSettings(settings Settings) error {
	if settings.Environment == domain.EnvironmentSandbox {
		return fmt.Errorf("Snowflake Cortex cannot use the sandbox environment")
	}
	for name, value := range map[string]string{
		"account": settings.Account, "user": settings.User, "role": settings.Role,
		"warehouse": settings.Warehouse, "database": settings.Database,
		"schema": settings.Schema, "secret_ref": settings.SecretRef,
	} {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("Snowflake %s must not be empty", name)
		}
	}
	if settings.Authenticator == "" {
		return fmt.Errorf("Snowflake authenticator must not be empty")
	}
	return nil
}

var _ ports.SecretProvider = EnvironmentSecrets{}
