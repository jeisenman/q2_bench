package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

type eventMetadata struct {
	threadID string
	usage    map[string]int64
}

func executeOne(parent context.Context, root, codex, cwd string, timeout time.Duration, prompt []byte, policySHA string, t targetRecord) (r result, fatal error) {
	dir, e := resolve(root, t.Directory)
	if e != nil {
		return r, e
	}
	input, e := pinned(root, t.Files.Input)
	if e != nil {
		return r, e
	}
	prepared, e := pinned(root, t.Files.Prepared)
	if e != nil {
		return r, e
	}
	var payload map[string]json.RawMessage
	if e = json.Unmarshal(input, &payload); e != nil {
		return r, e
	}
	var preparedValue definition
	if e = json.Unmarshal(prepared, &preparedValue); e != nil {
		return r, e
	}
	if preparedValue.NodeID != t.NodeID {
		return r, fmt.Errorf("prepared definition identity mismatch: %s", t.NodeID)
	}
	var inputDefinition map[string]any
	var preparedDefinition map[string]any
	if e = json.Unmarshal(payload["definition"], &inputDefinition); e != nil {
		return r, e
	}
	if e = json.Unmarshal(prepared, &preparedDefinition); e != nil {
		return r, e
	}
	a, _ := json.Marshal(inputDefinition)
	b, _ := json.Marshal(preparedDefinition)
	if !bytes.Equal(a, b) {
		return r, fmt.Errorf("prepared definition differs from model input: %s", t.NodeID)
	}
	var preparation struct {
		Status string `json:"status"`
	}
	preparationBytes, err := pinned(root, t.Files.Preparation)
	if err != nil {
		return r, err
	}
	if err = json.Unmarshal(preparationBytes, &preparation); err != nil {
		return r, err
	}
	cleanupPending := preparation.Status == "pending_single_luna_cleanup"
	if cleanupPending && policySHA == "" {
		return r, fmt.Errorf("pending mixed cleanup requires the approved caller policy")
	}
	r = result{EffectivePromptSHA: digest(prompt), CallerPolicySHA: policySHA, CitationAttribution: "Article URLs resolved to supplied candidate chunks; chunk IDs are evidence candidates, not a claim-level audit.", NodeID: t.NodeID, Model: "gpt-6-luna", PromptVersion: "2.0.0", PromptSHA: promptSHA, Passes: 1, Status: "failed", Started: time.Now().UTC().Format(time.RFC3339Nano), InputSHA: t.Files.Input.SHA256, BeforeSHA: t.Files.Before.SHA256, PreparedSHA: t.Files.Prepared.SHA256, Cited: []citation{}}
	marker, e := os.OpenFile(filepath.Join(dir, "attempt.json"), os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if e != nil {
		return r, e
	}
	markerBytes, _ := json.MarshalIndent(r, "", "  ")
	_, e = marker.Write(append(markerBytes, '\n'))
	closeErr := marker.Close()
	if e != nil {
		return r, e
	}
	if closeErr != nil {
		return r, closeErr
	}
	finish := func(problem error) (result, error) {
		r.Completed = time.Now().UTC().Format(time.RFC3339Nano)
		if problem != nil {
			r.Error = problem.Error()
		}
		if e := writeJSON(filepath.Join(dir, "result.json"), r); e != nil {
			return r, e
		}
		return r, nil
	}
	ctx, cancel := context.WithTimeout(parent, timeout)
	defer cancel()
	rawPath := filepath.Join(dir, "model-output.txt")
	cmd := exec.CommandContext(ctx, codex, "exec", "--ignore-user-config", "--ephemeral", "--disable", "shell_tool", "--disable", "unified_exec", "--disable", "apps", "--disable", "remote_plugin", "--disable", "multi_agent", "--disable", "unbounded_connection_retries", "--skip-git-repo-check", "--sandbox", "read-only", "--cd", cwd, "--model", "gpt-6-luna", "--json", "--color", "never", "--output-last-message", rawPath, "-")
	modelRequest := string(prompt) + "\n\n## Supplied inputs\n\n" + string(input)
	r.ModelRequestSHA = digest([]byte(modelRequest))
	cmd.Stdin = strings.NewReader(modelRequest)
	stdout, e := cmd.StdoutPipe()
	if e != nil {
		return finish(e)
	}
	// Stderr can contain echoed request text; retain no raw process logs.
	var stderr boundedBuffer
	cmd.Stderr = &stderr
	if e = cmd.Start(); e != nil {
		r, saveErr := finish(fmt.Errorf("start Codex CLI: %w", e))
		if saveErr != nil {
			return r, saveErr
		}
		return r, e
	}
	metadata := eventMetadata{}
	scanner := bufio.NewScanner(stdout)
	scanner.Buffer(make([]byte, 4096), 2*1024*1024)
	for scanner.Scan() {
		var event struct {
			Type     string           `json:"type"`
			ThreadID string           `json:"thread_id"`
			Usage    map[string]int64 `json:"usage"`
		}
		if json.Unmarshal(scanner.Bytes(), &event) == nil {
			if event.Type == "thread.started" {
				metadata.threadID = event.ThreadID
			}
			if event.Type == "turn.completed" {
				metadata.usage = event.Usage
			}
		}
	}
	scanErr := scanner.Err()
	waitErr := cmd.Wait()
	r.ThreadID = metadata.threadID
	r.Usage = metadata.usage
	if waitErr != nil || scanErr != nil {
		reason := "Codex CLI failed; raw process logs were not retained"
		if ctx.Err() != nil {
			reason = "single edit pass interrupted or exceeded its deadline"
		}
		if scanErr != nil {
			reason = "Codex event stream exceeded its validated event bound"
		}
		r, saveErr := finish(fmt.Errorf("%s", reason))
		if saveErr != nil {
			return r, saveErr
		}
		return r, fmt.Errorf("%s: %s", t.NodeID, reason)
	}
	raw, e := os.ReadFile(rawPath)
	if e != nil {
		return finish(fmt.Errorf("missing single-pass model output: %w", e))
	}
	r.RawSHA = digest(raw)
	normalized, note := normalizeOutput(raw)
	r.Normalization = note
	draft, citations, e := validateDefinition(normalized, prepared, input, t.NodeID, cleanupPending)
	if e != nil {
		if errors.Is(e, errIdentityMismatch) {
			saved, saveErr := finish(e)
			if saveErr != nil {
				return saved, saveErr
			}
			return saved, e
		}
		return finish(e)
	}
	if e = os.WriteFile(filepath.Join(dir, "draft.json"), draft, 0600); e != nil {
		return finish(e)
	}
	r.NewArticleURLs = []string{}
	originalURLs := urls(string(prepared))
	newURLs := urls(string(draft))
	for _, c := range citations {
		if newURLs[c.URL] && !originalURLs[c.URL] {
			found := false
			for _, u := range r.NewArticleURLs {
				if u == c.URL {
					found = true
				}
			}
			if !found {
				r.NewArticleURLs = append(r.NewArticleURLs, c.URL)
			}
		}
	}
	r.DraftSHA = digest(draft)
	r.Cited = citations
	r.Status = "changed"
	var old, new definition
	_ = json.Unmarshal(prepared, &old)
	_ = json.Unmarshal(draft, &new)
	r.ModelChanged = old != new
	beforeBytes, err := pinned(root, t.Files.Before)
	if err != nil {
		return finish(err)
	}
	var original definition
	if err = json.Unmarshal(beforeBytes, &original); err != nil {
		return finish(err)
	}
	r.AuditCleanupChanged = original != old
	if original == new {
		r.Status = "unchanged"
	}
	return finish(nil)
}

type boundedBuffer struct{ data []byte }

func (b *boundedBuffer) Write(p []byte) (int, error) {
	if len(b.data) < 4096 {
		n := 4096 - len(b.data)
		if n > len(p) {
			n = len(p)
		}
		b.data = append(b.data, p[:n]...)
	}
	return len(p), nil
}
