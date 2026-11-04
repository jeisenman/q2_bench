package projects

import "github.com/jeisenman/q2_bench/workflows/formallineage/model"

// EnvironmentProfile scopes an original implementation's reference runtime.
// It does not constrain the separate Python 3.11+ Databricks SDK bridge.
type EnvironmentProfile struct {
	ID          string            `json:"id"`
	Project     string            `json:"project"`
	Platform    string            `json:"platform"`
	Isolation   string            `json:"isolation"`
	WorkspaceID string            `json:"workspace_id,omitempty"`
	Versions    map[string]string `json:"versions"`
	Evidence    []model.Source    `json:"evidence"`
	Unresolved  []string          `json:"unresolved"`
}

// Environments returns independent profiles; no dependency environment is shared.
func Environments() []EnvironmentProfile {
	return []EnvironmentProfile{
		{ID: "di-pipelines-python312", Project: "di-pipelines", Platform: "ra", Isolation: "dedicated-compute", WorkspaceID: "7628572648057993", Versions: map[string]string{"python": "3.12.x", "pandas": "2.2.3", "spark": "4.1.0"}, Evidence: []model.Source{{Commit: "20822fe0d10e812d9858d4ec6d550cce1340cac9", Path: "pyproject.toml", SHA256: "28048ddfd402724389be0ef28a7bdb7c7bb2b5b2ddea19ec79cb9d047674d533"}}, Unresolved: []string{"Bind a separate RA compute resource and verify its complete package inventory before job execution."}},
		{ID: "radar-python310", Project: "radar", Platform: "ra", Isolation: "dedicated-compute", WorkspaceID: "7628572648057993", Versions: map[string]string{"python": "3.10.12", "pandas": "1.5.3", "spark": "3.5.0"}, Evidence: []model.Source{{Commit: "6f72bfb32c447e92cf641a1dd4bcb2b94fac27f9", Path: "cluster_definitions/cluster.json", SHA256: "9618458ea9817acdcc5fa963033c06acf3609b52b2dd3cbf74c50daa669c987f"}}, Unresolved: []string{"Versions observed in RA run 119994231425418; reserve separate compute and verify complete notebook/library dependencies."}},
		{ID: "data-ingress-dotnet10", Project: "data-ingress", Platform: "native-dotnet", Isolation: "separate-process-and-filesystem", Versions: map[string]string{"dotnet_sdk": "10.0.100+"}, Evidence: []model.Source{{Commit: "2b38cb46ac952e26556cd5f82676434247b5577c", Path: "global.json", SHA256: "eebc22778af9e2da192b0cd9b8e3e963a80ffba043904702598b0a928de4a708"}, {Commit: "2b38cb46ac952e26556cd5f82676434247b5577c", Path: "PrecisionLender.DataIngress.Calculations/PrecisionLender.DataIngress.Calculations.csproj", SHA256: "5447bc290a4d5aad08eb6e5b482b4ba0e8a0469aaa2823f716ae3192224edd03"}}, Unresolved: []string{"Native target net10.0; restore/configuration and application proxy dependency closure remain unresolved."}},
		{ID: "calculation-engine-dotnet10", Project: "pl-calculation-engine", Platform: "native-dotnet", Isolation: "separate-process-and-filesystem", Versions: map[string]string{"dotnet_sdk": "10.0.100+"}, Evidence: []model.Source{{Commit: "41616184ea208c601b37918bf942230d6921a7ea", Path: "PrecisionLender.CalculationEngine.Tests/PrecisionLender.CalculationEngine.Tests.csproj", SHA256: "48cc3a976b7379a2fe9f87618a7ea00f81ce80ea53dbb4e274aa652773fd0362"}}, Unresolved: []string{"Test target net10.0; core library netstandard2.1. Native configuration and restored dependency closure remain unresolved."}},
		{ID: "calculation-engine-typescript", Project: "pl-calculation-engine", Platform: "native-node", Isolation: "separate-process-and-filesystem", Versions: map[string]string{"node": "unresolved", "typescript": "4.9.4"}, Evidence: []model.Source{}, Unresolved: []string{"An engine-supported Node runtime must be bound before execution; the host Node installation is not an implicit default."}},
	}
}
