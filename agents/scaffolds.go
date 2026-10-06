package agents

import "github.com/jeisenman/q2_bench/domain"

// NewKPOSizer returns the version-one KPO sizing scaffold.
func NewKPOSizer() *PlanningAgent {
	return mustPlanningAgent(
		domain.AgentDefinition{
			Name: "kpo-sizer", Version: "1",
			Description:  "Size KPO work and produce traceable supporting evidence.",
			Instructions: "Collect evidence, estimate scope, and report assumptions explicitly.",
			Tools: []domain.ToolDefinition{
				{Name: "CollectEvidence", Description: "Collect allowlisted sizing evidence."},
				{Name: "EstimateKpo", Description: "Estimate KPO size from validated evidence."},
			},
		},
		[]WorkflowStep{
			{Name: "validate", Outcome: "confirm the sizing objective and constraints"},
			{Name: "evidence", Outcome: "collect traceable, non-secret evidence"},
			{Name: "estimate", Outcome: "calculate size and state assumptions"},
			{Name: "report", Outcome: "return the estimate with evidence references"},
		},
	)
}

// NewETL returns the version-one ETL planning scaffold.
func NewETL() *PlanningAgent {
	return mustPlanningAgent(
		domain.AgentDefinition{
			Name: "etl", Version: "1",
			Description:  "Define DAGs, write jobs, wire metadata, and identify test data.",
			Instructions: "Plan typed, testable ETL changes and fail on unresolved data contracts.",
			Tools: []domain.ToolDefinition{
				{Name: "DefineDag", Description: "Define an Airflow DAG contract."},
				{Name: "WriteJob", Description: "Create a typed data-processing job."},
				{Name: "WireMetadata", Description: "Register lineage and dataset metadata."},
				{Name: "FindTestData", Description: "Locate relevant test data through Data Finder."},
			},
		},
		[]WorkflowStep{
			{Name: "contract", Outcome: "validate source, transform, and sink contracts"},
			{Name: "discover", Outcome: "use Data Finder to identify test fixtures"},
			{Name: "dag", Outcome: "define scheduling, dependencies, and retries"},
			{Name: "job", Outcome: "implement typed and deterministic processing"},
			{Name: "metadata", Outcome: "wire ownership, lineage, and observability"},
			{Name: "verify", Outcome: "run success, boundary, and failure scenarios"},
		},
	)
}

// NewDataFinder returns the version-one data discovery scaffold.
func NewDataFinder() *PlanningAgent {
	return mustPlanningAgent(
		domain.AgentDefinition{
			Name: "data-finder", Version: "1",
			Description:  "Find relevant data across injected datastore connectors.",
			Instructions: "Search read-only connectors and return provenance without credentials.",
			Tools: []domain.ToolDefinition{
				{Name: "ListConnectors", Description: "List eligible read-only datastore connectors."},
				{Name: "SearchData", Description: "Search connector metadata and bounded samples."},
			},
		},
		[]WorkflowStep{
			{Name: "criteria", Outcome: "validate required fields and search bounds"},
			{Name: "connectors", Outcome: "select eligible read-only connectors"},
			{Name: "search", Outcome: "query metadata before bounded data samples"},
			{Name: "rank", Outcome: "rank matches deterministically with provenance"},
			{Name: "report", Outcome: "return locations without secrets or hidden answers"},
		},
	)
}

// NewDataCreator returns the version-one synthetic-data scaffold.
func NewDataCreator() *PlanningAgent {
	return mustPlanningAgent(
		domain.AgentDefinition{
			Name: "data-creator", Version: "1",
			Description:  "Generate deterministic test data through injected connectors.",
			Instructions: "Validate schemas and require explicit write targets before generation.",
			Tools: []domain.ToolDefinition{
				{Name: "InspectSchema", Description: "Read the target schema and constraints."},
				{Name: "GenerateData", Description: "Generate deterministic synthetic records."},
				{Name: "WriteTestData", Description: "Write records through an approved connector."},
			},
		},
		[]WorkflowStep{
			{Name: "target", Outcome: "validate the connector, schema, and write scope"},
			{Name: "model", Outcome: "derive boundary and failure-case records"},
			{Name: "generate", Outcome: "produce deterministic synthetic data"},
			{Name: "write", Outcome: "persist only after explicit target validation"},
			{Name: "verify", Outcome: "read back counts and constraint outcomes"},
		},
	)
}

// NewDataInsightTriage returns the version-one missing-data scaffold.
func NewDataInsightTriage() *PlanningAgent {
	return mustPlanningAgent(
		domain.AgentDefinition{
			Name: "data-insight-triage", Version: "1",
			Description:  "Trace where and why expected production data is missing.",
			Instructions: "Correlate triage, OMS, Airflow, and datastore evidence before diagnosis.",
			Tools: []domain.ToolDefinition{
				{Name: "Triage", Description: "Classify the missing-data symptom and impact."},
				{Name: "QueryOms", Description: "Query approved production-support OMS views."},
				{Name: "InspectAirflow", Description: "Inspect DAG, task, and dependency evidence."},
				{Name: "FindData", Description: "Trace records across datastore connectors."},
			},
		},
		[]WorkflowStep{
			{Name: "triage", Outcome: "bound the missing entity, interval, and impact"},
			{Name: "oms", Outcome: "establish expected upstream production state"},
			{Name: "airflow", Outcome: "trace DAG and task execution evidence"},
			{Name: "data", Outcome: "use Data Finder to locate the last known record"},
			{Name: "diagnose", Outcome: "identify the first unsupported transition"},
			{Name: "report", Outcome: "separate evidence, inference, and remediation"},
		},
	)
}

// NewBenchmarkBuilder returns the version-one benchmark builder scaffold.
func NewBenchmarkBuilder() *PlanningAgent {
	return mustPlanningAgent(
		domain.AgentDefinition{
			Name: "benchmark-builder", Version: "1",
			Description:  "Guide extraction, mocking, and reproducible benchmark construction.",
			Instructions: "Use isolated subprocess workers and keep hidden expectations protected.",
			Tools: []domain.ToolDefinition{
				{Name: "SpawnWorker", Description: "Spawn a bounded benchmark-building subprocess."},
				{Name: "ExtractScenario", Description: "Extract sanitized scenario inputs."},
				{Name: "BuildMocks", Description: "Create deterministic provider mocks."},
				{Name: "AuditLeakage", Description: "Run public-hidden and container-security checks."},
			},
		},
		[]WorkflowStep{
			{Name: "scope", Outcome: "define behavior and protected expectations"},
			{Name: "workers", Outcome: "spawn bounded subprocesses for guided extraction"},
			{Name: "extract", Outcome: "sanitize inputs and preserve provenance"},
			{Name: "mock", Outcome: "recreate provider behavior deterministically"},
			{Name: "evaluate", Outcome: "define public rubric and protected assertions"},
			{Name: "audit", Outcome: "run anti-leak and runtime-security checks"},
		},
	)
}

func mustPlanningAgent(
	definition domain.AgentDefinition,
	steps []WorkflowStep,
) *PlanningAgent {
	agent, err := NewPlanningAgent(definition, steps)
	if err != nil {
		panic(err)
	}
	return agent
}
