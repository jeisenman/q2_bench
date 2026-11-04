package dipipelines

import (
	"context"
	"fmt"
	"os/exec"
	"path"
	"regexp"
	"strconv"
	"strings"
	"time"
)

var commitRE = regexp.MustCompile(`^[0-9a-f]{40}$`)

func safePath(p string) bool {
	return p != "" && !strings.ContainsAny(p, "\x00\n\r:") && !strings.HasPrefix(p, "/") && p != ".." && !strings.HasPrefix(p, "../") && path.Clean(p) == p
}

// CompileGit reads an immutable source blob and binds compilation to its hash.
func CompileGit(ctx context.Context, root, commit, file, function string, tables []string) (Method, error) {
	b, err := readGit(ctx, root, commit, file)
	if err != nil {
		return Method{}, err
	}
	return Compile(b, Source{Commit: commit, Path: file, SHA256: hash(b)}, function, tables)
}

func readGit(ctx context.Context, root, commit, file string) ([]byte, error) {
	if root == "" || !commitRE.MatchString(commit) || !safePath(file) {
		return nil, fmt.Errorf("provide checkout root, full commit and safe relative source path")
	}
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	object := commit + ":" + file
	size, err := exec.CommandContext(ctx, "git", "-C", root, "cat-file", "-s", object).Output()
	if err != nil {
		return nil, fmt.Errorf("read source size: %w", err)
	}
	n, err := strconv.Atoi(strings.TrimSpace(string(size)))
	if err != nil || n < 0 || n > maxSource {
		return nil, fmt.Errorf("source must be at most 1 MiB")
	}
	b, err := exec.CommandContext(ctx, "git", "-C", root, "cat-file", "blob", object).Output()
	if err != nil {
		return nil, fmt.Errorf("read pinned source: %w", err)
	}
	return b, nil
}
