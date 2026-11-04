// Package projects defines source boundaries and runtime validation targets.
package projects

import "fmt"

// Repository binds a repository name to its currently reviewed source pin.
type Repository struct {
	Name   string `json:"name"`
	Commit string `json:"commit"`
	Scope  string `json:"scope"`
}

// Project defines an independently scoped adapter sharing the formal model.
type Project struct {
	ID                 string       `json:"id"`
	Repositories       []Repository `json:"repositories"`
	Runtimes           []string     `json:"runtimes"`
	ValidationPlatform string       `json:"validation_platform"`
	WorkspaceID        string       `json:"workspace_id,omitempty"`
	MinimumPython      string       `json:"minimum_python,omitempty"`
	EnvironmentIDs     []string     `json:"environment_ids"`
	PredictionReady    bool         `json:"prediction_ready"`
}

// All returns fresh project definitions; pins are evidence, not moving HEADs.
func All() []Project {
	result := []Project{
		{ID: "di-pipelines", Repositories: []Repository{{"di-pipelines", "20822fe0d10e812d9858d4ec6d550cce1340cac9", "All jobs; basic copy/dispatch steps remain part of their transformation unit."}}, Runtimes: []string{"pyspark"}, ValidationPlatform: "ra", WorkspaceID: "7628572648057993"},
		{ID: "radar", Repositories: []Repository{{"radar-notebooks", "60beb1ccd9bb2074f440de27e0e8f8956acab884", "Notebook Python and retained notebook magic."}, {"radar-libraries", "6f72bfb32c447e92cf641a1dd4bcb2b94fac27f9", "Shared Python libraries."}, {"radar-adf-pipeline", "99102279764c67b34d8eb054d754e6bdf4a1c6bc", "ADF orchestration and nested activity declarations."}}, Runtimes: []string{"pandas", "pyspark", "adf"}, ValidationPlatform: "ra", WorkspaceID: "7628572648057993"},
		{ID: "data-ingress", Repositories: []Repository{{"pl-dataingress", "2b38cb46ac952e26556cd5f82676434247b5577c", "C# ingestion and engine calls."}, {"pl-application", "5af19e313f0012911d695abb6cf1690650a24874", "PrecisionLender.Common.Engine.Proxy/ServiceWrappers/ only."}}, Runtimes: []string{"dotnet"}, ValidationPlatform: "native-dotnet"},
		{ID: "pl-calculation-engine", Repositories: []Repository{{"pl-calculation-engine", "41616184ea208c601b37918bf942230d6921a7ea", "C#/TypeScript implementations, build manifests and package locks."}}, Runtimes: []string{"dotnet", "typescript"}, ValidationPlatform: "native-runtime"},
	}
	for i := range result {
		if result[i].ID == "di-pipelines" {
			result[i].MinimumPython = "3.12"
		} else if result[i].ID == "radar" {
			result[i].MinimumPython = "3.10"
		}
		for _, environment := range Environments() {
			if environment.Project == result[i].ID {
				result[i].EnvironmentIDs = append(result[i].EnvironmentIDs, environment.ID)
			}
		}
	}
	return result
}

// Get returns a known project or an actionable error.
func Get(id string) (Project, error) {
	for _, project := range All() {
		if project.ID == id {
			return project, nil
		}
	}
	return Project{}, fmt.Errorf("unknown formal-lineage project %q", id)
}

// Allows rejects accidental cross-project source attribution.
func Allows(project, repository string) error {
	p, err := Get(project)
	if err != nil {
		return err
	}
	for _, repo := range p.Repositories {
		if repo.Name == repository {
			return nil
		}
	}
	return fmt.Errorf("repository %q is outside project %q", repository, project)
}
