package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"time"
)

const approvedPolicySHA = "0b0a9ac8e4ac0d0ab811bdb09955b613bb6d5d0c5c9d3db243a84efcca7acf4f"

const promptSHA = "6c876bc7a89ae483a6cfead9384fb37de14a60069c8e0852e20171616ae62226"

type filePin struct {
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
}
type targetRecord struct {
	NodeID     string `json:"node_id"`
	ArtifactID string `json:"artifact_id"`
	Directory  string `json:"directory"`
	Files      struct {
		Input       filePin `json:"input"`
		Prepared    filePin `json:"prepared"`
		Before      filePin `json:"before"`
		Preparation filePin `json:"preparation"`
	} `json:"files"`
}
type manifest struct {
	MaximumInputBytes      int `json:"maximum_input_bytes"`
	MaximumEstimatedTokens int `json:"maximum_estimated_input_tokens"`
	CallerPolicy           struct {
		Version string `json:"version"`
		Path    string `json:"path"`
		SHA256  string `json:"sha256"`
	} `json:"caller_policy"`
	SelectedCount int `json:"selected_count"`
	Prompt        struct {
		Version string `json:"version"`
		SHA256  string `json:"sha256"`
		Path    string `json:"path"`
	} `json:"prompt"`
	Targets []targetRecord `json:"targets"`
}
type result struct {
	ValidationContract     string           `json:"validation_contract,omitempty"`
	InitialValidationError string           `json:"initial_validation_error,omitempty"`
	InitialResultSHA       string           `json:"initial_result_sha256,omitempty"`
	ModelRequestSHA        string           `json:"model_request_sha256"`
	NewArticleURLs         []string         `json:"new_article_urls"`
	EffectivePromptSHA     string           `json:"effective_prompt_sha256"`
	CallerPolicySHA        string           `json:"caller_policy_sha256,omitempty"`
	CitationAttribution    string           `json:"citation_attribution"`
	ModelChanged           bool             `json:"model_changed"`
	AuditCleanupChanged    bool             `json:"audit_cleanup_changed"`
	NodeID                 string           `json:"node_id"`
	Model                  string           `json:"requested_model"`
	PromptVersion          string           `json:"prompt_version"`
	PromptSHA              string           `json:"prompt_sha256"`
	Passes                 int              `json:"edit_passes"`
	Status                 string           `json:"status"`
	Error                  string           `json:"error,omitempty"`
	Started                string           `json:"started_at"`
	Completed              string           `json:"completed_at"`
	InputSHA               string           `json:"input_sha256"`
	BeforeSHA              string           `json:"before_sha256"`
	PreparedSHA            string           `json:"prepared_sha256"`
	RawSHA                 string           `json:"raw_output_sha256,omitempty"`
	DraftSHA               string           `json:"draft_sha256,omitempty"`
	ThreadID               string           `json:"harness_thread_id,omitempty"`
	Usage                  map[string]int64 `json:"usage,omitempty"`
	Cited                  []citation       `json:"cited_chunks"`
	Normalization          string           `json:"normalization,omitempty"`
	Published              bool             `json:"published"`
	SMEApproved            bool             `json:"sme_approved"`
}
type citation struct {
	ArticleID string `json:"article_id"`
	ChunkID   string `json:"chunk_id"`
	URL       string `json:"url"`
}

func digest(b []byte) string { s := sha256.Sum256(b); return hex.EncodeToString(s[:]) }
func readJSON(path string, target any) error {
	b, e := os.ReadFile(path)
	if e != nil {
		return e
	}
	return json.Unmarshal(b, target)
}
func writeJSON(path string, value any) error {
	b, e := json.MarshalIndent(value, "", "  ")
	if e != nil {
		return e
	}
	return os.WriteFile(path, append(b, '\n'), 0600)
}
func resolve(root, relative string) (string, error) {
	if filepath.IsAbs(relative) {
		return "", errors.New("artifact paths must be relative")
	}
	p := filepath.Join(root, relative)
	rel, e := filepath.Rel(root, p)
	if e != nil || rel == ".." || (len(rel) > 3 && rel[:3] == ".."+string(os.PathSeparator)) {
		return "", errors.New("artifact path escapes frozen run")
	}
	return p, nil
}
func pinned(root string, pin filePin) ([]byte, error) {
	p, e := resolve(root, pin.Path)
	if e != nil {
		return nil, e
	}
	b, e := os.ReadFile(p)
	if e != nil {
		return nil, e
	}
	if digest(b) != pin.SHA256 {
		return nil, fmt.Errorf("input hash mismatch: %s", pin.Path)
	}
	return b, nil
}

