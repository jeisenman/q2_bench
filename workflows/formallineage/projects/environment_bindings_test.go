package projects

import (
	"strings"
	"testing"
)

func exampleBindings() []EnvironmentBinding {
	return []EnvironmentBinding{
		{ProfileID: "di-pipelines-python312", Platform: "ra", WorkspaceID: "7628572648057993", IsolationID: "cluster:di-fixture", Root: "/validation/di", Versions: map[string]string{"python": "3.12.1", "spark": "4.1.0", "pandas": "2.2.3"}},
		{ProfileID: "radar-python310", Platform: "ra", WorkspaceID: "7628572648057993", IsolationID: "cluster:radar-fixture", Root: "/validation/radar", Versions: map[string]string{"python": "3.10.12", "spark": "3.5.0", "pandas": "1.5.3"}},
		{ProfileID: "data-ingress-dotnet10", Platform: "native-dotnet", IsolationID: "process:ingress-fixture", Root: "/validation/ingress", Versions: map[string]string{"dotnet_sdk": "10.0.103"}},
		{ProfileID: "calculation-engine-dotnet10", Platform: "native-dotnet", IsolationID: "process:engine-fixture", Root: "/validation/engine", Versions: map[string]string{"dotnet_sdk": "10.0.103"}},
	}
}

func TestSeparateEnvironmentsAndPrivateCaches(t *testing.T) {
	bindings := exampleBindings()
	if err := CheckEnvironmentBindings(bindings); err != nil {
		t.Fatal(err)
	}
	for _, binding := range bindings {
		variables, err := EnvironmentVariables(binding)
		if err != nil {
			t.Fatal(err)
		}
		for name, value := range variables {
			if strings.HasSuffix(name, "CACHE_PATH") || name == "NUGET_PACKAGES" || name == "DOTNET_CLI_HOME" || name == "UV_CACHE_DIR" || name == "UV_PROJECT_ENVIRONMENT" {
				if !strings.HasPrefix(value, binding.Root+"/") {
					t.Fatalf("shared location %s=%s", name, value)
				}
			}
		}
	}
}

func TestRejectSharedOrWrongRuntimeBindings(t *testing.T) {
	tests := []struct {
		name    string
		edit    func([]EnvironmentBinding)
		message string
	}{
		{"same compute", func(b []EnvironmentBinding) { b[1].IsolationID = b[0].IsolationID }, "reuse compute"},
		{"same root", func(b []EnvironmentBinding) { b[1].Root = b[0].Root }, "share or nest"},
		{"nested root", func(b []EnvironmentBinding) { b[1].Root = b[0].Root + "/radar" }, "share or nest"},
		{"wrong python", func(b []EnvironmentBinding) { b[0].Versions["python"] = "3.10.12" }, "requires python"},
		{"wrong spark", func(b []EnvironmentBinding) { b[0].Versions["spark"] = "3.5.0" }, "requires spark"},
		{"SDK below minimum", func(b []EnvironmentBinding) { b[2].Versions["dotnet_sdk"] = "10.0.99" }, "requires dotnet_sdk"},
		{"SDK outside major", func(b []EnvironmentBinding) { b[2].Versions["dotnet_sdk"] = "11.0.100" }, "requires dotnet_sdk"},
		{"wrong workspace", func(b []EnvironmentBinding) { b[1].WorkspaceID = "3510128597187204" }, "requires platform"},
		{"missing identity", func(b []EnvironmentBinding) { b[1].IsolationID = "" }, "isolation ID"},
		{"relative root", func(b []EnvironmentBinding) { b[1].Root = "relative" }, "absolute private"},
		{"duplicate profile", func(b []EnvironmentBinding) { b[1] = b[0] }, "duplicate"},
		{"unknown profile", func(b []EnvironmentBinding) { b[1].ProfileID = "missing" }, "unknown"},
		{"unreviewed suffix", func(b []EnvironmentBinding) { b[0].Versions["python"] = "3.12.1-dev" }, "requires python"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			b := exampleBindings()
			tc.edit(b)
			if err := CheckEnvironmentBindings(b); err == nil || !strings.Contains(err.Error(), tc.message) {
				t.Fatalf("error=%v", err)
			}
		})
	}
	if err := CheckEnvironmentBindings(nil); err == nil {
		t.Fatal("accepted missing bindings")
	}
	b := EnvironmentBinding{ProfileID: "calculation-engine-typescript", Platform: "native-node", IsolationID: "process:node", Root: "/validation/node", Versions: map[string]string{"node": "24.13.0", "typescript": "4.9.4"}}
	if err := CheckEnvironmentBindings([]EnvironmentBinding{b}); err == nil || !strings.Contains(err.Error(), "unresolved") {
		t.Fatal("unknown runtime passed")
	}
}
