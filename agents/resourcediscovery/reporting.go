package resourcediscovery

import (
	"fmt"
	"strings"

	"github.com/jeisenman/q2_bench/agentmemory"
	"github.com/jeisenman/q2_bench/domain"
)

var displayFields = []struct {
	label string
	value func(Metadata) string
}{
	{"Client name", func(m Metadata) string { return m.ClientName }},
	{"Provisioned client ID", func(m Metadata) string { return m.ProvisionedClientID }},
	{"Client ID", func(m Metadata) string { return m.ClientID }},
	{"Subdomain", func(m Metadata) string { return m.Subdomain }},
	{"Environment", func(m Metadata) string { return m.Environment }},
	{"Zone", func(m Metadata) string { return m.Zone }},
	{"Service", func(m Metadata) string { return m.Service }},
	{"Resource set", func(m Metadata) string { return m.ResourceSet }},
	{"Resource ID", func(m Metadata) string { return m.ResourceID }},
	{"Resource name", func(m Metadata) string { return m.ResourceName }},
	{"Resource type", func(m Metadata) string { return m.ResourceType }},
	{"Database", func(m Metadata) string { return m.Database }},
	{"Storage", func(m Metadata) string { return m.Storage }},
	{"DataLake", func(m Metadata) string { return m.DataLake }},
	{"Reviewed resend URL", func(m Metadata) string { return m.ReviewedProductionResendURL }},
	{"Routing source", func(m Metadata) string { return m.RoutingSource }},
}

func renderSearch(search Search) string {
	lines := []string{
		"# Resource Discovery", "", "Version: v2",
		"Identifier: " + search.Identifier.Value, "",
	}
	switch search.Status() {
	case NotFound:
		return strings.Join(append(lines,
			"Finding: no unique match",
			"Resource Discovery:",
			"- No unique match was returned.",
			"",
			"Ambiguities:",
			"- None.",
		), "\n")
	case Ambiguous:
		lines = append(lines, "Finding: Ambiguous matches", "")
	default:
		lines = append(lines, "Finding: unique match", "")
	}
	for index, metadata := range search.Matches {
		if index > 0 {
			lines = append(lines, "", fmt.Sprintf("Match %d:", index+1))
		}
		lines = append(lines, "Resource Discovery:")
		for _, field := range displayFields {
			if value := field.value(metadata); value != "" {
				lines = append(lines, fmt.Sprintf("- %s: %s", field.label, value))
			}
		}
		if metadata.ProdSupportIgnore {
			lines = append(lines, "- Production support: ignored by reviewed configuration")
		}
	}
	lines = append(lines, "", "Ambiguities:")
	if search.Status() == Ambiguous {
		lines = append(lines, "- Multiple records matched; provide a more specific identifier.")
	} else {
		lines = append(lines, "- None.")
	}
	return strings.Join(lines, "\n")
}

func searchResult(
	search Search,
	correlationID string,
	extra domain.Attributes,
) domain.AgentResult {
	var unique Metadata
	if len(search.Matches) == 1 {
		unique = search.Matches[0]
	}
	attributes := domain.Attributes{
		{Name: "agent_version", Value: "2"},
		{Name: "identifier_kind", Value: string(search.Identifier.Kind)},
		{Name: "identifier_value", Value: search.Identifier.Value},
		{Name: "status", Value: string(search.Status())},
		{Name: "match_count", Value: len(search.Matches)},
		{Name: "client_name", Value: nilIfEmpty(unique.ClientName)},
		{Name: "provisioned_client_id", Value: nilIfEmpty(unique.ProvisionedClientID)},
		{Name: "environment", Value: nilIfEmpty(unique.Environment)},
		{Name: "reviewed_production_resend_url", Value: nilIfEmpty(unique.ReviewedProductionResendURL)},
		{Name: "routing_source", Value: nilIfEmpty(unique.RoutingSource)},
		{Name: "prod_support_ignore", Value: unique.ProdSupportIgnore},
	}
	attributes = append(attributes, extra...)
	return domain.AgentResult{
		Output: renderSearch(search), CorrelationID: correlationID,
		ToolCalls: []string{"ResourceDiscovery"}, Attributes: attributes,
	}
}

func confirmationResult(memory agentmemory.Record, correlationID string) domain.AgentResult {
	metadata := memoryMetadata(memory)
	name := metadata["canonical_name"]
	canonicalID := metadata["canonical_entity_id"]
	return domain.AgentResult{
		Output: fmt.Sprintf(
			"By %s, do you mean %s (%s)?\nConfirm memory %s.",
			memory.Key,
			name,
			canonicalID,
			memory.ID,
		),
		CorrelationID: correlationID,
		ToolCalls:     []string{"ResourceDiscovery"},
		Attributes: domain.Attributes{
			{Name: "status", Value: "confirmation_required"},
			{Name: "memory_id", Value: memory.ID},
			{Name: "memory_status", Value: string(memory.Status)},
			{Name: "memory_evidence_count", Value: memory.EvidenceCount},
			{Name: "candidate_client_name", Value: name},
			{Name: "candidate_provisioned_client_id", Value: canonicalID},
		},
	}
}

func feedbackOutput(
	memory agentmemory.Record,
	outcome agentmemory.EvidenceOutcome,
	promoteAfter int,
) string {
	if outcome == agentmemory.EvidenceRejected {
		return fmt.Sprintf("Rejected alias memory %s.", memory.ID)
	}
	if memory.Status == agentmemory.Confirmed {
		return fmt.Sprintf(
			"Confirmed alias memory %s; future lookups may resolve.",
			memory.ID,
		)
	}
	return fmt.Sprintf(
		"Recorded confirmation %d/%d for alias memory %s.",
		memory.EvidenceCount,
		promoteAfter,
		memory.ID,
	)
}

func memoryMetadata(memory agentmemory.Record) map[string]string {
	values := make(map[string]string, len(memory.Metadata))
	for _, item := range memory.Metadata {
		values[item.Name] = item.Value
	}
	return values
}

func nilIfEmpty(value string) any {
	if value == "" {
		return nil
	}
	return value
}
