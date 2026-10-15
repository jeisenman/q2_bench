// Package snowflake implements live and recorded Snowflake Cortex adapters.
package snowflake

import (
	"context"
	"crypto/rsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/jeisenman/q2_bench/domain"
	"github.com/jeisenman/q2_bench/ports"
	"github.com/snowflakedb/gosnowflake"
)

const (
	airflowConnectionSecretPrefix = "airflow-connection:"
	defaultAuthenticator          = "snowflake"
	jwtAuthenticator              = "snowflake_jwt"
	defaultLoginTimeout           = 30 * time.Second
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

type airflowConnectionIdentity struct {
	Login string `json:"login"`
	Extra struct {
		Account string `json:"account"`
	} `json:"extra"`
}

type airflowConnectionCredential struct {
	Extra struct {
		PrivateKeyContent string `json:"private_key_content"`
	} `json:"extra"`
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
	for _, suffix := range requiredSettingSuffixes {
		values[suffix] = strings.TrimSpace(os.Getenv(VariableName(environment, suffix)))
	}
	connectionFile := strings.TrimSpace(
		os.Getenv(VariableName(environment, "CONNECTION_FILE")),
	)
	if connectionFile != "" {
		identity, err := loadAirflowConnectionIdentity(connectionFile)
		if err != nil {
			return Settings{}, err
		}
		if values["ACCOUNT"] == "" {
			values["ACCOUNT"] = identity.Extra.Account
		}
		if values["USER"] == "" {
			values["USER"] = identity.Login
		}
	}
	required := requiredSettingSuffixes
	if connectionFile != "" {
		required = []string{"ACCOUNT", "USER"}
	}
	missing := make([]string, 0)
	for _, suffix := range required {
		if values[suffix] == "" {
			missing = append(missing, VariableName(environment, suffix))
		}
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
		if connectionFile != "" {
			authenticator = jwtAuthenticator
		}
	}
	if authenticator != "snowflake" && authenticator != "oauth" &&
		authenticator != "pat" && authenticator != jwtAuthenticator {
		return Settings{}, fmt.Errorf(
			"unsupported Snowflake authenticator %q; containerized warehouse-mcp supports snowflake, oauth, pat, or snowflake_jwt",
			authenticator,
		)
	}
	secretRef := strings.TrimSpace(os.Getenv(VariableName(environment, "SECRET_REF")))
	if secretRef == "" {
		if connectionFile != "" && authenticator == jwtAuthenticator {
			secretRef = airflowConnectionSecretPrefix + connectionFile
		} else {
			secretRef = fmt.Sprintf(
				"snowflake/%s/%s",
				environment,
				secretKind(authenticator),
			)
		}
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
	case jwtAuthenticator:
		privateKey, err := parsePrivateKey(secret)
		if err != nil {
			return gosnowflake.Config{}, err
		}
		config.Authenticator = gosnowflake.AuthTypeJwt
		config.PrivateKey = privateKey
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
	if strings.HasPrefix(name, airflowConnectionSecretPrefix) {
		return loadAirflowConnectionPrivateKey(
			strings.TrimPrefix(name, airflowConnectionSecretPrefix),
		)
	}
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
	if authenticator == jwtAuthenticator {
		return "private_key"
	}
	return "token"
}

func loadAirflowConnectionIdentity(path string) (airflowConnectionIdentity, error) {
	var identity airflowConnectionIdentity
	if err := readAirflowConnection(path, &identity); err != nil {
		return airflowConnectionIdentity{}, err
	}
	if strings.TrimSpace(identity.Login) == "" {
		return airflowConnectionIdentity{}, fmt.Errorf(
			"%s: Snowflake login must not be empty",
			path,
		)
	}
	if strings.TrimSpace(identity.Extra.Account) == "" {
		return airflowConnectionIdentity{}, fmt.Errorf(
			"%s: Snowflake extra.account must not be empty",
			path,
		)
	}
	return identity, nil
}

func loadAirflowConnectionPrivateKey(path string) (string, error) {
	var credential airflowConnectionCredential
	if err := readAirflowConnection(path, &credential); err != nil {
		return "", err
	}
	privateKey := strings.TrimSpace(credential.Extra.PrivateKeyContent)
	if privateKey == "" {
		return "", fmt.Errorf(
			"%s: Snowflake extra.private_key_content must not be empty",
			path,
		)
	}
	return privateKey, nil
}

func readAirflowConnection(path string, target any) error {
	if !filepath.IsAbs(path) {
		return fmt.Errorf("Snowflake connection file must be absolute; got %q", path)
	}
	content, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("read Snowflake connection file %q: %w", path, err)
	}
	if err := json.Unmarshal(content, target); err != nil {
		return fmt.Errorf("decode Snowflake connection file %q: %w", path, err)
	}
	return nil
}

func parsePrivateKey(value string) (*rsa.PrivateKey, error) {
	block, _ := pem.Decode([]byte(value))
	if block == nil {
		return nil, fmt.Errorf("Snowflake private key must be PEM encoded")
	}
	switch block.Type {
	case "PRIVATE KEY":
		parsed, err := x509.ParsePKCS8PrivateKey(block.Bytes)
		if err != nil {
			return nil, fmt.Errorf("parse Snowflake PKCS#8 private key: %w", err)
		}
		privateKey, ok := parsed.(*rsa.PrivateKey)
		if !ok {
			return nil, fmt.Errorf("Snowflake private key must be RSA")
		}
		return privateKey, nil
	case "RSA PRIVATE KEY":
		privateKey, err := x509.ParsePKCS1PrivateKey(block.Bytes)
		if err != nil {
			return nil, fmt.Errorf("parse Snowflake PKCS#1 private key: %w", err)
		}
		return privateKey, nil
	default:
		return nil, fmt.Errorf(
			"unsupported Snowflake private key PEM block %q",
			block.Type,
		)
	}
}

func validateSettings(settings Settings) error {
	if settings.Environment == domain.EnvironmentSandbox {
		return fmt.Errorf("Snowflake Cortex cannot use the sandbox environment")
	}
	for name, value := range map[string]string{
		"account": settings.Account, "user": settings.User,
		"secret_ref": settings.SecretRef,
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
