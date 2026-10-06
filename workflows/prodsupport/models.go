// Package prodsupport contains deterministic production-support workflow logic.
package prodsupport

import (
	"fmt"
	"strings"
	"time"

	"github.com/jeisenman/q2_bench/domain"
)

// Region identifies a production Airflow region.
type Region string

const (
	US01 Region = "US-01"
	CA02 Region = "CA-02"
)

// FailureKind identifies an evidence-based classification.
type FailureKind string

const (
	Omitted                    FailureKind = "omitted"
	Distinctness               FailureKind = "distinctness"
	OMSConfirmedTimeout        FailureKind = "oms_confirmed_timeout"
	AirflowConfirmedTimeout    FailureKind = "airflow_confirmed_timeout"
	ConfirmedOOM               FailureKind = "confirmed_oom"
	ProbableOOM                FailureKind = "probable_oom"
	UnknownResourceTermination FailureKind = "unknown_resource_termination"
	ApplicationError           FailureKind = "application_error"
	Unknown                    FailureKind = "unknown"
)

// EvidenceSource identifies the source used for one diagnosis.
type EvidenceSource string

const (
	UnknownEvidence         EvidenceSource = "unknown"
	AirflowFailureMessage   EvidenceSource = "airflow_failure_message"
	AirflowExactTaskAttempt EvidenceSource = "airflow_exact_task_attempt"
	AirflowPriorSameTask    EvidenceSource = "airflow_prior_same_task"
	OMSExactJob             EvidenceSource = "oms_exact_job"
)

// EvidenceStatus identifies evidence completeness.
type EvidenceStatus string

const (
	EvidenceUnknown       EvidenceStatus = "unknown"
	EvidenceTerminal      EvidenceStatus = "terminal"
	EvidenceNonDiagnostic EvidenceStatus = "non_diagnostic"
	EvidenceTruncated     EvidenceStatus = "truncated"
	EvidenceUnavailable   EvidenceStatus = "unavailable"
)

// AirflowFailure is one failed task instance and captured evidence.
type AirflowFailure struct {
	Region    Region    `json:"region"`
	DAGID     string    `json:"dag_id"`
	RunID     string    `json:"run_id"`
	TaskID    string    `json:"task_id"`
	StartAt   time.Time `json:"start_at"`
	EndAt     time.Time `json:"end_at"`
	TryNumber int       `json:"try_number"`
	Log       string    `json:"log,omitempty"`
}

// Validate checks required task identity and timing.
func (f AirflowFailure) Validate() error {
	if f.StartAt.IsZero() || f.EndAt.IsZero() {
		return fmt.Errorf("Airflow timestamps must be timezone-aware")
	}
	if f.EndAt.Before(f.StartAt) {
		return fmt.Errorf("Airflow failure end time must not precede start time")
	}
	if f.TryNumber < 1 {
		return fmt.Errorf("Airflow try number must be positive")
	}
	for name, value := range map[string]string{
		"dag_id": f.DAGID, "run_id": f.RunID, "task_id": f.TaskID,
	} {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("%s must not be empty", name)
		}
	}
	if f.Region != US01 && f.Region != CA02 {
		return fmt.Errorf("unsupported Airflow region %q", f.Region)
	}
	return nil
}

// FailureID returns a stable regional task-instance identifier.
func (f AirflowFailure) FailureID() string {
	return strings.Join([]string{string(f.Region), f.DAGID, f.RunID, f.TaskID}, "|")
}

// RetryCandidate is one numbered failed task eligible for follow-up.
type RetryCandidate struct {
	Number int    `json:"number"`
	Region Region `json:"region"`
	DAGID  string `json:"dag_id"`
	RunID  string `json:"run_id"`
	TaskID string `json:"task_id"`
	Label  string `json:"label"`
}

// Identity returns the stable regional task-instance identity.
func (c RetryCandidate) Identity() string {
	return strings.Join([]string{string(c.Region), c.DAGID, c.RunID, c.TaskID}, "|")
}

// PriorTaskLog is one earlier exact attempt for the same DAG and task.
type PriorTaskLog struct {
	RunID     string `json:"run_id"`
	TryNumber int    `json:"try_number"`
	Log       string `json:"log"`
}

// Validate checks prior-attempt identity.
func (l PriorTaskLog) Validate() error {
	if strings.TrimSpace(l.RunID) == "" {
		return fmt.Errorf("prior task-log run_id must not be empty")
	}
	if l.TryNumber < 1 {
		return fmt.Errorf("prior task-log try_number must be positive")
	}
	return nil
}

// FailureDiagnosis is an evidence-based diagnosis for one failure.
type FailureDiagnosis struct {
	FailureID         string         `json:"failure_id"`
	Kind              FailureKind    `json:"kind"`
	Confidence        string         `json:"confidence"`
	Evidence          []string       `json:"evidence,omitempty"`
	Source            EvidenceSource `json:"source"`
	Status            EvidenceStatus `json:"status"`
	OriginalCharCount int            `json:"original_char_count"`
}

// Outcome is the structured production-support result.
type Outcome struct {
	OperationalDate          time.Time
	FailedSince              time.Time
	Failures                 []AirflowFailure
	Diagnoses                []FailureDiagnosis
	Report                   string
	DeveloperReport          string
	DataInternalReport       string
	FollowUp                 string
	ResourceDiscoveryResults []domain.AgentResult
	Regions                  []Region
	RetryCandidates          []RetryCandidate
}
