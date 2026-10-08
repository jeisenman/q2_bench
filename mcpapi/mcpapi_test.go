package mcpapi

import (
	"context"
	"reflect"
	"sort"
	"testing"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func TestRemoteDataToolParity(t *testing.T) {
	t.Parallel()
	server := mcp.NewServer(&mcp.Implementation{Name: "test", Version: "1"}, nil)
	registerRemoteData(server)
	serverTransport, clientTransport := mcp.NewInMemoryTransports()
	if _, err := server.Connect(context.Background(), serverTransport, nil); err != nil {
		t.Fatal(err)
	}
	client := mcp.NewClient(&mcp.Implementation{Name: "test-client", Version: "1"}, nil)
	session, err := client.Connect(context.Background(), clientTransport, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer session.Close()
	result, err := session.ListTools(context.Background(), nil)
	if err != nil {
		t.Fatal(err)
	}
	names := make([]string, len(result.Tools))
	for index, tool := range result.Tools {
		names[index] = tool.Name
	}
	sort.Strings(names)
	expected := []string{
		"list_remote_data_targets",
		"make_adls_notebook",
		"make_databricks_notebook",
		"make_snowflake_notebook",
		"query_job_evidence",
		"query_oms",
		"run_databricks_notebook",
		"upload_databricks_integration_branch",
	}
	if !reflect.DeepEqual(names, expected) {
		t.Fatalf("tools = %#v", names)
	}
}

func TestWarehouseToolParity(t *testing.T) {
	t.Parallel()
	server := mcp.NewServer(&mcp.Implementation{Name: "test", Version: "1"}, nil)
	registerWarehouse(server)
	serverTransport, clientTransport := mcp.NewInMemoryTransports()
	if _, err := server.Connect(context.Background(), serverTransport, nil); err != nil {
		t.Fatal(err)
	}
	client := mcp.NewClient(&mcp.Implementation{Name: "test-client", Version: "1"}, nil)
	session, err := client.Connect(context.Background(), clientTransport, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer session.Close()
	result, err := session.ListTools(context.Background(), nil)
	if err != nil {
		t.Fatal(err)
	}
	names := make([]string, len(result.Tools))
	for index, tool := range result.Tools {
		names[index] = tool.Name
	}
	sort.Strings(names)
	expected := []string{"count_cortex_tokens", "run_cortex_complete"}
	if !reflect.DeepEqual(names, expected) {
		t.Fatalf("tools = %#v", names)
	}
}

func TestUpdateOmissionsPersistsValidatedValues(t *testing.T) {
	t.Parallel()
	api := &prodSupportAPI{omissionsPath: t.TempDir() + "/omissions.json"}
	if err := api.writeOmissions([]string{"d2p", "subscriber"}); err != nil {
		t.Fatal(err)
	}
	_, output, err := api.updateOmissions(
		context.Background(),
		nil,
		omissionUpdateInput{Direction: "remove d2p"},
	)
	if err != nil {
		t.Fatal(err)
	}
	values, ok := output["data_internal_omissions"].([]string)
	if !ok || !reflect.DeepEqual(values, []string{"subscriber"}) {
		t.Fatalf("output = %#v", output)
	}
	persisted, err := api.readOmissions()
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(persisted, values) {
		t.Fatalf("persisted = %#v", persisted)
	}
}

func TestFollowUpRequiresProductionMode(t *testing.T) {
	t.Setenv("PROD_SUPPORT_SOURCE", "replay")
	api := &prodSupportAPI{}
	_, _, err := api.executeFollowUp(context.Background(), nil, followUpInput{})
	if err == nil {
		t.Fatal("expected production mode requirement")
	}
}
