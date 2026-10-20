package snowflake

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/jeisenman/q2_bench/ports"
)

func TestAgentRunBindsVersionAndRequest(t *testing.T) {
	fakeDB := &fakeDatabase{value: `{"role":"assistant"}`}
	agent, err := NewAgent(cortexSettings(), &fakeSecrets{})
	if err != nil {
		t.Fatal(err)
	}
	agent.open = func(Settings, string) (database, error) {
		return fakeDB, nil
	}
	response, err := agent.Run(context.Background(), ports.CortexAgentRequest{
		AgentName: "DB.SCHEMA.AGENT", Version: "VERSION$2",
		RequestBody: `{"messages":[]}`, CreateThreadIfNotPresent: true,
	})
	if err != nil {
		t.Fatal(err)
	}
	if response.Response != `{"role":"assistant"}` || response.Recorded {
		t.Fatalf("response = %#v", response)
	}
	if fakeDB.statement != agentRunSQL {
		t.Fatalf("statement = %q", fakeDB.statement)
	}
	if len(fakeDB.arguments) != 3 ||
		fakeDB.arguments[0] != "DB.SCHEMA.AGENT!VERSION$2" ||
		fakeDB.arguments[1] != `{"messages":[]}` ||
		fakeDB.arguments[2] != true {
		t.Fatalf("arguments = %#v", fakeDB.arguments)
	}
	if !fakeDB.closed {
		t.Fatal("database was not closed")
	}
}

func TestAgentRunWrapsProviderFailure(t *testing.T) {
	fakeDB := &fakeDatabase{err: errors.New("network down")}
	agent, err := NewAgent(cortexSettings(), &fakeSecrets{})
	if err != nil {
		t.Fatal(err)
	}
	agent.open = func(Settings, string) (database, error) {
		return fakeDB, nil
	}
	_, err = agent.Run(context.Background(), ports.CortexAgentRequest{
		AgentName: "DB.SCHEMA.AGENT", RequestBody: `{"messages":[]}`,
	})
	if err == nil || !strings.Contains(err.Error(), "Cortex Agent dev run failed") {
		t.Fatalf("err = %v", err)
	}
}
