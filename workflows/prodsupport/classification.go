package prodsupport

import (
	"strings"
)

var (
	distinctnessMarkers = []string{"Distinctness validation failed", "Validate distinctness - counts"}
	oomMarkers          = []string{"OOMKilled", "OutOfMemoryError"}
	timeoutMarkers      = []string{"**TimeoutError", "ErrorTimeout", "AirflowTaskTimeout", "execution_timeout"}
	memoryMarkers       = []string{"memory pressure", "memory limit"}
	exitMinusNine       = []string{"exit -9", "exit code -9", "exit status -9", "return code -9"}
	evidenceMarkers     = []string{
		"Distinctness validation failed", "Validate distinctness - counts",
		"OOMKilled", "OutOfMemoryError", "**TimeoutError", "ErrorTimeout",
		"AirflowTaskTimeout", "execution_timeout", "exit -9", "exit code -9",
		"exit status -9", "return code -9", "SIGKILL", "Traceback", "Exception", "ValueError",
	}
)

// ClassifyLog classifies a log without inferring unsupported causes.
func ClassifyLog(
	failure AirflowFailure,
	log string,
	source EvidenceSource,
) FailureDiagnosis {
	if source == "" {
		source = UnknownEvidence
	}
	lowered := strings.ToLower(log)
	var kind FailureKind
	var confidence string
	switch {
	case containsAny(log, distinctnessMarkers):
		kind, confidence = Distinctness, "confirmed"
	case containsAny(log, oomMarkers):
		kind, confidence = ConfirmedOOM, "confirmed"
	case containsAny(log, timeoutMarkers):
		kind, confidence = OMSConfirmedTimeout, "confirmed"
		if source == AirflowExactTaskAttempt || source == AirflowPriorSameTask {
			kind = AirflowConfirmedTimeout
		}
	case containsAny(lowered, exitMinusNine):
		kind, confidence = UnknownResourceTermination, "unknown"
	case strings.Contains(log, "SIGKILL"):
		kind, confidence = UnknownResourceTermination, "unknown"
		if containsAny(lowered, memoryMarkers) {
			kind, confidence = ProbableOOM, "probable"
		}
	case strings.Contains(log, "Traceback") || strings.Contains(log, "Exception"):
		kind, confidence = ApplicationError, "confirmed"
	default:
		return FailureDiagnosis{
			FailureID: failure.FailureID(), Kind: Unknown, Confidence: "unknown",
			Source: source, Status: EvidenceUnknown, OriginalCharCount: len(log),
		}
	}
	return diagnosis(failure, kind, confidence, log, source)
}

func diagnosis(
	failure AirflowFailure,
	kind FailureKind,
	confidence, log string,
	source EvidenceSource,
) FailureDiagnosis {
	normalized := strings.ReplaceAll(log, `\n`, "\n")
	lines := nonEmptyLines(normalized)
	matching := make([]string, 0, 3)
	for _, line := range lines {
		if containsAny(line, evidenceMarkers) {
			matching = append(matching, line)
		}
	}
	evidence := matching
	if len(evidence) == 0 {
		start := max(0, len(lines)-3)
		evidence = lines[start:]
	}
	if len(evidence) > 3 {
		evidence = evidence[:3]
	}
	return FailureDiagnosis{
		FailureID: failure.FailureID(), Kind: kind, Confidence: confidence,
		Evidence: evidence, Source: source, OriginalCharCount: len(log),
	}
}

func containsAny(value string, markers []string) bool {
	for _, marker := range markers {
		if strings.Contains(value, marker) {
			return true
		}
	}
	return false
}

func nonEmptyLines(value string) []string {
	lines := make([]string, 0)
	for _, line := range strings.Split(value, "\n") {
		if trimmed := strings.TrimSpace(line); trimmed != "" {
			lines = append(lines, trimmed)
		}
	}
	return lines
}
