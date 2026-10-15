package local

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadDotEnvLoadsMissingVariablesAndPreservesEnvironment(t *testing.T) {
	t.Setenv("Q2_DOTENV_FILE_VALUE", "existing")
	unsetEnvironment := "Q2_DOTENV_FILE_ONLY"
	os.Unsetenv(unsetEnvironment)
	t.Cleanup(func() { os.Unsetenv(unsetEnvironment) })

	path := filepath.Join(t.TempDir(), ".env")
	content := "Q2_DOTENV_FILE_VALUE=from-file\n" +
		"export Q2_DOTENV_FILE_ONLY=\"from file\"\n"
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}

	if err := LoadDotEnv(path); err != nil {
		t.Fatal(err)
	}
	if got := os.Getenv("Q2_DOTENV_FILE_VALUE"); got != "existing" {
		t.Fatalf("existing value = %q", got)
	}
	if got := os.Getenv(unsetEnvironment); got != "from file" {
		t.Fatalf("loaded value = %q", got)
	}
}

func TestLoadDotEnvTreatsMissingFileAsOptional(t *testing.T) {
	if err := LoadDotEnv(filepath.Join(t.TempDir(), "missing.env")); err != nil {
		t.Fatal(err)
	}
}

func TestLoadDotEnvRejectsMalformedInput(t *testing.T) {
	path := filepath.Join(t.TempDir(), ".env")
	if err := os.WriteFile(path, []byte("not-an-assignment\n"), 0o600); err != nil {
		t.Fatal(err)
	}

	if err := LoadDotEnv(path); err == nil {
		t.Fatal("expected malformed dotenv input to fail")
	}
}
