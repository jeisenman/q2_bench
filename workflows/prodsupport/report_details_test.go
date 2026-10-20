package prodsupport

import (
	"reflect"
	"testing"
	"time"

	"github.com/jeisenman/q2_bench/domain"
)

func TestOmissionUpdates(t *testing.T) {
	t.Parallel()
	values, err := UpdateOmissionValues([]string{"d2p"}, "add subscriber and CMM")
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(values, []string{"d2p", "subscriber", "cmm"}) {
		t.Fatalf("values = %#v", values)
	}
	values, err = UpdateOmissionValues(values, "remove D2P and subscriber")
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(values, []string{"cmm"}) {
		t.Fatalf("values = %#v", values)
	}
}

func TestEventBusHistoricalOmissionIsOptIn(t *testing.T) {
	t.Parallel()
	if containsOmission(DefaultOmissions(), OmitEventBusHistorical) {
		t.Fatal("event-bus omission must remain opt-in")
	}

	config, err := NewReportConfig([]string{"event_bus_to_payloads_historical"})
	if err != nil {
		t.Fatal(err)
	}
	failure := AirflowFailure{
		Region: CA02, DAGID: "event_bus_to_payloads_historical",
		TaskID: "check_for_subscriber_client_errors",
	}
	if got := config.ConfiguredOmissionGroup(failure); got != OmitEventBusHistorical {
		t.Fatalf("ConfiguredOmissionGroup() = %q, want %q", got, OmitEventBusHistorical)
	}

	values, err := UpdateOmissionValues(
		[]string{"subscriber"},
		"add event_bus_to_payloads_historical",
	)
	if err != nil {
		t.Fatal(err)
	}
	want := []string{"subscriber", "event_bus_to_payloads_historical"}
	if !reflect.DeepEqual(values, want) {
		t.Fatalf("values = %#v, want %#v", values, want)
	}

	codes := config.OmissionCodes([]AirflowFailure{failure})
	if !reflect.DeepEqual(codes, []string{"event_bus_to_payloads_historical"}) {
		t.Fatalf("OmissionCodes() = %#v", codes)
	}
}

func TestClientIdentitiesTrustOnlyReviewedStatuses(t *testing.T) {
	t.Parallel()
	results := []domain.AgentResult{{
		Attributes: domain.Attributes{
			{Name: "identifier_value", Value: "client"},
			{Name: "status", Value: "unique"},
			{Name: "client_name", Value: "Example Bank"},
		},
	}}
	if got := ClientIdentities(results)["client"].Name; got != "Example Bank" {
		t.Fatalf("name = %q", got)
	}
}

func TestClientIDsAndLabels(t *testing.T) {
	t.Parallel()
	const clientID = "11111111-1111-4111-8111-111111111111"
	failure := AirflowFailure{
		Region: CA02, DAGID: "l3-main-" + clientID, RunID: "run",
		TaskID:  "market_insights_3.run",
		StartAt: time.Now(), EndAt: time.Now(), TryNumber: 1,
	}
	if got := ClientIDs(failure); !reflect.DeepEqual(got, []string{clientID}) {
		t.Fatalf("ClientIDs() = %#v", got)
	}
	if got := JobLabel(failure.TaskID); got != "MI3" {
		t.Fatalf("JobLabel() = %q", got)
	}
}

func TestFailureSubjectPreservesCompleteClientUUID(t *testing.T) {
	t.Parallel()
	const clientID = "11111111-1111-4111-8111-111111111111"
	failure := AirflowFailure{
		Region: US01, DAGID: "l3-main-" + clientID, RunID: "run",
		TaskID: "task", StartAt: time.Now(), EndAt: time.Now(), TryNumber: 1,
	}
	identities := map[string]ClientIdentity{
		clientID: {ClientID: clientID, Name: "Example Bank", Status: "reviewed"},
	}

	got := FailureSubject(failure, identities)
	want := "Example Bank (" + clientID + ")"
	if got != want {
		t.Fatalf("FailureSubject() = %q, want %q", got, want)
	}
}

func TestFailureSubjectPreservesCompleteUnresolvedUUID(t *testing.T) {
	t.Parallel()
	const clientID = "22222222-2222-4222-8222-222222222222"
	failure := AirflowFailure{
		Region: CA02, DAGID: "l3-main-" + clientID, RunID: "run",
		TaskID: "task", StartAt: time.Now(), EndAt: time.Now(), TryNumber: 1,
	}

	got := FailureSubject(failure, nil)
	want := "Unresolved client (" + clientID + ")"
	if got != want {
		t.Fatalf("FailureSubject() = %q, want %q", got, want)
	}
}

func TestEventCountUsesLargestEvidenceCount(t *testing.T) {
	t.Parallel()
	count := EventCount(FailureDiagnosis{
		Evidence: []string{"12 missing opportunity snapshots", "8 unique events"},
	}, "")
	if count == nil || *count != 12 {
		t.Fatalf("count = %v", count)
	}
}
