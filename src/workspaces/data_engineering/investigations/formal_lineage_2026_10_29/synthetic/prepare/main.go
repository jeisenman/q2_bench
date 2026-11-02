// Command prepare packages source-pinned D2P synthetic notebooks for remote execution.
package main

import (
	"bytes"
	"compress/gzip"
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

type evidence struct {
	ID         string `json:"id"`
	Repository string `json:"repository"`
	Path       string `json:"path"`
	Commit     string `json:"commit"`
	SHA256     string `json:"sha256"`
}

func main() {
	if err := prepare(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func prepare() error {
	base := flag.String("base", "src/workspaces/data_engineering/investigations/formal_lineage_2026_10_29", "Investigation root")
	repositories := flag.String("repositories", "..", "Parent of pinned source repositories")
	output := flag.String("output", filepath.Join(os.TempDir(), "qtwo-d2p-synthetic", "notebook.py"), "Generated notebook artifact outside source checkout")
	mode := flag.String("mode", "ast", "ast, modules or imports-probe")
	stages := flag.String("stages", "", "Optional comma-separated fixture stages for bounded troubleshooting")
	historyMode := flag.String("history-mode", "account-union", "account-union or full History output")
	flag.Parse()
	if *historyMode != "account-union" && *historyMode != "full" {
		return fmt.Errorf("unsupported History mode: %s", *historyMode)
	}
	read := func(name string) ([]byte, error) { return os.ReadFile(filepath.Join(*base, name)) }
	receiptBytes, err := read("delivery-to-promise-sources.json")
	if err != nil {
		return err
	}
	var receipt struct {
		Evidence []evidence `json:"evidence"`
	}
	if err = json.Unmarshal(receiptBytes, &receipt); err != nil {
		return err
	}
	selected := strings.Fields("derived_job helpers spark_download_helpers pandas_download_helpers snapshot_runner ra_runner history_job treasury_assumptions_job report_job spark_uploader dispatch_job")
	wanted := make(map[string]bool)
	for _, id := range selected {
		wanted[id] = true
	}
	sources := make(map[string]map[string]string)
	for _, e := range receipt.Evidence {
		if !wanted[e.ID] {
			continue
		}
		ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		blob, commandErr := exec.CommandContext(ctx, "git", "-C", filepath.Join(*repositories, e.Repository), "show", e.Commit+":"+e.Path).Output()
		cancel()
		if commandErr != nil {
			return fmt.Errorf("read pinned source %s: %w", e.ID, commandErr)
		}
		sum := sha256.Sum256(blob)
		if hex.EncodeToString(sum[:]) != e.SHA256 {
			return fmt.Errorf("source digest mismatch: %s", e.ID)
		}
		sources[e.ID] = map[string]string{"text": string(blob), "sha256": e.SHA256, "commit": e.Commit, "path": e.Path}
	}
	if len(sources) != len(wanted) {
		return fmt.Errorf("expected %d source files; found %d", len(wanted), len(sources))
	}
	fixtures, err := read("synthetic/cases.json")
	if err != nil {
		return err
	}
	if *stages != "" {
		fixtures, err = filterCases(fixtures, *stages)
		if err != nil {
			return err
		}
	}
	golden, err := read("synthetic/golden-report.json")
	if err != nil {
		return err
	}
	var fixtureMeta struct {
		Synthetic bool              `json:"synthetic"`
		Cases     []json.RawMessage `json:"cases"`
	}
	if err = json.Unmarshal(fixtures, &fixtureMeta); err != nil {
		return err
	}
	if !fixtureMeta.Synthetic || len(fixtureMeta.Cases) < 1 {
		return fmt.Errorf("expected nonempty synthetic fixtures")
	}
	values := map[string]any{"fixtures": json.RawMessage(fixtures), "golden": json.RawMessage(golden), "sources": sources, "history_mode": *historyMode}
	if *mode != "ast" {
		if *mode != "modules" && *mode != "imports-probe" {
			return fmt.Errorf("unsupported mode: %s", *mode)
		}
		archive, archiveErr := applicationArchive(*repositories)
		if archiveErr != nil {
			return archiveErr
		}
		values["application_archive"] = base64.StdEncoding.EncodeToString(archive)
	}
	payload, err := json.Marshal(values)
	if err != nil {
		return err
	}
	var compressed bytes.Buffer
	writer, err := gzip.NewWriterLevel(&compressed, gzip.BestCompression)
	if err != nil {
		return err
	}
	if _, err = writer.Write(payload); err != nil {
		return err
	}
	if err = writer.Close(); err != nil {
		return err
	}
	code := "# Databricks notebook source\nimport base64, gzip, json\nPAYLOAD = json.loads(gzip.decompress(base64.b64decode(" + fmt.Sprintf("%q", base64.StdEncoding.EncodeToString(compressed.Bytes())) + ")))\n"
	files := []string{"bootstrap.py", "stages_upstream.py", "stages.py", "jobs.py", "runner.py"}
	if *mode == "modules" {
		files = []string{"module_environment.py", "bootstrap_modules.py", "stages_upstream.py", "history_modules.py", "stages.py", "jobs.py", "jobs_modules.py", "runner.py"}
	}
	if *mode == "imports-probe" {
		files = []string{"module_environment.py"}
	}
	for _, name := range files {
		part, readErr := read("synthetic/" + name)
		if readErr != nil {
			return readErr
		}
		code += "\n# COMMAND ----------\n" + string(part) + "\n"
	}
	if *mode == "imports-probe" {
		code += "\ndbutils.notebook.exit(json.dumps({'status':'imports_ready','modules':MODULE_PROVENANCE}, sort_keys=True))\n"
	}
	// Future imports must occur at the beginning of the combined Python module.
	code = strings.ReplaceAll(code, "from __future__ import annotations\n", "")
	code = "from __future__ import annotations\n" + code
	// Leave room for the remote-data wrapper below its 1,000,000-byte limit.
	if len(code) > 999000 {
		return fmt.Errorf("packaged notebook exceeds remote-data SOURCE limit")
	}
	if err = os.MkdirAll(filepath.Dir(*output), 0700); err != nil {
		return err
	}
	if err = os.WriteFile(*output, []byte(code), 0600); err != nil {
		return err
	}
	sum := sha256.Sum256([]byte(code))
	return json.NewEncoder(os.Stdout).Encode(map[string]any{"notebook": *output, "source_sha256": hex.EncodeToString(sum[:]), "cases": len(fixtureMeta.Cases), "pinned_sources": len(sources)})
}
