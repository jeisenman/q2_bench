package prodsupport

import (
	"fmt"
	"strings"
)

const (
	DefaultEvidenceLines      = 3
	DefaultEvidenceCharacters = 1200
)

var (
	terminalMarkers = []string{
		"airflowtasktimeout", "distinctness", "exception", "exit -9",
		"exit code -9", "failed", "oomkilled", "outofmemoryerror", "sigkill", "traceback",
	}
	truncationMarkers = []string{"log truncated", "truncated log", "was not found in the log"}
	countMarkers      = []string{"missing opportunity", "unique events", "unique missing"}
)

// TaskLogSummary is bounded evidence retained from an exact attempt.
type TaskLogSummary struct {
	Status            EvidenceStatus
	OriginalCharCount int
	Excerpt           string
}

// SummarizeTaskLog selects diagnostic lines and bounds the raw log body.
func SummarizeTaskLog(log string, maxLines, maxCharacters int) (TaskLogSummary, error) {
	if maxLines == 0 {
		maxLines = DefaultEvidenceLines
	}
	if maxCharacters == 0 {
		maxCharacters = DefaultEvidenceCharacters
	}
	if maxLines < 1 {
		return TaskLogSummary{}, fmt.Errorf("max_lines must be positive")
	}
	if maxCharacters < 1 {
		return TaskLogSummary{}, fmt.Errorf("max_characters must be positive")
	}
	normalized := strings.ReplaceAll(log, `\n`, "\n")
	lines := nonEmptyLines(normalized)
	relevant := make([]string, 0)
	for _, line := range lines {
		lowered := strings.ToLower(line)
		if containsAny(lowered, append(terminalMarkers, countMarkers...)) {
			relevant = append(relevant, line)
		}
	}
	selected := relevant
	if len(selected) == 0 {
		selected = lines[max(0, len(lines)-maxLines):]
	}
	if len(selected) > maxLines {
		selected = selected[:maxLines]
	}
	excerpt := strings.Join(selected, "\n")
	if len(excerpt) > maxCharacters {
		excerpt = excerpt[:maxCharacters]
	}
	status := EvidenceNonDiagnostic
	switch {
	case containsAny(strings.ToLower(normalized), truncationMarkers):
		status = EvidenceTruncated
	case len(relevant) > 0:
		status = EvidenceTerminal
	}
	return TaskLogSummary{
		Status: status, OriginalCharCount: len(log), Excerpt: excerpt,
	}, nil
}
