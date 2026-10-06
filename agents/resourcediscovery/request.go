package resourcediscovery

import (
	"fmt"
	"regexp"
	"strings"

	"github.com/jeisenman/q2_bench/agentmemory"
	"github.com/jeisenman/q2_bench/domain"
)

var lookupPrompt = regexp.MustCompile(
	`(?i)^\s*(?:find|lookup|look\s+up|resolve|get|show)\s+(?:the\s+)?(?:client\s+)?(.+?)\s*[?!.]*\s*$`,
)

type memoryFeedback struct {
	ID      string
	Outcome agentmemory.EvidenceOutcome
}

func requestValues(request domain.AgentRequest) (map[string]any, error) {
	values := make(map[string]any, len(request.Attributes))
	for _, attribute := range request.Attributes {
		if _, exists := values[attribute.Name]; exists {
			return nil, fmt.Errorf("request attribute %q is duplicated", attribute.Name)
		}
		values[attribute.Name] = attribute.Value
	}
	return values, nil
}

func requestIdentifier(request domain.AgentRequest, values map[string]any) (Identifier, error) {
	identifierValue, legacy := values["identifier"]
	if !legacy {
		kindValue, hasKind := values["identifier_kind"]
		identifierValue, hasValue := values["identifier_value"]
		if !hasKind && !hasValue {
			match := lookupPrompt.FindStringSubmatch(request.Prompt)
			if len(match) != 2 {
				return Identifier{}, fmt.Errorf(
					"request must include identifier attributes or use 'find <client>' lookup wording",
				)
			}
			identifier := Identifier{Kind: ClientName, Value: match[1]}
			return identifier, identifier.Validate()
		}
		kindText, ok := kindValue.(string)
		if !ok {
			return Identifier{}, fmt.Errorf(
				"request must include string attribute 'identifier_kind'",
			)
		}
		kind := IdentifierKind(kindText)
		if !validIdentifierKind(kind) {
			values := make([]string, len(identifierKinds))
			for index, item := range identifierKinds {
				values[index] = string(item)
			}
			return Identifier{}, fmt.Errorf(
				"identifier_kind must be one of: %s",
				strings.Join(values, ", "),
			)
		}
		text, ok := identifierValue.(string)
		if !ok {
			return Identifier{}, fmt.Errorf(
				"request must include string attribute 'identifier'",
			)
		}
		identifier := Identifier{Kind: kind, Value: text}
		return identifier, identifier.Validate()
	}
	text, ok := identifierValue.(string)
	if !ok {
		return Identifier{}, fmt.Errorf("request must include string attribute 'identifier'")
	}
	identifier := Identifier{Kind: ResourceID, Value: text}
	return identifier, identifier.Validate()
}

func parseMemoryFeedback(values map[string]any) (*memoryFeedback, error) {
	rawID, hasID := values["memory_id"]
	rawOutcome, hasOutcome := values["memory_outcome"]
	if !hasID && !hasOutcome {
		return nil, nil
	}
	id, idOK := rawID.(string)
	if !idOK {
		return nil, fmt.Errorf("memory_id must be a UUID string")
	}
	outcomeText, outcomeOK := rawOutcome.(string)
	if !outcomeOK {
		return nil, fmt.Errorf("memory_outcome must be 'confirmed' or 'rejected'")
	}
	outcome := agentmemory.EvidenceOutcome(outcomeText)
	if !validUUID(id) ||
		(outcome != agentmemory.EvidenceConfirmed && outcome != agentmemory.EvidenceRejected) {
		return nil, fmt.Errorf("memory confirmation attributes are invalid")
	}
	return &memoryFeedback{ID: id, Outcome: outcome}, nil
}
