package lineagecheck

import (
	"context"
	"fmt"
	"os/exec"
	"strings"
	"time"
)

// PRScope selects a checkout and the source branch refs under review.
type PRScope struct {
	Repository string
	Root       string
	BaseRef    string
	HeadRef    string
}

// CheckPR requires freshly pinned merge-base/head snapshots and changed-file coverage.
func CheckPR(ctx context.Context, base, head Snapshot, p Policy, scope PRScope) (Report, error) {
	if scope.Repository == "" || scope.Root == "" || scope.BaseRef == "" || scope.HeadRef == "" {
		return Report{}, fmt.Errorf("PR check requires repository name, checkout root, base ref, and head ref")
	}
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	resolve := func(ref string) (string, error) {
		b, err := exec.CommandContext(ctx, "git", "-C", scope.Root, "rev-parse", "--verify", "--end-of-options", ref+"^{commit}").Output()
		if err != nil {
			return "", fmt.Errorf("resolve PR ref: %w", err)
		}
		v := strings.TrimSpace(string(b))
		if !commitPattern.MatchString(v) {
			return "", fmt.Errorf("PR ref did not resolve to a full commit")
		}
		return v, nil
	}
	b, err := resolve(scope.BaseRef)
	if err != nil {
		return Report{}, err
	}
	h, err := resolve(scope.HeadRef)
	if err != nil {
		return Report{}, err
	}
	merge, err := exec.CommandContext(ctx, "git", "-C", scope.Root, "merge-base", b, h).Output()
	if err != nil {
		return Report{}, fmt.Errorf("find PR merge base: %w", err)
	}
	mergeBase := strings.TrimSpace(string(merge))
	commit := func(m Manifest, name string) string {
		for _, r := range m.Repositories {
			if r.Name == name {
				return r.Commit
			}
		}
		return ""
	}
	if commit(base.Manifest, scope.Repository) != mergeBase || commit(head.Manifest, scope.Repository) != h {
		return Report{}, fmt.Errorf("stale PR snapshots: base must pin merge base %s and head must pin %s", mergeBase, h)
	}
	for _, repo := range base.Manifest.Repositories {
		if repo.Name != scope.Repository && commit(head.Manifest, repo.Name) != repo.Commit {
			return Report{}, fmt.Errorf("PR comparison changes an unreviewed repository pin: %s", repo.Name)
		}
	}
	r, err := Compare(base, head, p)
	if err != nil {
		return Report{}, err
	}
	changed, err := exec.CommandContext(ctx, "git", "-C", scope.Root, "diff", "--name-only", "-z", mergeBase, h, "--").Output()
	if err != nil {
		return Report{}, fmt.Errorf("list PR changed files: %w", err)
	}
	covered := map[string]bool{}
	for _, m := range []Manifest{base.Manifest, head.Manifest} {
		for _, e := range allEvidence(m) {
			if e.Repository == scope.Repository {
				covered[e.Path] = true
			}
		}
	}
	for _, file := range strings.Split(string(changed), "\x00") {
		if file != "" && !covered[file] {
			r.add("unknown", "uncovered_pr_file", file, "changed file has no reviewed source contract in the selected lineage scope")
		}
	}
	r.finish()
	return r, nil
}

func allEvidence(m Manifest) []Evidence {
	items := []Evidence{}
	for _, d := range m.Datasets {
		items = append(items, d.Evidence...)
		if d.Schema != nil {
			items = append(items, d.Schema.Evidence)
		}
	}
	for _, j := range m.Jobs {
		items = append(items, j.Evidence...)
	}
	return items
}
