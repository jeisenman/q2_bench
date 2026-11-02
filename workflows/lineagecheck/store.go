package lineagecheck

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

// DefaultStorePath contains independent snapshots and their publication index.
const DefaultStorePath = "var/lineage/local"

// Store retains immutable snapshots and atomically publishes their history index.
type Store struct{ Root string }

type storeIndex struct {
	Format string   `json:"format"`
	IDs    []string `json:"ids"`
}

// ReadFile reads a bounded lineage JSON document.
func ReadFile(path string) ([]byte, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	info, err := f.Stat()
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() || info.Size() > maxDocumentBytes {
		return nil, fmt.Errorf("lineage document %s must be a regular file under %d bytes", path, maxDocumentBytes)
	}
	b := make([]byte, info.Size()+1)
	n, err := f.ReadAt(b, 0)
	if err != nil && int64(n) != info.Size() {
		return nil, fmt.Errorf("read lineage document %s: %w", path, err)
	}
	if int64(n) != info.Size() {
		return nil, fmt.Errorf("lineage document changed while reading %s", path)
	}
	return b[:n], nil
}

// Load verifies a stored snapshot by ID; an empty ID selects the latest version.
func (s Store) Load(ctx context.Context, id string) (Snapshot, error) {
	if err := ctx.Err(); err != nil {
		return Snapshot{}, err
	}
	if s.Root == "" {
		return Snapshot{}, fmt.Errorf("lineage store root is required")
	}
	if id == "" {
		index, err := s.index()
		if err != nil {
			return Snapshot{}, err
		}
		if len(index.IDs) == 0 {
			return Snapshot{}, fmt.Errorf("lineage store has no published snapshots; run agentbench lineage build")
		}
		id = index.IDs[0]
	}
	if !validID(id) {
		return Snapshot{}, fmt.Errorf("snapshot ID must be a lowercase SHA256 digest")
	}
	b, err := ReadFile(filepath.Join(s.Root, "snapshots", id+".json"))
	if err != nil {
		return Snapshot{}, err
	}
	var snap Snapshot
	if err := Decode(b, &snap); err != nil {
		return Snapshot{}, err
	}
	if snap.ID != id {
		return Snapshot{}, fmt.Errorf("snapshot filename and ID disagree")
	}
	return snap, ValidateSnapshot(snap)
}

// Save publishes a new verified snapshot; concurrent writers fail immediately.
func (s Store) Save(ctx context.Context, snap Snapshot) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	if err := ValidateSnapshot(snap); err != nil {
		return err
	}
	if s.Root == "" {
		return fmt.Errorf("lineage store root is required")
	}
	if err := os.MkdirAll(filepath.Join(s.Root, "snapshots"), 0o755); err != nil {
		return err
	}
	lock := filepath.Join(s.Root, ".writer-lock")
	if err := os.Mkdir(lock, 0o700); err != nil {
		return fmt.Errorf("acquire lineage writer lock (another writer may be active): %w", err)
	}
	defer os.Remove(lock)
	index, err := s.index()
	if os.IsNotExist(err) {
		index = storeIndex{Format: snapshotFormat, IDs: []string{}}
	} else if err != nil {
		return err
	}
	path := filepath.Join(s.Root, "snapshots", snap.ID+".json")
	if contains(index.IDs, snap.ID) {
		_, err := s.Load(ctx, snap.ID)
		return err
	}
	if len(index.IDs) >= 10000 {
		return fmt.Errorf("lineage publication index exceeds 10000 snapshots; archive the store explicitly")
	}
	b, err := json.MarshalIndent(snap, "", "  ")
	if err != nil {
		return err
	}
	// An unindexed file can remain after interruption; validate before reusing it.
	if _, err := os.Stat(path); err == nil {
		if _, err := s.Load(ctx, snap.ID); err != nil {
			return err
		}
	} else if !os.IsNotExist(err) {
		return err
	} else if err := writeAtomic(path, b); err != nil {
		return err
	}
	index.IDs = append([]string{snap.ID}, index.IDs...)
	b, err = json.MarshalIndent(index, "", "  ")
	if err != nil {
		return err
	}
	return writeAtomic(filepath.Join(s.Root, "index.json"), b)
}

func (s Store) index() (storeIndex, error) {
	b, err := ReadFile(filepath.Join(s.Root, "index.json"))
	if err != nil {
		return storeIndex{}, err
	}
	var index storeIndex
	if err := Decode(b, &index); err != nil {
		return index, err
	}
	if index.Format != snapshotFormat || len(index.IDs) > 10000 {
		return index, fmt.Errorf("unsupported lineage publication index")
	}
	if err := unique(index.IDs); err != nil {
		return index, err
	}
	for _, id := range index.IDs {
		if !validID(id) {
			return index, fmt.Errorf("invalid lineage index snapshot ID")
		}
	}
	return index, nil
}

func validID(id string) bool {
	decoded, err := hex.DecodeString(id)
	return err == nil && len(decoded) == 32 && id == fmt.Sprintf("%x", decoded)
}

func writeAtomic(path string, b []byte) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	f, err := os.CreateTemp(filepath.Dir(path), ".lineage-*.json")
	if err != nil {
		return err
	}
	defer os.Remove(f.Name())
	if err := f.Chmod(0o644); err != nil {
		f.Close()
		return err
	}
	if _, err := f.Write(b); err != nil {
		f.Close()
		return err
	}
	if err := f.Sync(); err != nil {
		f.Close()
		return err
	}
	if err := f.Close(); err != nil {
		return err
	}
	return os.Rename(f.Name(), path)
}
