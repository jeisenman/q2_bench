package main

import (
	"bufio"
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
)

func digest(b []byte) string { h := sha256.Sum256(b); return hex.EncodeToString(h[:]) }
func read(path string) ([]byte, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read %s: %w", path, err)
	}
	return b, nil
}
func decode(b []byte, v any) error {
	d := json.NewDecoder(bytes.NewReader(b))
	if err := d.Decode(v); err != nil {
		return err
	}
	var extra any
	if err := d.Decode(&extra); err != io.EOF {
		return fmt.Errorf("JSON has trailing content")
	}
	return nil
}
func lines[T any](b []byte, id func(T) string) (map[string]T, map[string]json.RawMessage, error) {
	rows := map[string]T{}
	raw := map[string]json.RawMessage{}
	s := bufio.NewScanner(bytes.NewReader(b))
	s.Buffer(make([]byte, 4096), 16<<20)
	for s.Scan() {
		var row T
		if len(bytes.TrimSpace(s.Bytes())) == 0 {
			return nil, nil, fmt.Errorf("blank JSONL row")
		}
		if err := decode(s.Bytes(), &row); err != nil {
			return nil, nil, err
		}
		key := id(row)
		if key == "" {
			return nil, nil, fmt.Errorf("empty JSONL identity")
		}
		if _, ok := rows[key]; ok {
			return nil, nil, fmt.Errorf("duplicate JSONL identity %s", key)
		}
		rows[key] = row
		raw[key] = bytes.Clone(s.Bytes())
	}
	if err := s.Err(); err != nil {
		return nil, nil, err
	}
	return rows, raw, nil
}
func formatted(v any) ([]byte, error) {
	b, err := json.MarshalIndent(v, "", "  ")
	return append(b, '\n'), err
}
