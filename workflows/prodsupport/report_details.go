package prodsupport

import (
	"fmt"
	"regexp"
	"sort"
	"strconv"
	"strings"

	"github.com/jeisenman/q2_bench/domain"
)

const (
	clientDAGPrefix     = "l3-main-"
	resendTask          = "validate_event_bus_opportunities"
	eventBusHistoryTask = "get_opp_history_params"
	eventBusDAG         = "event_bus_to_payloads_historical"
)

var (
	reportUUIDPattern = regexp.MustCompile(
		`(?i)(?:^|[^0-9a-f])([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:$|[^0-9a-f])`,
	)
	eventCountPattern = regexp.MustCompile(
		`(?i)(\d[\d,]*)\s+(?:unique\s+)?(?:missing\s+)?(?:opportunity\s+)?(?:snapshots?|events?)`,
	)
	opportunityIDPattern = regexp.MustCompile(`(?i)OpportunityId:\s*([0-9a-f-]{36})`)
)

// ClientIdentity is reviewed identity and routing metadata.
type ClientIdentity struct {
	ClientID          string
	Name              string
	Status            string
	Environment       string
	ReviewedResendURL string
	ProdSupportIgnore bool
}

// FailureGroup minimizes repeated clients and jobs in reports.
type FailureGroup struct {
	SubjectLabels []string
	Jobs          []string
	Failures      []AirflowFailure
}

// ClientIdentities indexes structured Resource Discovery results by UUID.
func ClientIdentities(results []domain.AgentResult) map[string]ClientIdentity {
	identities := make(map[string]ClientIdentity)
	for _, result := range results {
		attributes := make(map[string]any, len(result.Attributes))
		for _, attribute := range result.Attributes {
			attributes[attribute.Name] = attribute.Value
		}
		identifier, identifierOK := attributes["identifier_value"].(string)
		status, statusOK := attributes["status"].(string)
		if !identifierOK || !statusOK {
			continue
		}
		trusted := status == "unique" || status == "user_confirmed" || status == "reviewed"
		identity := ClientIdentity{ClientID: identifier, Status: status}
		if trusted {
			identity.Name, _ = attributes["client_name"].(string)
			identity.Environment, _ = attributes["environment"].(string)
			identity.ReviewedResendURL, _ = attributes["reviewed_production_resend_url"].(string)
		}
		identity.ProdSupportIgnore = attributes["prod_support_ignore"] == true
		identities[identifier] = identity
	}
	return identities
}

// DataInternalClientIdentities applies channel-only client-name conventions.
func DataInternalClientIdentities(
	results []domain.AgentResult,
) map[string]ClientIdentity {
	identities := ClientIdentities(results)
	for identifier, identity := range identities {
		identity.Name = dataInternalName(identity.Name)
		identities[identifier] = identity
	}
	return identities
}

// ClientIDs extracts all validated client UUIDs from failure identity and logs.
func ClientIDs(failure AirflowFailure) []string {
	candidates := make([]string, 0)
	if strings.HasPrefix(failure.DAGID, clientDAGPrefix) {
		candidates = append(candidates, strings.TrimPrefix(failure.DAGID, clientDAGPrefix))
	}
	candidates = append(candidates, UUIDsFromText(failure.TaskID)...)
	if failure.DAGID == eventBusDAG && failure.TaskID == eventBusHistoryTask {
		candidates = append(candidates, UUIDsFromText(failure.Log)...)
	}
	identifiers := make([]string, 0, len(candidates))
	for _, candidate := range candidates {
		if !looseUUID(candidate) || contains(identifiers, strings.ToLower(candidate)) {
			continue
		}
		identifiers = append(identifiers, strings.ToLower(candidate))
	}
	return identifiers
}

// UUIDsFromText extracts normalized UUIDs from evidence text.
func UUIDsFromText(text string) []string {
	identifiers := make([]string, 0)
	for _, match := range reportUUIDPattern.FindAllStringSubmatch(text, -1) {
		identifier := strings.ToLower(match[1])
		if !contains(identifiers, identifier) {
			identifiers = append(identifiers, identifier)
		}
	}
	return identifiers
}

// FailureSubject returns a reviewed client or recurring-issue label.
func FailureSubject(
	failure AirflowFailure,
	identities map[string]ClientIdentity,
) string {
	identifiers := ClientIDs(failure)
	if len(identifiers) > 0 {
		return subjectForIdentifier(identifiers[0], identities)
	}
	if strings.Contains(failure.DAGID, "market_insights") {
		return "Market Insights 3"
	}
	if strings.Contains(failure.TaskID, "subscriber") {
		return "Subscriber validation"
	}
	return failure.DAGID
}

