package resourcediscovery

import (
	"fmt"
	"regexp"
	"sort"
	"strings"
)

var (
	scotiabankDataValidation = regexp.MustCompile(`(?i)^scotiabank\s*-\s*data\s+validation$`)
	nameKeyCharacters        = regexp.MustCompile(`[^a-z0-9]+`)
	parenthetical            = regexp.MustCompile(`\([^)]*\)`)
	acronymWords             = regexp.MustCompile(`[A-Za-z0-9]+`)
)

var acronymStopWords = map[string]struct{}{"and": {}, "of": {}, "the": {}}

const minAcronymLength = 2

// ParseClientName applies approved display-name conventions.
func ParseClientName(name string) string {
	normalized := strings.Join(strings.Fields(name), " ")
	if scotiabankDataValidation.MatchString(normalized) {
		return "Scotiabank DV"
	}
	if strings.EqualFold(normalized, "bofa") {
		return "Bank of America"
	}
	return normalized
}

// ClientNameIndexKey returns a punctuation-insensitive client-name key.
func ClientNameIndexKey(name string) string {
	parsed := strings.ToLower(ParseClientName(name))
	return strings.TrimSpace(nameKeyCharacters.ReplaceAllString(parsed, " "))
}

// ClientNameAcronym returns a deterministic canonical-name acronym.
func ClientNameAcronym(name string) string {
	parsed := parenthetical.ReplaceAllString(ParseClientName(name), "")
	var acronym strings.Builder
	for _, word := range acronymWords.FindAllString(parsed, -1) {
		if _, skip := acronymStopWords[strings.ToLower(word)]; !skip {
			acronym.WriteByte(byte(strings.ToLower(word)[0]))
		}
	}
	return acronym.String()
}

// ClientLookupIndex indexes authoritative client records by UUID and name.
type ClientLookupIndex struct {
	byUUID    map[string]map[string]any
	byName    map[string][]map[string]any
	byAcronym map[string][]map[string]any
}

// NewClientLookupIndex builds an index from non-secret quick-lookup metadata.
func NewClientLookupIndex(payload map[string]any) *ClientLookupIndex {
	index := &ClientLookupIndex{
		byUUID:    make(map[string]map[string]any),
		byName:    make(map[string][]map[string]any),
		byAcronym: make(map[string][]map[string]any),
	}
	for rawUUID, rawEntry := range payload {
		entry, ok := rawEntry.(map[string]any)
		if !ok || !validUUID(rawUUID) {
			continue
		}
		record, ok := indexedRecord(rawUUID, entry)
		if !ok {
			continue
		}
		index.byUUID[rawUUID] = record
		originalName := entry["name"].(string)
		parsedName := record["client_name"].(string)
		nameSet := map[string]struct{}{originalName: {}, parsedName: {}}
		for name := range nameSet {
			key := ClientNameIndexKey(name)
			index.byName[key] = append(index.byName[key], record)
			acronym := ClientNameAcronym(name)
			if len(acronym) >= minAcronymLength {
				index.byAcronym[acronym] = appendUniqueRecord(index.byAcronym[acronym], record)
			}
		}
	}
	for _, records := range index.byName {
		sortRecords(records)
	}
	for _, records := range index.byAcronym {
		sortRecords(records)
	}
	return index
}

// Lookup returns indexed records for supported client identifiers.
func (i *ClientLookupIndex) Lookup(identifier Identifier) []map[string]any {
	switch identifier.Kind {
	case ClientID:
		record, exists := i.byUUID[strings.ToLower(identifier.Value)]
		if !exists {
			return nil
		}
		return []map[string]any{cloneRecord(record)}
	case ClientName:
		return cloneRecords(i.byName[ClientNameIndexKey(identifier.Value)])
	default:
		return nil
	}
}

// AliasCandidates returns canonical records matching one generated acronym.
func (i *ClientLookupIndex) AliasCandidates(alias string) []map[string]any {
	return cloneRecords(i.byAcronym[ClientNameIndexKey(alias)])
}

func indexedRecord(clientUUID string, entry map[string]any) (map[string]any, bool) {
	name, nameOK := entry["name"].(string)
	source, sourceOK := entry["source"].(string)
	status, statusOK := entry["api_status"].(string)
	authoritative := source == "resource-discovery-api" || source == "user-confirmed"
	if !nameOK || strings.TrimSpace(name) == "" || !sourceOK || !authoritative ||
		(!statusOK && source != "user-confirmed") ||
		(status != "unique-match" && source != "user-confirmed") {
		return nil, false
	}
	record := map[string]any{
		"provisioned_client_id": clientUUID,
		"client_name":           ParseClientName(name),
		"routing_source":        fmt.Sprintf("local-client-index:%s", source),
	}
	for _, field := range []string{
		"client_id", "subdomain", "environment", "service", "resource_id",
		"resource_set", "reviewed_production_resend_url",
	} {
		if value, ok := entry[field].(string); ok && strings.TrimSpace(value) != "" {
			record[field] = value
		}
	}
	if value, ok := entry["prod_support_ignore"].(bool); ok {
		record["prod_support_ignore"] = value
	}
	return record, true
}

func appendUniqueRecord(records []map[string]any, record map[string]any) []map[string]any {
	id := record["provisioned_client_id"]
	for _, existing := range records {
		if existing["provisioned_client_id"] == id {
			return records
		}
	}
	return append(records, record)
}

func sortRecords(records []map[string]any) {
	sort.Slice(records, func(left, right int) bool {
		return fmt.Sprint(records[left]["provisioned_client_id"]) <
			fmt.Sprint(records[right]["provisioned_client_id"])
	})
}

func cloneRecord(record map[string]any) map[string]any {
	cloned := make(map[string]any, len(record))
	for key, value := range record {
		cloned[key] = value
	}
	return cloned
}

func cloneRecords(records []map[string]any) []map[string]any {
	cloned := make([]map[string]any, len(records))
	for index, record := range records {
		cloned[index] = cloneRecord(record)
	}
	return cloned
}
