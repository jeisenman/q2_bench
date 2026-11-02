// Package lineagecheck builds source-pinned lineage contracts and audits changes.
package lineagecheck

// Format identifies the independently maintained structural contract.
const Format = "q2-lineage-contract/v1"

// Repository pins one source checkout to an immutable Git commit.
type Repository struct {
	Name   string `json:"name"`
	Commit string `json:"commit"`
}

// Evidence binds a reviewed contract to the exact source bytes it describes.
type Evidence struct {
	Repository string `json:"repository"`
	Path       string `json:"path"`
	SHA256     string `json:"sha256"`
}

// Field is a physical or explicitly declared partition column.
type Field struct {
	Name     string `json:"name"`
	Type     string `json:"type"`
	Nullable bool   `json:"nullable"`
}

// SchemaSource selects a literal PySpark schema at a pinned source location.
type SchemaSource struct {
	Evidence Evidence `json:"evidence"`
	Class    string   `json:"class"`
	Major    int      `json:"major"`
}

// Dataset is a versioned logical dataset with its consumed schema and keys.
type Dataset struct {
	ID        string        `json:"id"`
	Major     int           `json:"major"`
	Minor     int           `json:"minor"`
	Fields    []Field       `json:"fields"`
	Keys      []string      `json:"keys"`
	Partition string        `json:"partition"`
	Schema    *SchemaSource `json:"schema,omitempty"`
	Evidence  []Evidence    `json:"evidence"`
}

// Input records the fields and join keys actually consumed by a job.
type Input struct {
	Dataset string   `json:"dataset"`
	Major   int      `json:"major"`
	Fields  []string `json:"fields"`
	Keys    []string `json:"keys"`
}

// FieldRef identifies a dataset column in a transformation dependency.
type FieldRef struct {
	Dataset string `json:"dataset"`
	Field   string `json:"field"`
}

// Dependency records value, filter, join, or other row-affecting dependencies.
type Dependency struct {
	Output FieldRef   `json:"output"`
	Inputs []FieldRef `json:"inputs"`
}

// Replay describes the historical write contract of a job invocation.
type Replay struct {
	BypassSchedule bool   `json:"bypass_schedule"`
	Mode           string `json:"mode"`
	HourUTC        int    `json:"hour_utc"`
	WriteMode      string `json:"write_mode"`
	Force          bool   `json:"force"`
	ClientScope    string `json:"client_scope"`
}

// Job describes a transformation, copy, or reporting task across DAGs.
type Job struct {
	ID              string       `json:"id"`
	DAG             string       `json:"dag"`
	Inputs          []Input      `json:"inputs"`
	Outputs         []string     `json:"outputs"`
	After           []string     `json:"after"`
	Dependencies    []Dependency `json:"dependencies"`
	ColumnsComplete bool         `json:"columns_complete"`
	Replay          Replay       `json:"replay"`
	Evidence        []Evidence   `json:"evidence"`
}

// Manifest is a reviewed structural extraction recipe scoped to named products.
type Manifest struct {
	Format       string       `json:"format"`
	Scope        string       `json:"scope"`
	Profile      string       `json:"profile"`
	Repositories []Repository `json:"repositories"`
	Datasets     []Dataset    `json:"datasets"`
	Jobs         []Job        `json:"jobs"`
	Unresolved   []string     `json:"unresolved"`
}

// Snapshot is an immutable, content-addressed build of one reviewed manifest.
type Snapshot struct {
	Format    string   `json:"format"`
	ID        string   `json:"id"`
	Extractor string   `json:"extractor"`
	Manifest  Manifest `json:"manifest"`
}

// Finding explains a broken contract or a gap in available evidence.
type Finding struct {
	Severity string `json:"severity"`
	Code     string `json:"code"`
	Entity   string `json:"entity"`
	Message  string `json:"message"`
}

// Report is deterministic and passes only when no errors or unknowns remain.
type Report struct {
	Status       string     `json:"status"`
	Scope        string     `json:"scope"`
	BaseID       string     `json:"base_id,omitempty"`
	HeadID       string     `json:"head_id"`
	Affected     []FieldRef `json:"affected"`
	RequiredJobs []string   `json:"required_jobs"`
	Findings     []Finding  `json:"findings"`
}

func (r *Report) add(severity, code, entity, message string) {
	r.Findings = append(r.Findings, Finding{severity, code, entity, message})
}

func (r *Report) finish() {
	r.Status = "pass"
	for _, f := range r.Findings {
		if f.Severity == "unknown" && r.Status == "pass" {
			r.Status = "unknown"
		}
		if f.Severity == "error" {
			r.Status = "fail"
		}
	}
}
