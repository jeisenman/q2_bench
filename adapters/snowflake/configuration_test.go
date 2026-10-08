package snowflake

import (
	"context"
	"strings"
	"testing"

	"github.com/jeisenman/q2_bench/domain"
	"github.com/snowflakedb/gosnowflake"
)

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
