package prodsupport

import "testing"

func TestSelectRetryCandidatesAcceptsRerunLanguage(t *testing.T) {
	t.Parallel()
	candidates := []RetryCandidate{{
		Number: 1,
		Region: US01,
		DAGID:  "dag",
		RunID:  "run",
		TaskID: "task",
		Label:  "client",
	}}

	selected, err := SelectRetryCandidates(
		"I give permission to re-run the dependency candidates",
		candidates,
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(selected) != 1 || selected[0].Identity() != candidates[0].Identity() {
		t.Fatalf("selected = %#v", selected)
	}
}
