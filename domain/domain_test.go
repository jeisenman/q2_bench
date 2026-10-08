package domain

import (
	"errors"
	"strings"
	"testing"
)

func TestParseEnvironment(t *testing.T) {
	t.Parallel()
	environment, err := ParseEnvironment(" Sandbox ")
	if err != nil {
		t.Fatal(err)
	}
	if !environment.Deterministic() || environment.Production() {
		t.Fatalf("unexpected environment flags: %q", environment)
	}
	if _, err := ParseEnvironment("unknown"); err == nil {
		t.Fatal("expected unsupported environment to fail")
	}
}

func TestBenchmarkIdentityQualifiedName(t *testing.T) {
	t.Parallel()
	identity, err := NewBenchmarkIdentity("data_transformation", "prod-support", "", nil)
	if err != nil {
		t.Fatal(err)
	}
	if got := identity.QualifiedName(); got != "data_transformation/prod-support" {
		t.Fatalf("QualifiedName() = %q", got)
	}
}

func TestAgentDefinitionRejectsDuplicateTools(t *testing.T) {
	t.Parallel()
	tool := ToolDefinition{Name: "lookup", Description: "Look up data."}
	definition := AgentDefinition{
		Name: "agent", Description: "Description.", Instructions: "Instructions.",
		Tools: []ToolDefinition{tool, tool},
	}
	if err := definition.Validate(); err == nil || !strings.Contains(err.Error(), "duplicate") {
		t.Fatalf("Validate() error = %v", err)
	}
}

func TestSQLPortability(t *testing.T) {
	t.Parallel()
	if err := RequirePortable("SELECT client_code FROM jobs"); err != nil {
		t.Fatal(err)
	}
	statement := "SELECT payload:region, RANDOM() FROM t WHERE ts < NOW()"
	err := RequirePortable(statement)
	var portabilityError *SQLPortabilityError
	if !errors.As(err, &portabilityError) {
		t.Fatalf("expected SQLPortabilityError, got %v", err)
	}
	if len(portabilityError.Violations) != 3 {
		t.Fatalf("violations = %v", portabilityError.Violations)
	}
}

func TestSQLNoiseIsIgnored(t *testing.T) {
	t.Parallel()
	for _, statement := range []string{
		"SELECT 'payload:region' AS example",
		"SELECT n FROM t -- avoid CURRENT_TIMESTAMP here",
		"SELECT n FROM t /* OBJECT_CONSTRUCT was removed */",
	} {
		if err := RequirePortable(statement); err != nil {
			t.Fatalf("RequirePortable(%q): %v", statement, err)
		}
	}
}

func TestAICortexCallsAreNotPortable(t *testing.T) {
	t.Parallel()
	if !IsCortexCall("SELECT AI_COMPLETE('model', 'prompt')") {
		t.Fatal("AI_COMPLETE must be routed through CortexInference")
	}
}