func main() {
	if e := run(); e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(1)
	}
}
func run() error {
	runDir := flag.String("run", "", "frozen run directory")
	promptPath := flag.String("prompt", "", "frozen prompt release path")
	codex := flag.String("codex", "codex", "Codex CLI executable")
	cwd := flag.String("cwd", "", "empty working directory for isolated CLI sessions")
	parallel := flag.Int("parallel", 3, "concurrent Codex CLI harness calls; at least one")
	limit := flag.Int("limit", 553, "maximum previously unattempted targets to dispatch")
	timeout := flag.Duration("timeout", 5*time.Minute, "deadline for each single edit pass")
	revalidate := flag.Bool("revalidate-held", false, "recheck held raw outputs with corrected audit metadata/format guards; no model calls")
	dispatch := flag.Bool("execute", false, "dispatch the authorized single edit pass")
	flag.Parse()
	if *runDir == "" || *promptPath == "" || *cwd == "" || *parallel < 1 || *limit < 1 || *timeout <= 0 {
		return errors.New("run, prompt, cwd, positive parallel, limit and timeout are required")
	}
	root, e := filepath.Abs(*runDir)
	if e != nil {
		return e
	}
	var m manifest
	if e = readJSON(filepath.Join(root, "manifest.json"), &m); e != nil {
		return e
	}
	if m.MaximumInputBytes != 524288 || m.MaximumEstimatedTokens != 128000 {
		return errors.New("frozen input budget differs from verified Luna capacity plan")
	}
	if m.SelectedCount != 553 || len(m.Targets) != 553 || m.Prompt.Version != "2.0.0" || m.Prompt.SHA256 != promptSHA {
		return errors.New("frozen manifest scope or prompt mismatch")
	}
	prompt, e := os.ReadFile(*promptPath)
	if e != nil {
		return e
	}
	if digest(prompt) != promptSHA {
		return errors.New("prompt release hash mismatch")
	}
	policySHA := ""
	if m.CallerPolicy.Version != "" {
		if m.CallerPolicy.Version != "single-luna-audit-cleanup/1" || m.CallerPolicy.SHA256 != approvedPolicySHA {
			return errors.New("unsupported caller cleanup policy")
		}
		policy, err := pinned(root, filePin{Path: m.CallerPolicy.Path, SHA256: m.CallerPolicy.SHA256})
		if err != nil {
			return err
		}
		policySHA = m.CallerPolicy.SHA256
		prompt = append(append(prompt, []byte("\n\n## Explicit caller cleanup policy\n\n")...), policy...)
	}
	seen := map[string]bool{}
	pending := []targetRecord{}
	for _, t := range m.Targets {
		if seen[t.NodeID] || t.NodeID == "" || t.ArtifactID != digest([]byte(t.NodeID)) {
			return errors.New("duplicate or invalid frozen identity")
		}
		seen[t.NodeID] = true
		inputBytes, inputErr := pinned(root, t.Files.Input)
		if inputErr != nil {
			return inputErr
		}
		if len(inputBytes) > m.MaximumInputBytes || (len(inputBytes)+len(prompt)+2)/3 > m.MaximumEstimatedTokens {
			return fmt.Errorf("input exceeds verified model budget: %s", t.NodeID)
		}
		for _, p := range []filePin{t.Files.Input, t.Files.Prepared, t.Files.Before, t.Files.Preparation} {
			if _, e = pinned(root, p); e != nil {
				return e
			}
		}
		dir, e := resolve(root, t.Directory)
		if e != nil {
			return e
		}
		var previous result
		if e = readJSON(filepath.Join(dir, "result.json"), &previous); e == nil {
			if previous.NodeID != t.NodeID || previous.Passes != 1 || (previous.Status != "changed" && previous.Status != "unchanged" && previous.Status != "failed") {
				return fmt.Errorf("prior failed or mismatched result blocks dispatch: %s", t.NodeID)
			}
			continue
		} else if !os.IsNotExist(e) {
			return e
		}
		if _, e = os.Stat(filepath.Join(dir, "attempt.json")); e == nil {
			return fmt.Errorf("prior unresolved attempt blocks a second pass: %s", t.NodeID)
		} else if !os.IsNotExist(e) {
			return e
		}
		pending = append(pending, t)
	}
	fmt.Printf("Validated %d selected identities; %d completed; %d pending.\n", len(m.Targets), len(m.Targets)-len(pending), len(pending))
	if *revalidate {
		if *dispatch {
			return errors.New("revalidation cannot dispatch model calls")
		}
		return revalidateHeld(root, m)
	}
	if !*dispatch {
		return nil
	}
	if e = os.MkdirAll(*cwd, 0700); e != nil {
		return e
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	queue := make(chan targetRecord)
	fail := make(chan error, 1)
	var wg sync.WaitGroup
	var completed atomic.Int64
	for i := 0; i < *parallel; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for t := range queue {
				if ctx.Err() != nil {
					return
				}
				r, e := executeOne(ctx, root, *codex, *cwd, *timeout, prompt, policySHA, t)
				if e != nil {
					select {
					case fail <- e:
					default:
					}
					cancel()
					return
				}
				n := completed.Add(1)
				fmt.Printf("Completed %d: %s (%s)\n", n, t.NodeID, r.Status)
			}
		}()
	}
send:
	for i, t := range pending {
		if i >= *limit {
			break
		}
		select {
		case queue <- t:
		case <-ctx.Done():
			break send
		}
	}
	close(queue)
	wg.Wait()
	select {
	case e := <-fail:
		return e
	default:
		return nil
	}
}
