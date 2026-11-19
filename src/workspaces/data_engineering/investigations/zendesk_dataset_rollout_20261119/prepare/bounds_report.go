package main

import (
	"fmt"
	"os"
)

func writeBoundReport(output string, failures []preflightFailure, stats preparationStats) error {
	b, err := formatted(struct {
		Status     string             `json:"status"`
		Statistics preparationStats   `json:"statistics"`
		Failures   []preflightFailure `json:"failures"`
	}{"blocked_input_bounds", stats, failures})
	if err != nil {
		return err
	}
	path := output + ".bounds.json"
	f, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return err
	}
	_, writeErr := f.Write(b)
	closeErr := f.Close()
	if writeErr != nil {
		return writeErr
	}
	if closeErr != nil {
		return closeErr
	}
	return fmt.Errorf("input bounds blocked %d targets; evidence was not truncated; report %s", len(failures), path)
}
