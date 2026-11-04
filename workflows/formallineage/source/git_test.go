package source

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestPinnedGitAndBounds(t *testing.T) {
	root := t.TempDir()
	git := func(args ...string) string {
		t.Helper()
		b, err := exec.Command("git", append([]string{"-C", root}, args...)...).CombinedOutput()
		if err != nil {
			t.Fatalf("git %v: %s", args, b)
		}
		return strings.TrimSpace(string(b))
	}
	git("init", "--quiet")
	git("config", "user.name", "Test")
	git("config", "user.email", "test@example.invalid")
	if err := os.WriteFile(filepath.Join(root, "file.py"), []byte("original"), 0600); err != nil {
		t.Fatal(err)
	}
	git("add", "file.py")
	git("commit", "--quiet", "-m", "fixture")
	pin := git("rev-parse", "HEAD")
	if err := os.WriteFile(filepath.Join(root, "file.py"), []byte("modified"), 0600); err != nil {
		t.Fatal(err)
	}
	b, err := ReadGit(context.Background(), root, pin, "file.py", 8)
	if err != nil || string(b) != "original" {
		t.Fatalf("not pinned: %s %v", b, err)
	}
	files, err := ListGit(context.Background(), root, pin)
	if err != nil || len(files) != 1 || files[0] != "file.py" {
		t.Fatalf("inventory %v %v", files, err)
	}
	for _, bound := range []int{0, 7, (16 << 20) + 1} {
		if _, err := ReadGit(context.Background(), root, pin, "file.py", bound); err == nil {
			t.Fatalf("accepted bound %d", bound)
		}
	}
	for _, bad := range []string{"", ".", "../file.py", "/file.py", "a/../file.py", "a:b", "a\\b", "a\n"} {
		if ValidPath(bad) {
			t.Fatalf("accepted unsafe path %q", bad)
		}
	}
	if _, err := Receipt("HEAD", "file.py", b); err == nil {
		t.Fatal("accepted moving pin")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := ReadGit(ctx, root, pin, "file.py", 8); err == nil {
		t.Fatal("ignored cancellation")
	}
}
