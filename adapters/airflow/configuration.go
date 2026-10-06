package airflow

import (
	"fmt"
	"os"
	"strings"

	"gopkg.in/yaml.v3"
)

// Environment identifies an Airflow deployment in configurations.yaml.
type Environment string

const (
	Alpha   Environment = "alpha"
	Staging Environment = "staging"
	ProdUS  Environment = "produs"
	ProdCA  Environment = "prodca"
)

type configuration struct {
	Workspaces struct {
		DataEngineering struct {
			Airflow map[string]struct {
				HostEnv     string `yaml:"host_env"`
				UserEnv     string `yaml:"user_env"`
				PasswordEnv string `yaml:"password_env"`
			} `yaml:"airflow"`
		} `yaml:"data_engineering"`
	} `yaml:"workspaces"`
}

// LoadConnection resolves one environment from YAML and environment variables.
func LoadConnection(
	path string,
	environment Environment,
	environ map[string]string,
) (Credentials, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return Credentials{}, fmt.Errorf("read Airflow configuration %s: %w", path, err)
	}
	var values configuration
	if err := yaml.Unmarshal(content, &values); err != nil {
		return Credentials{}, fmt.Errorf("parse Airflow configuration %s: %w", path, err)
	}
	entry, exists := values.Workspaces.DataEngineering.Airflow[string(environment)]
	if !exists {
		return Credentials{}, fmt.Errorf(
			"%s: workspaces.data_engineering.airflow.%s must be a mapping; "+
				"copy it from configurations.yaml.example",
			path,
			environment,
		)
	}
	names := map[string]string{
		"host_env": entry.HostEnv, "user_env": entry.UserEnv,
		"password_env": entry.PasswordEnv,
	}
	for key, name := range names {
		if strings.TrimSpace(name) == "" {
			return Credentials{}, fmt.Errorf(
				"%s: workspaces.data_engineering.airflow.%s.%s must be set",
				path,
				environment,
				key,
			)
		}
	}
	if environ == nil {
		environ = currentEnvironment()
	}
	host := strings.TrimSpace(environ[entry.HostEnv])
	username := strings.TrimSpace(environ[entry.UserEnv])
	password := strings.TrimSpace(environ[entry.PasswordEnv])
	missing := make([]string, 0)
	for _, pair := range []struct {
		name  string
		value string
	}{
		{entry.HostEnv, host}, {entry.UserEnv, username}, {entry.PasswordEnv, password},
	} {
		if pair.value == "" {
			missing = append(missing, pair.name)
		}
	}
	if len(missing) > 0 {
		return Credentials{}, fmt.Errorf(
			"Airflow %s needs environment variables %s; set them in .env",
			environment,
			strings.Join(missing, ", "),
		)
	}
	host = strings.TrimRight(host, "/")
	if !strings.HasPrefix(host, "https://") {
		return Credentials{}, fmt.Errorf(
			"%s must be an https:// URL for Airflow %s",
			entry.HostEnv,
			environment,
		)
	}
	return Credentials{Host: host, Username: username, Password: password}, nil
}

func currentEnvironment() map[string]string {
	values := make(map[string]string)
	for _, pair := range os.Environ() {
		name, value, found := strings.Cut(pair, "=")
		if found {
			values[name] = value
		}
	}
	return values
}
