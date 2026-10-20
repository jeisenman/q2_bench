package prodsupport

import (
	"fmt"
	"strings"
)

// OmissionGroup identifies a Data Internal omission category.
type OmissionGroup string

const (
	OmitD2P                OmissionGroup = "d2p"
	OmitMI3                OmissionGroup = "mi3"
	OmitSubscriber         OmissionGroup = "subscriber"
	OmitMaintenance        OmissionGroup = "maintenance"
	OmitBackfill           OmissionGroup = "backfill"
	OmitCMM                OmissionGroup = "cmm"
	OmitEventBusHistorical OmissionGroup = "event_bus_to_payloads_historical"
)

var (
	defaultOmissionGroups = []OmissionGroup{
		OmitD2P, OmitMI3, OmitSubscriber, OmitMaintenance, OmitBackfill, OmitCMM,
	}
	supportedOmissionGroups = append(
		append([]OmissionGroup(nil), defaultOmissionGroups...),
		OmitEventBusHistorical,
	)
	omissionPatterns = map[OmissionGroup][]string{
		OmitD2P:                {"delivery_to_promise", "d2p"},
		OmitMI3:                {"market_insights_3", "mi_3", "mi3"},
		OmitSubscriber:         {"check_for_subscriber_client_errors", "subscriber"},
		OmitMaintenance:        {"log_cleanup", "expire_logs", "expire-logs"},
		OmitBackfill:           {"backfill"},
		OmitCMM:                {"credit_migration_matrix", "credit-migration-matrix", "cmm"},
		OmitEventBusHistorical: {"event_bus_to_payloads_historical"},
	}
	omissionCodes = map[OmissionGroup]string{
		OmitD2P:                "D2P",
		OmitMI3:                "MI3",
		OmitSubscriber:         "Subscriber",
		OmitMaintenance:        "log_cleanup",
		OmitBackfill:           "Backfill",
		OmitCMM:                "CMM",
		OmitEventBusHistorical: "event_bus_to_payloads_historical",
	}
)

// DefaultOmissions returns the canonical audience omission order.
func DefaultOmissions() []OmissionGroup {
	return append([]OmissionGroup(nil), defaultOmissionGroups...)
}

// ReportConfig controls audience filtering after recovery verification.
type ReportConfig struct {
	DataInternalOmissions []OmissionGroup
	VerifiedFailureIDs    map[string]struct{}
}

// NewReportConfig parses MCP-safe string values; nil selects defaults.
func NewReportConfig(values []string) (ReportConfig, error) {
	if values == nil {
		return ReportConfig{DataInternalOmissions: DefaultOmissions()}, nil
	}
	parsed := make([]OmissionGroup, 0, len(values))
	seen := make(map[OmissionGroup]struct{}, len(values))
	for _, value := range values {
		if strings.TrimSpace(value) == "" {
			return ReportConfig{}, fmt.Errorf(
				"data_internal_omissions must contain non-empty strings",
			)
		}
		group := OmissionGroup(strings.ToLower(strings.TrimSpace(value)))
		if !validOmissionGroup(group) {
			return ReportConfig{}, fmt.Errorf(
				"unsupported Data Internal omission %q; expected one of: %s",
				value,
				omissionGroupNames(),
			)
		}
		if _, exists := seen[group]; exists {
			return ReportConfig{}, fmt.Errorf("duplicate Data Internal omission: %s", group)
		}
		seen[group] = struct{}{}
		parsed = append(parsed, group)
	}
	return ReportConfig{DataInternalOmissions: parsed}, nil
}

// WithVerifiedOmissions limits omissions to confirmed recovered failures.
func (c ReportConfig) WithVerifiedOmissions(failureIDs []string) ReportConfig {
	verified := make(map[string]struct{}, len(failureIDs))
	for _, failureID := range failureIDs {
		verified[failureID] = struct{}{}
	}
	return ReportConfig{
		DataInternalOmissions: append([]OmissionGroup(nil), c.DataInternalOmissions...),
		VerifiedFailureIDs:    verified,
	}
}

