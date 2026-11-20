// Package contract defines the investigation's frozen offline HTTP wire DTOs.
// It contains no provider, service, graph computation or semantic implementation.
package contract

import (
	"encoding/json"
	"fmt"
	"net/url"
	"strings"
)

// Version identifies this investigation-owned boundary snapshot.
const Version = "lineage-http-wire/investigation-v1"

// SourceSHA256 pins the local wire definition mirrored for the used JSON shapes.
const SourceSHA256 = "de86919cd639509e79ea6444e9c12f5bf9a4740616284517a88ad6cbde73290c"

// SourcePath records the original local contract location, not a runtime dependency.
const SourcePath = "lineagegraph/models.go"

// NodeID identifies a logical job, dataset, or a column within a dataset.
// Namespace and name are retained verbatim; names are never guessed from labels.
type NodeID struct {
	Namespace string `json:"namespace"`
	Name      string `json:"name"`
	Column    string `json:"column,omitempty"`
}

// Validate rejects incomplete or whitespace-padded identities.
func (id NodeID) Validate() error {
	for _, part := range []string{id.Namespace, id.Name} {
		if strings.TrimSpace(part) == "" || part != strings.TrimSpace(part) {
			return fmt.Errorf("node identity requires an explicit namespace and name without surrounding whitespace")
		}
	}
	if id.Column != strings.TrimSpace(id.Column) {
		return fmt.Errorf("column identity contains surrounding whitespace")
	}
	return nil
}

// String returns an unambiguous escaped representation suitable for lookup.
func (id NodeID) String() string {
	return url.PathEscape(id.Namespace) + "/" + url.PathEscape(id.Name) + "#" + url.PathEscape(id.Column)
}

// Job is an orchestration node; DAG may be unavailable in external snapshots.
type Job struct {
	DAG             string              `json:"dag,omitempty"`
	Transformations []JobTransformation `json:"transformations,omitempty"`
}

// JobTransformation is a declared implementation inventory, not executable logic.
type JobTransformation struct {
	Name           string `json:"name"`
	Implementation string `json:"implementation"`
	Source         Source `json:"source"`
}

// Dataset records declared logical keys, without asserting physical storage.
type Dataset struct {
	Keys      []string `json:"keys,omitempty"`
	Partition string   `json:"partition,omitempty"`
}

// Column records its declared type and nullability.
type Column struct {
	Type     string `json:"type"`
	Nullable bool   `json:"nullable"`
}

// Source retains provenance without recording production payloads or credentials.
type Source struct {
	Repository string `json:"repository,omitempty"`
	Commit     string `json:"commit,omitempty"`
	Path       string `json:"path,omitempty"`
	SHA256     string `json:"sha256,omitempty"`
	SnapshotID string `json:"snapshot_id,omitempty"`
}

// Location describes declared storage. Verified is false until external proof exists.
type Location struct {
	URI      string `json:"uri"`
	Verified bool   `json:"verified"`
}

// Definition retains human-authored text and its pinned definitions commit.
type Definition struct {
	Text   string `json:"text"`
	Commit string `json:"commit"`
}

// MachineMeaning retains generated text and its upstream generation/evidence pins.
type MachineMeaning struct {
	Description     string `json:"description"`
	BusinessContext string `json:"business_context"`
	GenerationID    string `json:"generation_id"`
	EvidenceSHA256  string `json:"evidence_sha256"`
	Producer        string `json:"producer"`
}

// Meaning keeps approved human and generated descriptions independently visible.
type Meaning struct {
	SME     *Definition     `json:"sme,omitempty"`
	Machine *MachineMeaning `json:"machine,omitempty"`
}

// Formal is a reference only; executable definitions are fetched explicitly.
type Formal struct {
	MethodID string `json:"method_id"`
	Profile  string `json:"profile"`
	Status   string `json:"status"`
	Source   Source `json:"source"`
}

// Facets are independently supplied layers of information about a node.
type Facets struct {
	Location    *Location        `json:"location,omitempty"`
	Meaning     Meaning          `json:"meaning"`
	Formal      *Formal          `json:"formal,omitempty"`
	EventStream *json.RawMessage `json:"event_stream,omitempty"`
	EventSchema *json.RawMessage `json:"event_schema,omitempty"`
}

// Node contains exactly one typed job, dataset, or column body.
type Node struct {
	ID      NodeID   `json:"id"`
	Job     *Job     `json:"job,omitempty"`
	Dataset *Dataset `json:"dataset,omitempty"`
	Column  *Column  `json:"column,omitempty"`
	Facets  Facets   `json:"facets"`
	Sources []Source `json:"sources,omitempty"`
}

// Edge is a directed dependency, membership, consumption, or production relation.
type Edge struct {
	Source NodeID `json:"source"`
	Target NodeID `json:"target"`
	Kind   string `json:"kind"`
}

// Alias explicitly carries a renamed_from identity to its current identity.
type Alias struct {
	RenamedFrom NodeID `json:"renamed_from"`
	Current     NodeID `json:"current"`
}

// Graph is a scoped projection; unresolved findings never imply complete coverage.
type Graph struct {
	Nodes      []Node   `json:"nodes"`
	Edges      []Edge   `json:"edges"`
	Aliases    []Alias  `json:"aliases"`
	Unresolved []string `json:"unresolved"`
}
