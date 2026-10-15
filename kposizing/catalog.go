package kposizing

import (
	"fmt"
	"strings"
	"unicode/utf8"
)

// InputMode identifies how a job selects its source input.
type InputMode string

const (
	// InputModeRAFile reads a named file from an RA run.
	InputModeRAFile InputMode = "ra_file"
	// InputModeDatedHDM reads a dated Historical Data Mart partition.
	InputModeDatedHDM InputMode = "dated_hdm"
	// InputModeHistoricalLatest uses the HistoricalLatest path convention.
	InputModeHistoricalLatest InputMode = "historical_latest"
	// InputModeAuditSelected reads partitions selected by audit metadata.
	InputModeAuditSelected InputMode = "audit_selected"
)

// Validate rejects an unknown input mode.
func (m InputMode) Validate() error {
	switch m {
	case InputModeRAFile, InputModeDatedHDM, InputModeHistoricalLatest, InputModeAuditSelected:
		return nil
	default:
		return fmt.Errorf("input mode %q is unsupported", m)
	}
}

// AuxiliaryInputPolicy identifies verified companion-input behavior.
type AuxiliaryInputPolicy string

const (
	// AuxiliaryInputNone means no companion input is part of the known template.
	AuxiliaryInputNone AuxiliaryInputPolicy = "none"
	// AuxiliaryInputUnchanged means the job attempts the main and Unchanged RA files.
	AuxiliaryInputUnchanged AuxiliaryInputPolicy = "unchanged"
	// AuxiliaryInputUnchangedConditional means Unchanged data is included when present.
	AuxiliaryInputUnchangedConditional AuxiliaryInputPolicy = "unchanged_if_present"
)

// Validate rejects an unknown auxiliary-input policy.
func (p AuxiliaryInputPolicy) Validate() error {
	switch p {
	case AuxiliaryInputNone, AuxiliaryInputUnchanged, AuxiliaryInputUnchangedConditional:
		return nil
	default:
		return fmt.Errorf("auxiliary input policy %q is unsupported", p)
	}
}

// RunnerChoice describes one verified runner and family route.
type RunnerChoice struct {
	Runner         Runner               `json:"runner"`
	Family         TransformationFamily `json:"family"`
	AuxiliaryInput AuxiliaryInputPolicy `json:"auxiliary_input"`
	Condition      string               `json:"condition,omitempty"`
	Provenance     []ProvenanceRef      `json:"provenance"`
}

// SourceIdentity records verified static source identity without runtime paths.
type SourceIdentity struct {
	Dataset string `json:"dataset,omitempty"`
	Stage   string `json:"stage,omitempty"`
	Version string `json:"version,omitempty"`
	File    string `json:"file,omitempty"`
}

// ProvenanceRef identifies a stable source repository file and symbol.
type ProvenanceRef struct {
	Repository string `json:"repository"`
	File       string `json:"file"`
	Symbol     string `json:"symbol"`
}

// JobTemplate records only the static, verified portion of one KPO workload.
//
// Zero row and concurrency values mean that the catalog does not know that
// value. Returned templates are defensive copies of package-owned data.
type JobTemplate struct {
	Job               string               `json:"job"`
	Aliases           []string             `json:"aliases,omitempty"`
	DefaultRunner     Runner               `json:"default_runner"`
	DefaultFamily     TransformationFamily `json:"default_family"`
	RunnerChoices     []RunnerChoice       `json:"runner_choices"`
	InputMode         InputMode            `json:"input_mode"`
	InputNote         string               `json:"input_note,omitempty"`
	Source            SourceIdentity       `json:"source"`
	AuxiliaryInput    AuxiliaryInputPolicy `json:"auxiliary_input"`
	ChunkRows         uint64               `json:"chunk_rows,omitempty"`
	OutputChunkRows   uint64               `json:"output_chunk_rows,omitempty"`
	CopyConcurrency   int                  `json:"copy_concurrency,omitempty"`
	UploadConcurrency int                  `json:"upload_concurrency,omitempty"`
	Provenance        []ProvenanceRef      `json:"provenance"`
}

// ListJobTemplates returns all canonical templates in deterministic order.
func ListJobTemplates() []JobTemplate {
	templates := staticJobTemplates()
	result := make([]JobTemplate, len(templates))
	for index, template := range templates {
		result[index] = cloneJobTemplate(template)
	}
	return result
}

// LookupJobTemplate resolves a canonical name or documented alias.
func LookupJobTemplate(name string) (JobTemplate, error) {
	nameLength := utf8.RuneCountInString(name)
	if nameLength > MaxJobNameLength {
		return JobTemplate{}, fmt.Errorf(
			"job name length %d exceeds maximum %d",
			nameLength,
			MaxJobNameLength,
		)
	}
	normalized := strings.TrimSpace(name)
	if normalized == "" {
		return JobTemplate{}, fmt.Errorf(
			"job name must not be blank; available canonical jobs: %s",
			availableJobNames(),
		)
	}
	for _, template := range staticJobTemplates() {
		if normalized == template.Job || containsString(template.Aliases, normalized) {
			return cloneJobTemplate(template), nil
		}
	}
	return JobTemplate{}, fmt.Errorf(
		"unknown KPO job %q; available canonical jobs: %s",
		normalized,
		availableJobNames(),
	)
}

