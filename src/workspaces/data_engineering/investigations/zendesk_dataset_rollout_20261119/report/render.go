package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

func markdown(text string) string {
	text = strings.ReplaceAll(text, "\\", "\\\\")
	text = strings.ReplaceAll(text, "|", "\\|")
	text = strings.ReplaceAll(text, "`", "\\`")
	text = strings.ReplaceAll(text, "\n", " ")
	text = strings.ReplaceAll(text, "\r", " ")
	return text
}
func artifactLink(root, out, name, relative string) string {
	if relative == "" {
		return "—"
	}
	p := filepath.Join(root, filepath.FromSlash(relative))
	rel, err := filepath.Rel(out, p)
	if err != nil {
		return "—"
	}
	return "[" + name + "](<" + filepath.ToSlash(rel) + ">)"
}
func writeReport(root, out string, s summary) (err error) {
	files := map[string][]byte{}
	b, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return err
	}
	files["summary.json"] = append(b, '\n')
	readme := strings.Builder{}
	fmt.Fprintf(&readme, "# Offline dataset draft artifact report\n\nAccounted for %d selected dataset identities. Complete dispatch snapshot: **%t**.\n\n", s.Selected, s.Complete)
	fmt.Fprint(&readme, "These are local machine drafts. **Published: false. SME approved: false.** Failed and unresolved outputs remain held. This report does not change or accept definitions.\n\n")
	fmt.Fprintln(&readme, "| Emitted state | Count |\n| --- | ---: |")
	for _, name := range []string{"changed", "unchanged", "failed", "pending", "unresolved_attempt"} {
		fmt.Fprintf(&readme, "| %s | %d |\n", name, s.Counts[name])
	}
	fmt.Fprintf(&readme, "\nModel changes among validated successful results: %d. Deterministic before-to-prepared audit changes across all targets: %d.\n\n", s.ModelChanged, s.AuditPrepared)
	fmt.Fprintf(&readme, "Source generation: `%s`. Corpus: `%s`, %d articles, %d chunks. Source and evidence file hashes are retained in [summary.json](summary.json).\n\n", s.Pins.Generation, s.Corpus.Snapshot, s.Corpus.Articles, s.Corpus.Chunks)
	fmt.Fprint(&readme, "Article URLs are matched to supplied candidate chunks. This does not prove exact per-claim support. Hash consistency does not prove semantic correctness, technical equivalence, completeness or runtime behavior. Failed raw outputs are not reconsidered.\n\n")
	fmt.Fprint(&readme, "No source/graph writes, model calls, retries, publication or approval were performed. Token usage totals in summary.json retain separate emitted categories.\n\n")
	for start := 0; start < len(s.Nodes); start += 80 {
		end := min(start+80, len(s.Nodes))
		name := fmt.Sprintf("datasets-%02d.md", start/80+1)
		fmt.Fprintf(&readme, "- [Datasets %d–%d](%s)\n", start+1, end, name)
		index := strings.Builder{}
		fmt.Fprintf(&index, "# Dataset artifacts %d–%d\n\nAll artifacts are offline drafts. Failed, pending and unresolved attempts are held.\n\n", start+1, end)
		fmt.Fprintln(&index, "| Exact dataset ID | State | Draft | Inputs | Emitted evidence / error |\n| --- | --- | --- | --- | --- |")
		for _, row := range s.Nodes[start:end] {
			draft := artifactLink(root, out, "draft (artifact-validated only)", row.Files["draft"])
			inputs := artifactLink(root, out, "before", row.Files["before"]) + " · " + artifactLink(root, out, "prepared", row.Files["prepared"]) + " · " + artifactLink(root, out, "target", row.Files["target"])
			evidence := artifactLink(root, out, "result", row.Files["result"]) + " · " + artifactLink(root, out, "raw", row.Files["raw"]) + " · " + artifactLink(root, out, "attempt", row.Files["attempt"])
			if row.Files["initial-result"] != "" {
				evidence += " · " + artifactLink(root, out, "initial result", row.Files["initial-result"]) + " · " + artifactLink(root, out, "artifact correction", row.Files["validation-v2"])
			}
			if row.Error != "" {
				evidence += " — " + markdown(row.Error)
			}
			state := row.Status
			if row.Held {
				state += " (held)"
			}
			fmt.Fprintf(&index, "| %s | %s | %s | %s | %s |\n", markdown(row.NodeID), state, draft, inputs, evidence)
		}
		files[name] = []byte(index.String())
	}
	files["README.md"] = []byte(readme.String())
	for name, contents := range files {
		if strings.HasSuffix(name, ".md") && strings.Count(string(contents), "\n") >= 400 {
			return fmt.Errorf("Markdown report exceeds source/document line limit")
		}
	}
	if err := os.Mkdir(out, 0700); err != nil {
		return err
	}
	defer func() {
		if err != nil {
			_ = os.RemoveAll(out)
		}
	}()
	for name, contents := range files {
		if err := os.WriteFile(filepath.Join(out, name), contents, 0600); err != nil {
			return err
		}
	}
	return nil
}
