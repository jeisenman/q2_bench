package projects

import "testing"

func TestProjectTargetsAndFreshValues(t *testing.T) {
	for _, id := range []string{"di-pipelines", "radar"} {
		p, err := Get(id)
		if err != nil || p.ValidationPlatform != "ra" || p.WorkspaceID != "7628572648057993" || len(p.EnvironmentIDs) != 1 || p.PredictionReady {
			t.Fatalf("invalid target %+v %v", p, err)
		}
	}
	values := All()
	values[0].Repositories[0].Name = "edited"
	if err := Allows("di-pipelines", "di-pipelines"); err != nil {
		t.Fatal("mutable registry escaped")
	}
	if err := Allows("radar", "pl-application"); err == nil {
		t.Fatal("accepted foreign repository")
	}
	if _, err := Get("unknown"); err == nil {
		t.Fatal("accepted unknown project")
	}
}