// ApplyJobTemplateDefaults applies verified defaults for name to workload.
func ApplyJobTemplateDefaults(name string, workload Workload) (Workload, error) {
	template, err := LookupJobTemplate(name)
	if err != nil {
		return Workload{}, err
	}
	return applyJobTemplate(template, workload)
}

// ApplyDefaults applies this template's canonical catalog defaults.
func (t JobTemplate) ApplyDefaults(workload Workload) (Workload, error) {
	template, err := LookupJobTemplate(t.Job)
	if err != nil {
		return Workload{}, fmt.Errorf("apply job template: %w", err)
	}
	return applyJobTemplate(template, workload)
}

func applyJobTemplate(template JobTemplate, workload Workload) (Workload, error) {
	result := workload
	result.Profile.FileBytes = append([]uint64(nil), workload.Profile.FileBytes...)
	result.Profile.TopConcurrentFileBytes = append(
		[]uint64(nil),
		workload.Profile.TopConcurrentFileBytes...,
	)
	if err := applyJobName(template, &result); err != nil {
		return Workload{}, err
	}
	route, err := selectRunnerChoice(template, result.Runner, result.Family)
	if err != nil {
		return Workload{}, err
	}
	result.Runner = route.Runner
	result.Family = route.Family
	if route.Family != template.DefaultFamily {
		return result, nil
	}
	if err := applyUint64Default("chunk_rows", template.ChunkRows, &result.Profile.ChunkRows); err != nil {
		return Workload{}, err
	}
	if err := applyUint64Default(
		"output_chunk_rows",
		template.OutputChunkRows,
		&result.Profile.OutputChunkRows,
	); err != nil {
		return Workload{}, err
	}
	if err := applyIntDefault(
		"copy_concurrency",
		template.CopyConcurrency,
		&result.Profile.CopyConcurrency,
	); err != nil {
		return Workload{}, err
	}
	if err := applyIntDefault(
		"upload_concurrency",
		template.UploadConcurrency,
		&result.Profile.UploadConcurrency,
	); err != nil {
		return Workload{}, err
	}
	return result, nil
}

func applyJobName(template JobTemplate, workload *Workload) error {
	if strings.TrimSpace(workload.Job) == "" {
		workload.Job = template.Job
		return nil
	}
	selected, err := LookupJobTemplate(workload.Job)
	if err != nil {
		return fmt.Errorf("workload job contradicts template %q: %w", template.Job, err)
	}
	if selected.Job != template.Job {
		return fmt.Errorf(
			"workload job %q resolves to %q, which contradicts template %q",
			workload.Job,
			selected.Job,
			template.Job,
		)
	}
	workload.Job = template.Job
	return nil
}

func selectRunnerChoice(
	template JobTemplate,
	runner Runner,
	family TransformationFamily,
) (RunnerChoice, error) {
	if runner == "" && family == "" {
		runner = template.DefaultRunner
		family = template.DefaultFamily
	}
	for _, route := range template.RunnerChoices {
		runnerMatches := runner == "" || runner == route.Runner
		familyMatches := family == "" || family == route.Family
		if runnerMatches && familyMatches {
			return route, nil
		}
	}
	return RunnerChoice{}, fmt.Errorf(
		"runner %q and family %q contradict job template %q; allowed routes: %s",
		runner,
		family,
		template.Job,
		formatRunnerChoices(template.RunnerChoices),
	)
}

func applyUint64Default(name string, known uint64, target **uint64) error {
	if known == 0 {
		return nil
	}
	if *target != nil {
		if **target != known {
			return fmt.Errorf("%s %d contradicts known template value %d", name, **target, known)
		}
		return nil
	}
	value := known
	*target = &value
	return nil
}

func applyIntDefault(name string, known int, target **int) error {
	if known == 0 {
		return nil
	}
	if *target != nil {
		if **target != known {
			return fmt.Errorf("%s %d contradicts known template value %d", name, **target, known)
		}
		return nil
	}
	value := known
	*target = &value
	return nil
}

func cloneJobTemplate(template JobTemplate) JobTemplate {
	result := template
	result.Aliases = append([]string(nil), template.Aliases...)
	result.RunnerChoices = make([]RunnerChoice, len(template.RunnerChoices))
	for index, route := range template.RunnerChoices {
		result.RunnerChoices[index] = route
		result.RunnerChoices[index].Provenance = append([]ProvenanceRef(nil), route.Provenance...)
	}
	result.Provenance = append([]ProvenanceRef(nil), template.Provenance...)
	return result
}

func availableJobNames() string {
	templates := staticJobTemplates()
	names := make([]string, len(templates))
	for index, template := range templates {
		names[index] = template.Job
	}
	return strings.Join(names, ", ")
}

func formatRunnerChoices(choices []RunnerChoice) string {
	values := make([]string, len(choices))
	for index, choice := range choices {
		values[index] = string(choice.Runner) + "/" + string(choice.Family)
	}
	return strings.Join(values, ", ")
}

func containsString(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}
