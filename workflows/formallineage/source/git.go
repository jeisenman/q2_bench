// Package source reads immutable, bounded source-repository evidence.
package source

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os/exec"
	"path"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/jeisenman/q2_bench/workflows/formallineage/model"
)

var commitPattern = regexp.MustCompile(`^[0-9a-f]{40}$`)

// ValidPath accepts normalized repository-relative paths without Git separators.
func ValidPath(value string) bool {
	return value != "" && value != "." && !strings.ContainsAny(value, "\x00\n\r:\\") && !strings.HasPrefix(value, "/") && value != ".." && !strings.HasPrefix(value, "../") && path.Clean(value) == value
}

// Receipt binds exact source bytes to a safe path and full commit.
func Receipt(commit, file string, content []byte) (model.Source, error) {
	if !commitPattern.MatchString(commit) || !ValidPath(file) {
		return model.Source{}, fmt.Errorf("source requires a full commit and safe relative path")
	}
	digest := sha256.Sum256(content)
	return model.Source{Commit: commit, Path: file, SHA256: hex.EncodeToString(digest[:])}, nil
}

// ReadGit reads one pinned blob without reading the checkout's working tree.
func ReadGit(ctx context.Context, root, commit, file string, limit int) ([]byte, error) {
	if root == "" || !commitPattern.MatchString(commit) || !ValidPath(file) || limit < 1 || limit > 16<<20 {
		return nil, fmt.Errorf("provide checkout root, full commit, safe relative path and a 1..16 MiB read bound")
	}
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	object := commit + ":" + file
	size, err := exec.CommandContext(ctx, "git", "-C", root, "cat-file", "-s", object).Output()
	if err != nil {
		return nil, fmt.Errorf("read source size: %w", err)
	}
	n, err := strconv.Atoi(strings.TrimSpace(string(size)))
	if err != nil || n < 0 || n > limit {
		return nil, fmt.Errorf("source %s exceeds the %d-byte bound", file, limit)
	}
	b, err := exec.CommandContext(ctx, "git", "-C", root, "cat-file", "blob", object).Output()
	if err != nil {
		return nil, fmt.Errorf("read pinned source: %w", err)
	}
	return b, nil
}

// ListGit inventories at most 20,000 tracked paths without checking files out.
func ListGit(ctx context.Context, root, commit string) ([]string, error) {
	if root == "" || !commitPattern.MatchString(commit) {
		return nil, fmt.Errorf("provide checkout root and full commit")
	}
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	var output boundedOutput
	cmd := exec.CommandContext(ctx, "git", "-C", root, "ls-tree", "-r", "--name-only", "-z", commit)
	cmd.Stdout = &output
	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("inventory pinned repository: %w", err)
	}
	paths := strings.Split(strings.TrimSuffix(output.value.String(), "\x00"), "\x00")
	if len(paths) == 1 && paths[0] == "" {
		return []string{}, nil
	}
	if len(paths) > 20000 {
		return nil, fmt.Errorf("repository exceeds 20000 tracked paths")
	}
	for _, file := range paths {
		if !ValidPath(file) {
			return nil, fmt.Errorf("repository contains an unsupported path")
		}
	}
	return paths, nil
}

type boundedOutput struct{ value strings.Builder }

func (b *boundedOutput) Write(p []byte) (int, error) {
	if b.value.Len()+len(p) > 4<<20 {
		return 0, fmt.Errorf("repository path inventory exceeds 4 MiB")
	}
	return b.value.Write(p)
}
