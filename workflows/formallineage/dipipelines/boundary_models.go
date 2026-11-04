package dipipelines

// BoundaryClause retains an exact source operation, even when it cannot execute.
type BoundaryClause struct {
	ID         string             `json:"id"`
	Source     Source             `json:"source"`
	Function   string             `json:"function"`
	Line       int                `json:"line"`
	StartByte  uint               `json:"start_byte"`
	EndByte    uint               `json:"end_byte"`
	Kind       string             `json:"kind"`
	Expression string             `json:"expression"`
	Families   []string           `json:"families"`
	CaseIDs    []string           `json:"case_ids"`
	Blocked    string             `json:"blocked,omitempty"`
	EdgeCases  []string           `json:"edge_cases"`
	Mutations  []BoundaryMutation `json:"fixture_mutations,omitempty"`
	Findings   []BoundaryFinding  `json:"findings,omitempty"`
}

// BoundaryFinding is a conservative source-rule contradiction within the profile.
type BoundaryFinding struct {
	Code         string `json:"code"`
	Field        string `json:"field"`
	Message      string `json:"message"`
	OperatorPath string `json:"operator_path"`
}

// BoundaryMutation measures whether fixtures detect an artificial IR fault.
// It measures fixture sensitivity, not execution of mutated application source.
type BoundaryMutation struct {
	Change string `json:"change"`
	Status string `json:"status"`
}

// BoundaryCheck explains one source-specific obligation in ordinary language.
type BoundaryCheck struct {
	ClauseID string `json:"clause_id"`
	Given    string `json:"given,omitempty"`
	Assert   string `json:"assert,omitempty"`
}

// BoundaryScenario bundles many independent rows/checks within one job scenario.
// Planned checks are never reported as executed coverage.
type BoundaryScenario struct {
	ID           string          `json:"id"`
	Title        string          `json:"title"`
	Status       string          `json:"status"`
	Checks       []BoundaryCheck `json:"checks"`
	ClauseFamily string          `json:"clause_family"`
	ClauseChecks int             `json:"clause_checks"`
}

// BoundaryJob includes source jobs absent from the published semantic graph.
type BoundaryJob struct {
	EntryPoint string             `json:"entrypoint"`
	LineageIDs []string           `json:"lineage_ids"`
	UnitIDs    []string           `json:"unit_ids"`
	Copies     []CopyTarget       `json:"copies"`
	Sources    []Source           `json:"sources"`
	Clauses    []BoundaryClause   `json:"-"`
	ClauseIDs  []string           `json:"clause_ids"`
	Scenarios  []BoundaryScenario `json:"scenarios"`
	Gaps       []string           `json:"gaps"`
	Status     string             `json:"status"`
}

// BoundarySuite is a source-pinned test design and its executable clause subset.
// Cases test isolated clauses; they do not establish whole-job equivalence.
type BoundarySuite struct {
	Format         string                   `json:"format"`
	Commit         string                   `json:"commit"`
	GraphSHA256    string                   `json:"graph_sha256"`
	GraphID        string                   `json:"graph_id"`
	GenerationID   string                   `json:"generation_id"`
	ScenarioLimit  int                      `json:"scenario_limit"`
	PropertyConfig *PropertyConfig          `json:"property_config,omitempty"`
	LogicalJobs    []LogicalBoundary        `json:"logical_jobs"`
	Jobs           []BoundaryJob            `json:"jobs"`
	Cases          []ComparisonCase         `json:"cases"`
	Clauses        []BoundaryClause         `json:"clauses"`
	Procedures     map[string]BoundaryCheck `json:"scenario_procedures"`
	CaseBatches    []BoundaryBatch          `json:"case_batches"`
	Status         string                   `json:"status"`
}

// BoundaryBatch identifies an exact persisted execution batch.
type BoundaryBatch struct {
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
	Count  int    `json:"count"`
}

// LogicalBoundary accounts for every published job, including orchestration.
type LogicalBoundary struct {
	ID              string            `json:"id"`
	Implementations []string          `json:"implementations"`
	Scope           string            `json:"scope"`
	Status          string            `json:"status"`
	Scenarios       []LogicalScenario `json:"scenarios"`
}

// LogicalScenario groups the same scenario family across a logical job's units.
type LogicalScenario struct {
	ID              string   `json:"id"`
	Title           string   `json:"title"`
	Implementations []string `json:"implementations"`
	Status          string   `json:"status"`
}

// ClauseEvidence identifies the original expression and its generated adapter.
type ClauseEvidence struct {
	Source    Source          `json:"source"`
	StartByte uint            `json:"start_byte"`
	EndByte   uint            `json:"end_byte"`
	Adapter   string          `json:"adapter"`
	Literals  []ClauseLiteral `json:"literal_bindings,omitempty"`
}

// ClauseLiteral pins a primitive literal copied into an isolated clause adapter.
// It assumes no indirect mutation between the definition and invocation.
type ClauseLiteral struct {
	Name      string `json:"name"`
	StartByte uint   `json:"start_byte"`
	EndByte   uint   `json:"end_byte"`
}
