package main

import (
	"archive/zip"
	"bytes"
	"context"
	"fmt"
	"io"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

func applicationArchive(parent string) ([]byte, error) {
	inputs := []struct {
		repository, commit string
		paths              []string
	}{
		{"di-pipelines", "fd9d9b74b53946150a01ed68fb87e4ffa4b7bc1e", []string{"ds-jobs/src/datascience_jobs"}},
		{"di-pyjobs", "32fbfc493d7f039def61c157e579caf24288db48", []string{"di_pyjobs"}},
		{"di-model-server", "7b73b3cdc2b44d29758e5733cf05e7e246dd717d", []string{"di-models/dimodels"}},
	}
	files := make(map[string][]byte)
	for _, input := range inputs {
		ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		args := append([]string{"-C", filepath.Join(parent, input.repository), "archive", "--format=zip", input.commit}, input.paths...)
		data, err := exec.CommandContext(ctx, "git", args...).Output()
		cancel()
		if err != nil {
			return nil, fmt.Errorf("archive %s: %w", input.repository, err)
		}
		reader, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
		if err != nil {
			return nil, err
		}
		for _, file := range reader.File {
			if !strings.HasSuffix(file.Name, ".py") {
				continue
			}
			if file.UncompressedSize64 > 2<<20 {
				return nil, fmt.Errorf("oversized Python source: %s", file.Name)
			}
			in, err := file.Open()
			if err != nil {
				return nil, err
			}
			contents, err := io.ReadAll(in)
			in.Close()
			if err != nil {
				return nil, err
			}
			files[input.repository+"/"+file.Name] = contents
		}
	}
	selected, err := importClosure(files)
	if err != nil {
		return nil, err
	}
	var output bytes.Buffer
	writer := zip.NewWriter(&output)
	for _, path := range selected {
		out, createErr := writer.Create(path)
		if createErr != nil {
			return nil, createErr
		}
		if _, err = out.Write(files[path]); err != nil {
			return nil, err
		}
	}
	if err := writer.Close(); err != nil {
		return nil, err
	}
	return output.Bytes(), nil
}
