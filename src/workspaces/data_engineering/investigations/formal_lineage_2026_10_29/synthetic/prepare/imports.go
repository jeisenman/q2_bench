package main

import (
	"fmt"
	"regexp"
	"sort"
	"strings"
)

var fromImport = regexp.MustCompile(`(?m)^\s*from\s+([.\w]+)\s+import\s+(\([^)]*\)|[^\n]+)`)
var plainImport = regexp.MustCompile(`(?m)^\s*import\s+([^\n]+)`)

func importClosure(files map[string][]byte) ([]string, error) {
	index := make(map[string]string)
	packages := make(map[string]bool)
	for path := range files {
		module := path
		for _, prefix := range []string{"di-pipelines/ds-jobs/src/", "di-pyjobs/", "di-model-server/di-models/"} {
			if strings.HasPrefix(path, prefix) {
				module = strings.TrimPrefix(path, prefix)
				break
			}
		}
		module = strings.ReplaceAll(strings.TrimSuffix(module, ".py"), "/", ".")
		if strings.HasSuffix(module, ".__init__") {
			module = strings.TrimSuffix(module, ".__init__")
			packages[module] = true
		}
		index[module] = path
	}
	queue := []string{
		"datascience_jobs.utils.datascience_helpers",
		"datascience_jobs.jobs.data.delivery_to_promise.delivery_to_promise_data",
		"datascience_jobs.dataset_downloader.downloaders.spark_dataset_downloader_helpers",
		"datascience_jobs.dataset_downloader.downloaders.pandas_dataset_downloader_helpers",
		"datascience_jobs.runner.derived", "datascience_jobs.jobs.data.ra.utils.ra_job_template",
		"datascience_jobs.jobs.data.account_level_opportunities.account_level_opportunities_history_event_bus",
		"datascience_jobs.jobs.data.products.core_treasury_product_assumptions_data",
		"datascience_jobs.jobs.reports.delivery_to_promise.delivery_to_promise_report",
		"datascience_jobs.dataset_uploader.uploaders.spark_dataset_uploader",
		"datascience_jobs.jobs.dispatch.library_datafeeds_v2",
	}
	for _, module := range queue {
		if index[module] == "" {
			return nil, fmt.Errorf("missing root module %s", module)
		}
	}
	seen := make(map[string]bool)
	add := func(module string) {
		if index[module] != "" {
			queue = append(queue, module)
		}
		for parts := strings.Split(module, "."); len(parts) > 1; {
			parts = parts[:len(parts)-1]
			parent := strings.Join(parts, ".")
			if index[parent] != "" {
				queue = append(queue, parent)
			}
		}
	}
	for len(queue) > 0 {
		module := queue[0]
		queue = queue[1:]
		if seen[module] {
			continue
		}
		seen[module] = true
		add(module)
		text := string(files[index[module]])
		for _, match := range fromImport.FindAllStringSubmatch(text, -1) {
			base := match[1]
			if strings.HasPrefix(base, ".") {
				dots := len(base) - len(strings.TrimLeft(base, "."))
				parts := strings.Split(module, ".")
				if !packages[module] {
					parts = parts[:len(parts)-1]
				}
				if dots > len(parts) {
					return nil, fmt.Errorf("invalid relative import in %s", module)
				}
				parts = parts[:len(parts)-dots+1]
				base = strings.Join(parts, ".") + "." + strings.TrimLeft(base, ".")
				base = strings.TrimSuffix(base, ".")
			}
			add(base)
			items := strings.NewReplacer("(", "", ")", "", "\n", " ").Replace(match[2])
			for _, item := range strings.Split(items, ",") {
				words := strings.Fields(item)
				if len(words) > 0 {
					add(base + "." + words[0])
				}
			}
		}
		for _, match := range plainImport.FindAllStringSubmatch(text, -1) {
			for _, item := range strings.Split(match[1], ",") {
				words := strings.Fields(item)
				if len(words) > 0 {
					add(words[0])
				}
			}
		}
	}
	paths := make([]string, 0, len(seen))
	for module := range seen {
		paths = append(paths, index[module])
	}
	sort.Strings(paths)
	return paths, nil
}