// ConfiguredOmissionGroup returns the configured category before verification.
func (c ReportConfig) ConfiguredOmissionGroup(failure AirflowFailure) OmissionGroup {
	identity := strings.ToLower(failure.DAGID + " " + failure.TaskID)
	for _, group := range c.DataInternalOmissions {
		for _, pattern := range omissionPatterns[group] {
			if strings.Contains(identity, pattern) {
				return group
			}
		}
	}
	return ""
}

// OmissionGroup returns the verified compact-code category for a failure.
func (c ReportConfig) OmissionGroup(failure AirflowFailure) OmissionGroup {
	group := c.ConfiguredOmissionGroup(failure)
	if group == OmitSubscriber {
		return group
	}
	if c.VerifiedFailureIDs != nil {
		if _, verified := c.VerifiedFailureIDs[failure.FailureID()]; !verified {
			return ""
		}
	}
	return group
}

// OmissionCodes returns represented configured codes in canonical order.
func (c ReportConfig) OmissionCodes(failures []AirflowFailure) []string {
	present := make(map[OmissionGroup]struct{})
	for _, failure := range failures {
		if group := c.OmissionGroup(failure); group != "" {
			present[group] = struct{}{}
		}
	}
	codes := make([]string, 0, len(present))
	for _, group := range c.DataInternalOmissions {
		if _, exists := present[group]; exists {
			codes = append(codes, omissionCodes[group])
		}
	}
	return codes
}

// ShorthandCodes returns represented MI3 and D2P codes in channel order.
func (c ReportConfig) ShorthandCodes(failures []AirflowFailure) []string {
	present := make(map[OmissionGroup]struct{})
	for _, failure := range failures {
		present[c.ConfiguredOmissionGroup(failure)] = struct{}{}
	}
	codes := make([]string, 0, 2)
	for _, group := range []OmissionGroup{OmitMI3, OmitD2P} {
		if _, exists := present[group]; exists {
			codes = append(codes, omissionCodes[group])
		}
	}
	return codes
}

// UpdateOmissionValues applies an explicit conversational add/remove request.
func UpdateOmissionValues(current []string, direction string) ([]string, error) {
	lowered := strings.ToLower(direction)
	add := strings.Contains(lowered, "add")
	remove := strings.Contains(lowered, "remove") || strings.Contains(lowered, "delete")
	if add == remove {
		return nil, fmt.Errorf("omission direction must say exactly one of add or remove")
	}
	requested := make([]OmissionGroup, 0)
	for _, group := range supportedOmissionGroups {
		if strings.Contains(lowered, string(group)) ||
			strings.Contains(lowered, strings.ToLower(omissionCodes[group])) {
			requested = append(requested, group)
		}
	}
	if len(requested) == 0 {
		return nil, fmt.Errorf("omission direction must name one of: %s", omissionGroupNames())
	}
	config, err := NewReportConfig(current)
	if err != nil {
		return nil, err
	}
	values := append([]OmissionGroup(nil), config.DataInternalOmissions...)
	for _, group := range requested {
		if add && !containsOmission(values, group) {
			values = append(values, group)
		}
		if remove {
			values = removeOmission(values, group)
		}
	}
	result := make([]string, len(values))
	for index, group := range values {
		result[index] = string(group)
	}
	return result, nil
}

func validOmissionGroup(group OmissionGroup) bool {
	return containsOmission(supportedOmissionGroups, group)
}

func containsOmission(values []OmissionGroup, group OmissionGroup) bool {
	for _, value := range values {
		if value == group {
			return true
		}
	}
	return false
}

func removeOmission(values []OmissionGroup, group OmissionGroup) []OmissionGroup {
	result := make([]OmissionGroup, 0, len(values))
	for _, value := range values {
		if value != group {
			result = append(result, value)
		}
	}
	return result
}

func omissionGroupNames() string {
	values := make([]string, len(supportedOmissionGroups))
	for index, group := range supportedOmissionGroups {
		values[index] = string(group)
	}
	return strings.Join(values, ", ")
}
