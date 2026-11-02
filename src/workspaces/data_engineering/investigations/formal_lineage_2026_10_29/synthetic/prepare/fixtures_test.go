package main

import (
	"encoding/json"
	"testing"
)

func TestFilterCases(t *testing.T) {
	data := []byte(`{"synthetic":true,"clock":"fixed","cases":[{"id":"a","stage":"one"},{"id":"b","stage":"two"},{"id":"c","stage":"one"}]}`)
	filtered, err := filterCases(data, "one")
	if err != nil {
		t.Fatal(err)
	}
	var got struct {
		Clock string
		Cases []struct{ ID string }
	}
	if err := json.Unmarshal(filtered, &got); err != nil {
		t.Fatal(err)
	}
	if got.Clock != "fixed" || len(got.Cases) != 2 || got.Cases[0].ID != "a" || got.Cases[1].ID != "c" {
		t.Fatalf("selection changed order or metadata: %s", filtered)
	}
	for _, invalid := range []string{"unknown", "one,", "one,unknown"} {
		if _, err := filterCases(data, invalid); err == nil {
			t.Fatalf("accepted selector %q", invalid)
		}
	}
	if _, err := filterCases([]byte(`{"cases":"invalid"}`), "one"); err == nil {
		t.Fatal("accepted invalid fixtures")
	}
}
