package ports

import (
	"strings"
	"testing"
)

func TestCortexAgentRequestQualifiedName(t *testing.T) {
	t.Parallel()
	request := CortexAgentRequest{
		AgentName: "DB.SCHEMA.AGENT", Version: "VERSION$2",
		RequestBody: `{"messages":[]}`,
	}
	if got := request.QualifiedName(); got != "DB.SCHEMA.AGENT!VERSION$2" {
		t.Fatalf("QualifiedName() = %q", got)
	}
}

func TestCortexAgentRequestAcceptsDefaultVersionAndJSON(t *testing.T) {
	t.Parallel()
	request := CortexAgentRequest{
		AgentName: "DB.SCHEMA.AGENT", RequestBody: `{"messages":[]}`,
	}
	if err := request.Validate(); err != nil {
		t.Fatal(err)
	}
}

func TestCortexAgentRequestRejectsStreaming(t *testing.T) {
	t.Parallel()
	request := CortexAgentRequest{
		AgentName: "DB.SCHEMA.AGENT", RequestBody: `{"stream":true}`,
	}
	if err := request.Validate(); err == nil || !strings.Contains(err.Error(), "stream must be false") {
		t.Fatalf("Validate() error = %v", err)
	}
}

func TestCortexAgentRequestRejectsInvalidJSON(t *testing.T) {
	t.Parallel()
	request := CortexAgentRequest{
		AgentName: "DB.SCHEMA.AGENT", RequestBody: `{`,
	}
	if err := request.Validate(); err == nil || !strings.Contains(err.Error(), "JSON object") {
		t.Fatalf("Validate() error = %v", err)
	}
}
