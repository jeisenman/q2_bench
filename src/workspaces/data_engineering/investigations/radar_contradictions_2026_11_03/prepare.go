// Prepare the source-pinned synthetic RADAR contradiction campaign.
package main

import (
	"bytes"
	"compress/gzip"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"math"
	"math/rand/v2"
	"os"
	"path/filepath"
	"strings"

	"github.com/jeisenman/q2_bench/workflows/formallineage/model"
	"github.com/jeisenman/q2_bench/workflows/formallineage/source"
)

type pinned struct {
	Repository string       `json:"repository"`
	Source     model.Source `json:"source"`
	Content    string       `json:"content_base64"`
}
type input struct {
	ID           string   `json:"id"`
	Family       string   `json:"family"`
	Seed         *uint64  `json:"seed,omitempty"`
	Factor       *float64 `json:"factor"`
	ImportType   *float64 `json:"import_type"`
	Spread       *float64 `json:"spread"`
	BadPair      bool     `json:"expected_bad_pair"`
	BadSpread    bool     `json:"expected_bad_spread"`
	Joint        bool     `json:"expected_joint"`
	Default      bool     `json:"expected_default"`
	OutputFactor float64  `json:"expected_output_factor"`
	Error        bool     `json:"expected_error"`
}

func number(n float64) *float64 { return &n }
func row(id, family string, f, t, s *float64, seed *uint64) input {
	fp, tp, sp := f != nil, t != nil, s != nil
	badPair := fp != tp
	badSpread := fp && tp && !sp
	replacement := (badPair && badSpread) || !fp
	value := 1.0
	if !replacement {
		value = *f
	}
	return input{id, family, seed, f, t, s, badPair, badSpread, badPair && badSpread, replacement, value, badPair || badSpread || value <= 0 || value > 1}
}
func run() error {
	ctx := context.Background()
	dir := "src/workspaces/data_engineering/investigations/radar_contradictions_2026_11_03"
	out := "var/lineage/radar-contradictions-20261103"
	libraryPin := "6f72bfb32c447e92cf641a1dd4bcb2b94fac27f9"
	specifications := []struct{ key, repo, pin, path string }{
		{"loan", "radar-libraries", libraryPin, "radar_libraries/transform/loan_transform_helper.py"},
		{"dataframe", "radar-libraries", libraryPin, "radar_libraries/mapping/dataframe_helper.py"},
		{"mapping", "radar-libraries", libraryPin, "radar_libraries/mapping/mapping_helper.py"},
		{"transform", "radar-libraries", libraryPin, "radar_libraries/transform/transform_helper.py"},
		{"notebook", "radar-notebooks", "60beb1ccd9bb2074f440de27e0e8f8956acab884", "notebooks/Shared/Clients/BOTW/Map_Others_BOTW.py"},
	}
	sources := map[string]pinned{}
	for _, s := range specifications {
		b, err := source.ReadGit(ctx, "../"+s.repo, s.pin, s.path, 1<<20)
		if err != nil {
			return err
		}
		receipt, err := source.Receipt(s.pin, s.path, b)
		if err != nil {
			return err
		}
		sources[s.key] = pinned{s.repo, receipt, base64.StdEncoding.EncodeToString(b)}
	}
	cases := []input{}
	for f := 0; f < 2; f++ {
		for t := 0; t < 2; t++ {
			for s := 0; s < 2; s++ {
				var factor, typ, spread *float64
				if f == 1 {
					factor = number(.75)
				}
				if t == 1 {
					typ = number(0)
				}
				if s == 1 {
					spread = number(.01)
				}
				cases = append(cases, row(fmt.Sprintf("presence-%d%d%d", f, t, s), "exhaustive_null_presence", factor, typ, spread, nil))
			}
		}
	}
	for i, n := range []float64{-1, 0, math.Nextafter(0, 1), .75, 1, math.Nextafter(1, 2)} {
		cases = append(cases, row(fmt.Sprintf("boundary-%d", i), "scaling_boundaries", number(n), number(0), number(.01), nil))
	}
	for _, seed := range []uint64{1, 42, 20261103} {
		rng := rand.New(rand.NewPCG(seed, 20261103))
		for i := 0; i < 32; i++ {
			f, t, s := number([]float64{0, .25, .75, 1, 1.25}[rng.IntN(5)]), number(0), number(.01)
			if rng.IntN(2) == 0 {
				f = nil
			}
			if rng.IntN(2) == 0 {
				t = nil
			}
			if rng.IntN(2) == 0 {
				s = nil
			}
			cases = append(cases, row(fmt.Sprintf("seed-%d-%d", seed, i), "seeded_null_presence", f, t, s, &seed))
		}
	}
	payload := struct {
		Sources map[string]pinned `json:"sources"`
		Cases   []input           `json:"cases"`
		Seeds   []uint64          `json:"seeds"`
		Samples int               `json:"samples_per_seed"`
	}{sources, cases, []uint64{1, 42, 20261103}, 32}
	b, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(out, 0700); err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(out, "payload.json"), b, 0600); err != nil {
		return err
	}
	template, err := os.ReadFile(filepath.Join(dir, "compare.py"))
	if err != nil {
		return err
	}
	marker := "PAYLOAD_GZIP_BASE64 = '__PINNED_PAYLOAD__'"
	if strings.Count(string(template), marker) != 1 {
		return fmt.Errorf("comparison template requires exactly one payload marker")
	}
	var compressed bytes.Buffer
	w := gzip.NewWriter(&compressed)
	if _, err := w.Write(b); err != nil {
		return err
	}
	if err := w.Close(); err != nil {
		return err
	}
	literal, err := json.Marshal(base64.StdEncoding.EncodeToString(compressed.Bytes()))
	if err != nil {
		return err
	}
	notebook := strings.Replace(string(template), marker, "PAYLOAD_GZIP_BASE64 = "+string(literal), 1)
	if len(notebook) > 950000 {
		return fmt.Errorf("prepared SOURCE exceeds 950000 bytes")
	}
	if err := os.WriteFile(filepath.Join(out, "prepared.py"), []byte(notebook), 0600); err != nil {
		return err
	}
	fmt.Printf("Prepared %d library rows; seeds [1,42,20261103], 32 samples/seed; %d SOURCE bytes.\n", len(cases), len(notebook))
	return nil
}
func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
