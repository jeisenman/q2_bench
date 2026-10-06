package main

import (
	"bytes"
	"context"
	"os"
	"testing"
)

func TestVersionCommand(t *testing.T) {
	original := os.Stdout
	reader, writer, err := os.Pipe()
	if err != nil {
		t.Fatal(err)
	}
	os.Stdout = writer
	defer func() { os.Stdout = original }()
	if err := run(context.Background(), []string{"version"}); err != nil {
		t.Fatal(err)
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	var output bytes.Buffer
	if _, err := output.ReadFrom(reader); err != nil {
		t.Fatal(err)
	}
	if output.String() != version+"\n" {
		t.Fatalf("output = %q", output.String())
	}
}

func TestRemovedPythonCommandFailsClearly(t *testing.T) {
	t.Parallel()
	err := run(context.Background(), []string{"capture-prod-support"})
	if err == nil || err.Error() != `unsupported agentbench command "capture-prod-support"` {
		t.Fatalf("error = %v", err)
	}
}
