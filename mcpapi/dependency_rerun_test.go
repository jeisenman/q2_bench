package mcpapi

import (
	"strings"
	"testing"

	"github.com/jeisenman/q2_bench/workflows/prodsupport"
)

func TestDependencyPlanIDIsOrderIndependent(t *testing.T) {
	t.Parallel()
	left := []prodsupport.RetryTaskReference{
		{
			Region: prodsupport.US01,
			DAGID:  "dag",
			RunID:  "run-2",
			TaskID: "task-b",
		},
		{
			Region: prodsupport.US01,
			DAGID:  "dag",
			RunID:  "run-1",
			TaskID: "task-a",
		},
	}
	right := []prodsupport.RetryTaskReference{left[1], left[0]}

	if dependencyPlanID(left) != dependencyPlanID(right) {
		t.Fatal("plan ID changed with task ordering")
	}
}

func TestValidateRerunCandidatesRejectsDuplicateIdentity(t *testing.T) {
	t.Parallel()
	candidates := []prodsupport.RetryCandidate{
		{
			Number: 1,
			Region: prodsupport.US01,
			DAGID:  "dag",
			RunID:  "run",
			TaskID: "task",
			Label:  "client",
		},
		{
			Number: 2,
			Region: prodsupport.US01,
			DAGID:  "dag",
			RunID:  "run",
			TaskID: "task",
			Label:  "client",
		},
	}

	err := validateRerunCandidates(candidates)
	if err == nil || !strings.Contains(err.Error(), "duplicate") {
		t.Fatalf("error = %v", err)
	}
}

func TestRequireProductionDependencyRerun(t *testing.T) {
	t.Setenv("PROD_SUPPORT_SOURCE", "replay")
	err := requireProductionFollowUp()
	if err == nil || !strings.Contains(err.Error(), "production") {
		t.Fatalf("error = %v", err)
	}
}

func TestDependencyRerunDirectionRequiresDependencyAndRerun(t *testing.T) {
	t.Parallel()
	if !dependencyRerunRequested(
		"Later day runs depended on the past day; re-run dependent datasets",
	) {
		t.Fatal("expected changed-dataset direction to select dependency mode")
	}
	if dependencyRerunRequested("retry failed tasks") {
		t.Fatal("ordinary retry unexpectedly selected dependency mode")
	}
}
