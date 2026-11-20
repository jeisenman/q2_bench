package contract

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestWireRoundtripAndOmission(t *testing.T) {
	raw := `{"nodes":[{"id":{"namespace":"q2://test","name":"input"},"dataset":{"keys":["id"],"partition":"date"},"facets":{"meaning":{"sme":{"text":"Supplied","commit":"review"},"machine":{"description":"Draft","business_context":"Context","generation_id":"generation","evidence_sha256":"evidence","producer":"model"}},"formal":{"method_id":"method","profile":"profile","status":"draft","source":{"repository":"repo","commit":"commit","path":"file","sha256":"digest","snapshot_id":"snapshot"}}},"sources":[{"repository":"repo","commit":"commit","path":"file","sha256":"digest","snapshot_id":"snapshot"}]},{"id":{"namespace":"q2://test","name":"job"},"job":{"dag":"dag","transformations":[{"name":"declared","implementation":"pkg.Job","source":{"path":"job.go"}}]},"facets":{"location":{"uri":"declared://path","verified":false},"meaning":{},"event_stream":{"opaque":"retained"},"event_schema":{"schema":"retained"}}},{"id":{"namespace":"q2://test","name":"input","column":"id"},"column":{"type":"string","nullable":false},"facets":{"meaning":{}}}],"edges":[{"source":{"namespace":"q2://test","name":"job"},"target":{"namespace":"q2://test","name":"input"},"kind":"produces"}],"aliases":[{"renamed_from":{"namespace":"q2://test","name":"old"},"current":{"namespace":"q2://test","name":"input"}}],"unresolved":["Missing evidence"]}`
	var graph Graph
	if err := json.Unmarshal([]byte(raw), &graph); err != nil {
		t.Fatal(err)
	}
	encoded, err := json.Marshal(graph)
	if err != nil {
		t.Fatal(err)
	}
	if string(encoded) != raw {
		t.Fatalf("wire serialization changed:\n%s", encoded)
	}
	for _, text := range []string{`{"nodes":[{"id":{"namespace":"n","name":"d"},"dataset":{},"facets":{"meaning":{},"event_stream":null,"event_schema":null}}],"edges":null,"aliases":null,"unresolved":null}`, `{"nodes":[{"id":{"namespace":"n","name":"d"},"dataset":{},"facets":{"meaning":{}}}],"edges":[],"aliases":[],"unresolved":[]}`} {
		var g Graph
		if err := json.Unmarshal([]byte(text), &g); err != nil {
			t.Fatal(err)
		}
		b, err := json.Marshal(g)
		if err != nil {
			t.Fatal(err)
		}
		if strings.Contains(string(b), "event_stream") || strings.Contains(string(b), "event_schema") {
			t.Fatal("null optional facet was retained")
		}
	}
}

func TestIdentityMethodsAndMalformedJSON(t *testing.T) {
	ids := []NodeID{{Namespace: "a/b", Name: "c#d"}, {Namespace: "a", Name: "b/c#d"}, {Namespace: "a/b", Name: "c", Column: "d"}, {Namespace: "a/b", Name: "c#d", Column: "[x]/%"}}
	seen := map[string]bool{}
	for _, id := range ids {
		if err := id.Validate(); err != nil {
			t.Fatal(err)
		}
		if seen[id.String()] {
			t.Fatal("escaped identities collided")
		}
		seen[id.String()] = true
	}
	for _, id := range []NodeID{{Name: "a"}, {Namespace: "test", Name: " "}, {Namespace: " test", Name: "a"}, {Namespace: "test", Name: "a", Column: " bad "}} {
		if err := id.Validate(); err == nil {
			t.Fatal("invalid identity accepted")
		}
	}
	var graph Graph
	for _, bad := range []string{`{"nodes":"bad"}`, `{"nodes":[{"id":{"name":1}}]}`, `{"nodes":[{"facets":{"meaning":{"machine":{"description":false}}}}]}`} {
		if err := json.Unmarshal([]byte(bad), &graph); err == nil {
			t.Fatal("invalid typed JSON accepted")
		}
	}
	if Version != "lineage-http-wire/investigation-v1" || SourceSHA256 != "de86919cd639509e79ea6444e9c12f5bf9a4740616284517a88ad6cbde73290c" {
		t.Fatal("contract provenance changed")
	}
}
