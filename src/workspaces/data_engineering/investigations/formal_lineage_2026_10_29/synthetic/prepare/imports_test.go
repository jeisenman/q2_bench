package main

import (
	"reflect"
	"testing"
)

func TestImportClosure(t *testing.T) {
	roots := []string{
		"utils/datascience_helpers", "jobs/data/delivery_to_promise/delivery_to_promise_data",
		"dataset_downloader/downloaders/spark_dataset_downloader_helpers",
		"dataset_downloader/downloaders/pandas_dataset_downloader_helpers", "runner/derived",
		"jobs/data/ra/utils/ra_job_template", "jobs/data/account_level_opportunities/account_level_opportunities_history_event_bus",
		"jobs/data/products/core_treasury_product_assumptions_data",
		"jobs/reports/delivery_to_promise/delivery_to_promise_report",
		"dataset_uploader/uploaders/spark_dataset_uploader", "jobs/dispatch/library_datafeeds_v2",
	}
	const prefix = "di-pipelines/ds-jobs/src/datascience_jobs/"
	files := map[string][]byte{prefix + "__init__.py": {}, prefix + "utils/__init__.py": {}}
	for _, root := range roots {
		files[prefix+root+".py"] = nil
	}
	files[prefix+roots[0]+".py"] = []byte("from . import sibling\nfrom di_pyjobs.client import (\n example,\n)\n")
	files[prefix+"utils/sibling.py"] = []byte("from .. import shared\n")
	files[prefix+"shared.py"] = nil
	files[prefix+"unused.py"] = nil
	files["di-pyjobs/di_pyjobs/__init__.py"] = nil
	files["di-pyjobs/di_pyjobs/client/__init__.py"] = nil
	files["di-pyjobs/di_pyjobs/client/example.py"] = nil
	got, err := importClosure(files)
	if err != nil {
		t.Fatal(err)
	}
	set := make(map[string]bool)
	for _, path := range got {
		set[path] = true
	}
	for _, path := range []string{prefix + "utils/sibling.py", prefix + "shared.py", "di-pyjobs/di_pyjobs/client/example.py", "di-pyjobs/di_pyjobs/__init__.py"} {
		if !set[path] {
			t.Errorf("missing reachable file %s", path)
		}
	}
	if set[prefix+"unused.py"] {
		t.Fatal("included unreachable source")
	}
	second, err := importClosure(files)
	if err != nil || !reflect.DeepEqual(got, second) {
		t.Fatal("archive ordering is not deterministic")
	}
	delete(files, prefix+roots[0]+".py")
	if _, err := importClosure(files); err == nil {
		t.Fatal("accepted missing root")
	}
}
