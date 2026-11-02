package formalmethod

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestMetadataInterfaceUsesPinnedVersionsAndLiteralSchemas(t *testing.T) {
	root := t.TempDir()
	sources := map[string]string{
		"ds-jobs/src/datascience_jobs/jobs/test_job.py": `from datascience_jobs.meta_data.test_metadata import ExampleMetaData
SOURCE = [ExampleMetaData(major_version=1, dates_to_download=DatesToDownload.RUN_DATE)]
OUTPUT = ExampleMetaData(major_version=ExampleMetaData.LATEST_MAJOR_VERSION, minor_version=ExampleMetaData.LATEST_MINOR_VERSION, dates_to_download=DatesToDownload.RUN_DATE)
class ExampleJob:
    @property
    def source_meta_data(self):
        return SOURCE
    @property
    def output_meta_data(self):
        return OUTPUT
`,
		"ds-jobs/src/datascience_jobs/meta_data/test_metadata.py": `class ExampleMetaData:
    LATEST_MAJOR_VERSION: int = 1
    LATEST_MINOR_VERSION: int = 2
    PATH_STAGE = 'Derived'
    PATH_PROVIDER = 'Example'
    PATH_GROUP = 'Group'
    DATASET_NAME = 'ExampleData'
    def __init__(self, data_source_name='InputAlias'):
        pass
    @property
    def _schema_v1(self):
        return StructType([StructField('Id', StringType(), True)])
`,
	}
	for path, content := range sources {
		absolute := filepath.Join(root, path)
		if err := os.MkdirAll(filepath.Dir(absolute), 0700); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(absolute, []byte(content), 0600); err != nil {
			t.Fatal(err)
		}
	}
	git := func(args ...string) string {
		t.Helper()
		out, err := exec.Command("git", append([]string{"-C", root}, args...)...).CombinedOutput()
		if err != nil {
			t.Fatalf("git: %s %v", out, err)
		}
		return strings.TrimSpace(string(out))
	}
	git("init", "-q")
	git("config", "user.name", "Fixture")
	git("config", "user.email", "fixture@example.invalid")
	git("add", ".")
	git("commit", "-qm", "metadata fixture")
	commit := git("rev-parse", "HEAD")
	result, err := DescribeJob(context.Background(), root, commit, "datascience_jobs.jobs.test_job.ExampleJob")
	if err != nil {
		t.Fatal(err)
	}
	if len(result.Inputs) != 1 || len(result.Outputs) != 1 || result.Inputs[0].Minor != nil || result.Outputs[0].Minor == nil || *result.Outputs[0].Minor != 2 {
		t.Fatalf("metadata=%+v", result)
	}
	if result.Outputs[0].Name != "InputAlias" || len(result.Outputs[0].Fields) != 1 || result.Outputs[0].Fields[0].Name != "Id" || result.PredictionReady || len(result.Unresolved) != 1 {
		t.Fatalf("port=%+v unresolved=%v", result.Outputs, result.Unresolved)
	}
}

func TestMetadataVersionCannotBorrowAnotherClassesConstants(t *testing.T) {
	b := []byte("class First:\n    LATEST_MAJOR_VERSION = 1\n")
	tree, err := parse(b)
	if err != nil {
		t.Fatal(err)
	}
	defer tree.Close()
	owner := &parsedModule{content: b, tree: tree}
	callerSource := []byte("version = Other.LATEST_MAJOR_VERSION\n")
	callTree, err := parse(callerSource)
	if err != nil {
		t.Fatal(err)
	}
	defer callTree.Close()
	expression := callTree.RootNode().NamedChild(0).NamedChild(0).ChildByFieldName("right")
	caller := &parsedModule{content: callerSource, imports: map[string]string{"Other": "metadata.Other"}}
	if _, err := metadataNumber(caller, expression, owner, classNode(owner, "First"), "metadata.First"); err == nil {
		t.Fatal("borrowed version accepted")
	}
}