// JobLabel normalizes reviewed aliases while preserving task identifiers.
func JobLabel(taskID string) string {
	lowered := strings.ToLower(taskID)
	rules := []struct{ marker, label string }{
		{eventBusHistoryTask, eventBusDAG},
		{"delivery_to_promise_other_products", "D2P—Other Products"},
		{"delivery_to_promise", "D2P"},
		{"market_insights_3", "MI3"},
		{"market_insights", "MI3"},
		{resendTask, resendTask},
		{"credit_migration_matrix", "CMM"},
	}
	for _, rule := range rules {
		if strings.Contains(lowered, rule.marker) {
			return rule.label
		}
	}
	if strings.Contains(lowered, "mi_3") {
		return "MI3"
	}
	if before, _, found := strings.Cut(taskID, "."); found {
		return before
	}
	return taskID
}

// HiddenFromReport identifies non-actionable maintenance tasks.
func HiddenFromReport(failure AirflowFailure) bool {
	hidden := map[string]struct{}{"log_cleanup": {}, "expire_logs_3": {}}
	_, taskHidden := hidden[JobLabel(failure.TaskID)]
	_, dagHidden := hidden[strings.ToLower(failure.DAGID)]
	return taskHidden || dagHidden
}

// IsResendFailure identifies tasks requiring event-resend handling.
func IsResendFailure(failure AirflowFailure) bool {
	lowered := strings.ToLower(failure.TaskID)
	return strings.Contains(lowered, resendTask) ||
		(failure.DAGID == eventBusDAG && strings.Contains(lowered, eventBusHistoryTask))
}

// EventCount returns the largest stated count or unique opportunity-ID count.
func EventCount(diagnosis FailureDiagnosis, log string) *int {
	maximum := 0
	sources := append(append([]string(nil), diagnosis.Evidence...), log)
	ids := make(map[string]struct{})
	for _, source := range sources {
		for _, match := range eventCountPattern.FindAllStringSubmatch(source, -1) {
			value, _ := strconv.Atoi(strings.ReplaceAll(match[1], ",", ""))
			if value > maximum {
				maximum = value
			}
		}
		for _, match := range opportunityIDPattern.FindAllStringSubmatch(source, -1) {
			ids[strings.ToLower(match[1])] = struct{}{}
		}
	}
	if len(ids) > maximum {
		maximum = len(ids)
	}
	if maximum == 0 {
		return nil
	}
	return &maximum
}

// GroupFailuresByJob returns deterministic human-readable job groups.
func GroupFailuresByJob(failures []AirflowFailure) map[string][]AirflowFailure {
	grouped := make(map[string][]AirflowFailure)
	for _, failure := range failures {
		label := JobLabel(failure.TaskID)
		grouped[label] = append(grouped[label], failure)
	}
	for _, items := range grouped {
		sort.Slice(items, func(left, right int) bool {
			return failureSortKey(items[left]) < failureSortKey(items[right])
		})
	}
	return grouped
}

func subjectForIdentifier(
	identifier string,
	identities map[string]ClientIdentity,
) string {
	name := identities[identifier].Name
	if name == "" {
		name = "Unresolved client"
	}
	return fmt.Sprintf("%s (%s)", name, identifier)
}

func dataInternalName(name string) string {
	lowered := strings.ToLower(strings.TrimSpace(name))
	for _, pair := range [][2]string{
		{"scotiabank - data validation", "Scotiabank DV"},
		{"wells fargo", "WF"}, {"city national bank", "CNB"},
		{"bank of america", "BoFA"}, {"bofa", "BoFA"}, {"cibc canada", "CIBC CA"},
	} {
		if strings.HasPrefix(lowered, pair[0]) {
			return pair[1]
		}
	}
	return name
}

func looseUUID(value string) bool {
	return len(value) == 36 && len(UUIDsFromText(" "+value+" ")) == 1
}

func failureSortKey(failure AirflowFailure) string {
	return fmt.Sprintf(
		"%s\x00%s\x00%s\x00%s\x00%09d",
		failure.Region,
		failure.DAGID,
		failure.TaskID,
		failure.RunID,
		failure.TryNumber,
	)
}
