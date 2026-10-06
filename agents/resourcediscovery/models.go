// Package resourcediscovery resolves non-secret client and resource metadata.
package resourcediscovery

import (
	"fmt"
	"regexp"
	"strings"
)

// IdentifierKind identifies a supported non-secret search field.
type IdentifierKind string

const (
	ClientID    IdentifierKind = "client_id"
	ClientName  IdentifierKind = "client_name"
	Subdomain   IdentifierKind = "subdomain"
	ResourceID  IdentifierKind = "resource_id"
	ResourceSet IdentifierKind = "resource_set"
	Environment IdentifierKind = "environment"
	Database    IdentifierKind = "database"
	Storage     IdentifierKind = "storage"
	DataLake    IdentifierKind = "datalake"
)

var identifierKinds = []IdentifierKind{
	ClientID, ClientName, Subdomain, ResourceID, ResourceSet,
	Environment, Database, Storage, DataLake,
}

// SearchStatus identifies resource-search cardinality.
type SearchStatus string

const (
	NotFound  SearchStatus = "not_found"
	Unique    SearchStatus = "unique"
	Ambiguous SearchStatus = "ambiguous"
)

// Identifier is one read-only search field and its non-secret value.
type Identifier struct {
	Kind  IdentifierKind
	Value string
}

// Validate checks identifier kind, value, and client UUID completeness.
func (i Identifier) Validate() error {
	if !validIdentifierKind(i.Kind) {
		return fmt.Errorf("kind must be an IdentifierKind")
	}
	if strings.TrimSpace(i.Value) == "" {
		return fmt.Errorf("value must not be empty")
	}
	if i.Kind == ClientID && !validUUID(i.Value) {
		return fmt.Errorf(
			"client_id must be a complete UUID; three-character prefixes are report-only",
		)
	}
	return nil
}

// Metadata contains only allowlisted client and resource fields.
type Metadata struct {
	ResourceID                  string
	ResourceName                string
	ResourceType                string
	ProvisionedClientID         string
	ClientID                    string
	ClientName                  string
	Subdomain                   string
	Environment                 string
	Zone                        string
	Service                     string
	ResourceSet                 string
	Database                    string
	Storage                     string
	DataLake                    string
	ReviewedProductionResendURL string
	RoutingSource               string
	ProdSupportIgnore           bool
}

var metadataFields = []struct {
	key string
	set func(*Metadata, string)
}{
	{"resource_id", func(m *Metadata, v string) { m.ResourceID = v }},
	{"resource_name", func(m *Metadata, v string) { m.ResourceName = v }},
	{"resource_type", func(m *Metadata, v string) { m.ResourceType = v }},
	{"provisioned_client_id", func(m *Metadata, v string) { m.ProvisionedClientID = v }},
	{"client_id", func(m *Metadata, v string) { m.ClientID = v }},
	{"client_name", func(m *Metadata, v string) { m.ClientName = v }},
	{"subdomain", func(m *Metadata, v string) { m.Subdomain = v }},
	{"environment", func(m *Metadata, v string) { m.Environment = v }},
	{"zone", func(m *Metadata, v string) { m.Zone = v }},
	{"service", func(m *Metadata, v string) { m.Service = v }},
	{"resource_set", func(m *Metadata, v string) { m.ResourceSet = v }},
	{"database", func(m *Metadata, v string) { m.Database = v }},
	{"storage", func(m *Metadata, v string) { m.Storage = v }},
	{"datalake", func(m *Metadata, v string) { m.DataLake = v }},
	{"reviewed_production_resend_url", func(m *Metadata, v string) {
		m.ReviewedProductionResendURL = v
	}},
	{"routing_source", func(m *Metadata, v string) { m.RoutingSource = v }},
}

// MetadataFromRecord sanitizes an untrusted record through the fixed allowlist.
func MetadataFromRecord(record map[string]any) (Metadata, error) {
	var metadata Metadata
	hasField := false
	for _, field := range metadataFields {
		value, exists := record[field.key]
		if !exists || value == nil {
			continue
		}
		text, ok := value.(string)
		if !ok {
			return Metadata{}, fmt.Errorf("%s must be a string when present", field.key)
		}
		if strings.TrimSpace(text) == "" {
			return Metadata{}, fmt.Errorf("%s must not be empty", field.key)
		}
		field.set(&metadata, text)
		hasField = true
	}
	if raw, exists := record["prod_support_ignore"]; exists {
		ignore, ok := raw.(bool)
		if !ok {
			return Metadata{}, fmt.Errorf("prod_support_ignore must be a boolean when present")
		}
		metadata.ProdSupportIgnore = ignore
	}
	if !hasField && !metadata.ProdSupportIgnore {
		return Metadata{}, fmt.Errorf("resource metadata must contain at least one field")
	}
	return metadata, nil
}

// Record returns the safe metadata as a sparse map.
func (m Metadata) Record() map[string]any {
	record := make(map[string]any)
	values := []struct {
		key   string
		value string
	}{
		{"resource_id", m.ResourceID},
		{"resource_name", m.ResourceName},
		{"resource_type", m.ResourceType},
		{"provisioned_client_id", m.ProvisionedClientID},
		{"client_id", m.ClientID},
		{"client_name", m.ClientName},
		{"subdomain", m.Subdomain},
		{"environment", m.Environment},
		{"zone", m.Zone},
		{"service", m.Service},
		{"resource_set", m.ResourceSet},
		{"database", m.Database},
		{"storage", m.Storage},
		{"datalake", m.DataLake},
		{"reviewed_production_resend_url", m.ReviewedProductionResendURL},
		{"routing_source", m.RoutingSource},
	}
	for _, item := range values {
		if item.value != "" {
			record[item.key] = item.value
		}
	}
	if m.ProdSupportIgnore {
		record["prod_support_ignore"] = true
	}
	return record
}

// Search contains one identifier and ordered safe matches.
type Search struct {
	Identifier Identifier
	Matches    []Metadata
}

// Status returns explicit result cardinality.
func (s Search) Status() SearchStatus {
	switch len(s.Matches) {
	case 0:
		return NotFound
	case 1:
		return Unique
	default:
		return Ambiguous
	}
}

var uuidPattern = regexp.MustCompile(
	`(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`,
)

func validUUID(value string) bool {
	return uuidPattern.MatchString(value)
}

func validIdentifierKind(kind IdentifierKind) bool {
	for _, candidate := range identifierKinds {
		if kind == candidate {
			return true
		}
	}
	return false
}
