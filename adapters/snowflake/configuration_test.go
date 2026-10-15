package snowflake

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/jeisenman/q2_bench/domain"
	"github.com/snowflakedb/gosnowflake"
)

func writeAirflowConnection(t *testing.T, privateKey string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "snowflake.json")
	payload := map[string]any{
		"login":    "airflow-user",
		"password": "",
		"extra": map[string]string{
			"account":             "airflow-account",
			"private_key_content": privateKey,
		},
	}
	content, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, content, 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}

func testPrivateKeyPEM(t *testing.T) string {
	t.Helper()
	privateKey, err := rsa.GenerateKey(rand.Reader, 1024)
	if err != nil {
		t.Fatal(err)
	}
	encoded, err := x509.MarshalPKCS8PrivateKey(privateKey)
	if err != nil {
		t.Fatal(err)
	}
	return string(pem.EncodeToMemory(&pem.Block{
		Type: "PRIVATE KEY", Bytes: encoded,
	}))
}

func configureEnvironment(t *testing.T, environment domain.Environment) {
	t.Helper()
	for _, suffix := range requiredSettingSuffixes {
		t.Setenv(VariableName(environment, suffix), strings.ToLower(suffix)+"-value")
	}
}

func TestLoadSettingsUsesEnvironmentScopedValues(t *testing.T) {
	configureEnvironment(t, domain.EnvironmentDev)
	settings, err := LoadSettings(domain.EnvironmentDev)
	if err != nil {
		t.Fatal(err)
	}
	if settings.Account != "account-value" {
		t.Fatalf("account = %q", settings.Account)
	}
	if settings.SecretRef != "snowflake/dev/password" {
		t.Fatalf("secret ref = %q", settings.SecretRef)
	}
}

func TestLoadSettingsNamesEveryMissingValue(t *testing.T) {
	for _, suffix := range requiredSettingSuffixes {
		t.Setenv(VariableName(domain.EnvironmentStage, suffix), "")
	}
	_, err := LoadSettings(domain.EnvironmentStage)
	if err == nil {
		t.Fatal("expected missing settings error")
	}
	for _, suffix := range requiredSettingSuffixes {
		if !strings.Contains(err.Error(), VariableName(domain.EnvironmentStage, suffix)) {
			t.Fatalf("error does not name %s: %v", suffix, err)
		}
	}
}

func TestOAuthUsesCallTimeToken(t *testing.T) {
	configureEnvironment(t, domain.EnvironmentProd)
	t.Setenv(VariableName(domain.EnvironmentProd, "AUTHENTICATOR"), "oauth")
	settings, err := LoadSettings(domain.EnvironmentProd)
	if err != nil {
		t.Fatal(err)
	}
	if settings.SecretRef != "snowflake/prod/token" {
		t.Fatalf("secret ref = %q", settings.SecretRef)
	}
	config, err := settings.DriverConfig("token-value")
	if err != nil {
		t.Fatal(err)
	}
	if config.Authenticator != gosnowflake.AuthTypeOAuth || config.Token != "token-value" {
		t.Fatalf("driver config = %#v", config)
	}
}

func TestLoadSettingsUsesAirflowConnectionIdentity(t *testing.T) {
	connectionFile := writeAirflowConnection(t, testPrivateKeyPEM(t))
	t.Setenv(
		VariableName(domain.EnvironmentDev, "CONNECTION_FILE"),
		connectionFile,
	)
	for _, suffix := range requiredSettingSuffixes {
		t.Setenv(VariableName(domain.EnvironmentDev, suffix), "")
	}
	t.Setenv(VariableName(domain.EnvironmentDev, "AUTHENTICATOR"), "")
	settings, err := LoadSettings(domain.EnvironmentDev)
	if err != nil {
		t.Fatal(err)
	}
	if settings.Account != "airflow-account" || settings.User != "airflow-user" {
		t.Fatalf("settings = %#v", settings)
	}
	if settings.Authenticator != jwtAuthenticator {
		t.Fatalf("authenticator = %q", settings.Authenticator)
	}
	if settings.SecretRef != airflowConnectionSecretPrefix+connectionFile {
		t.Fatalf("secret ref = %q", settings.SecretRef)
	}
}

func TestJWTUsesAirflowPrivateKey(t *testing.T) {
	privateKey := testPrivateKeyPEM(t)
	settings := Settings{
		Environment: domain.EnvironmentDev, Account: "account", User: "user",
		Authenticator: jwtAuthenticator, SecretRef: "private-key",
	}
	config, err := settings.DriverConfig(privateKey)
	if err != nil {
		t.Fatal(err)
	}
	if config.Authenticator != gosnowflake.AuthTypeJwt || config.PrivateKey == nil {
		t.Fatalf("driver config = %#v", config)
	}
	if _, err := NewCortex(settings, EnvironmentSecrets{}); err != nil {
		t.Fatalf("JWT settings should use Snowflake defaults: %v", err)
	}
}

func TestEnvironmentSecretsReadsAirflowPrivateKey(t *testing.T) {
	privateKey := testPrivateKeyPEM(t)
	connectionFile := writeAirflowConnection(t, privateKey)
	secret, err := (EnvironmentSecrets{}).GetSecret(
		context.Background(),
		airflowConnectionSecretPrefix+connectionFile,
	)
	if err != nil {
		t.Fatal(err)
	}
	if secret != strings.TrimSpace(privateKey) {
		t.Fatal("private key content did not round trip")
	}
}

func TestContainerRejectsInteractiveAuthenticator(t *testing.T) {
	configureEnvironment(t, domain.EnvironmentDev)
	t.Setenv(VariableName(domain.EnvironmentDev, "AUTHENTICATOR"), "externalbrowser")
	_, err := LoadSettings(domain.EnvironmentDev)
	if err == nil || !strings.Contains(err.Error(), "containerized") {
		t.Fatalf("err = %v", err)
	}
}

func TestEnvironmentSecretsNamesMissingVariable(t *testing.T) {
	t.Setenv("SNOWFLAKE_DEV_PASSWORD", "")
	_, err := (EnvironmentSecrets{}).GetSecret(
		context.Background(),
		"snowflake/dev/password",
	)
	if err == nil || !strings.Contains(err.Error(), "SNOWFLAKE_DEV_PASSWORD") {
		t.Fatalf("err = %v", err)
	}
}
