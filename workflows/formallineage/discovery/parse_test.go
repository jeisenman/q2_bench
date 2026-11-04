package discovery

import (
	"context"
	"github.com/jeisenman/q2_bench/workflows/formallineage/model"
	"github.com/jeisenman/q2_bench/workflows/formallineage/source"
	"strings"
	"testing"
)

const testCommit = "0123456789012345678901234567890123456789"

func TestSharedCandidatesRemainUnknown(t *testing.T) {
	cases := []struct {
		file, code, name string
		runtime          model.Runtime
	}{
		{"example.py", "import pandas as pd\ndef transform(df):\n    return df.query('value > 0').drop(columns=['secret'])\n", "transform", model.Pandas},
		{"example.py", "from pyspark.sql import functions as F\ndef transform(df):\n    return df.filter(F.col('value') > 0).drop('secret')\n", "transform", model.PySpark},
		{"example.cs", "using System.Linq; namespace Example { class Jobs { object Transform(dynamic df) { return df.Where(x => x.Value > 0).Select(x => x.Value); } } }", "Example.Jobs.Transform", model.DotNet},
		{"example.ts", "class Jobs { transform(df: any) { return df.filter((x: any) => x.value > 0); } }", "Jobs.transform", model.TypeScript},
		{"example.cs", "namespace Example; class Jobs { object Transform(dynamic df) => df.Where(x => x.Value > 0); }", "Example.Jobs.Transform", model.DotNet},
	}
	for _, tc := range cases {
		t.Run(tc.name+string(tc.runtime), func(t *testing.T) {
			b := []byte(tc.code)
			receipt, err := source.Receipt(testCommit, tc.file, b)
			if err != nil {
				t.Fatal(err)
			}
			got, err := Parse(context.Background(), "test", "test", receipt, b)
			if err != nil {
				t.Fatal(err)
			}
			if got.PredictionReady || got.Status != "unknown" || got.Runtime != tc.runtime {
				t.Fatalf("invalid readiness/runtime: %+v", got)
			}
			found, filter := false, false
			for _, d := range got.Declarations {
				if d.Method.Function == tc.name {
					found = true
					for _, o := range d.Operations {
						filter = filter || o.Kind == "filter"
						if o.Resolved {
							t.Fatal("lexical operation resolved")
						}
					}
				}
				if d.Method.Status != "unknown" || len(d.Method.Steps) != 0 || d.Method.ID == "" {
					t.Fatal("discovery became executable")
				}
			}
			if !found || !filter {
				t.Fatalf("missing declaration/filter: %+v", got.Declarations)
			}
			again, err := Parse(context.Background(), "test", "test", receipt, b)
			if err != nil || got.Declarations[0].Method.ID != again.Declarations[0].Method.ID {
				t.Fatal("unstable IDs")
			}
		})
	}
}

func TestModuleAndRejections(t *testing.T) {
	b := []byte("import pandas as pd\nresult = pd.read_csv('synthetic.csv').query('x > 0')\n")
	receipt, _ := source.Receipt(testCommit, "notebook.py", b)
	result, err := Parse(context.Background(), "radar", "radar-notebooks", receipt, b)
	if err != nil {
		t.Fatal(err)
	}
	if len(result.ModuleCalls) == 0 || len(result.Declarations) != 1 || result.Declarations[0].Method.Function != "<module>" {
		t.Fatal("module calls lost")
	}
	receipt.SHA256 = strings.Repeat("0", 64)
	if _, err := Parse(context.Background(), "radar", "radar-notebooks", receipt, b); err == nil {
		t.Fatal("accepted stale bytes")
	}
	broken := []byte("def broken(:\n")
	receipt, _ = source.Receipt(testCommit, "broken.py", broken)
	if _, err := Parse(context.Background(), "test", "test", receipt, broken); err == nil {
		t.Fatal("accepted syntax error")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	receipt, _ = source.Receipt(testCommit, "notebook.py", b)
	if _, err := Parse(ctx, "test", "test", receipt, b); err == nil {
		t.Fatal("ignored cancellation")
	}
	large := []byte(strings.Repeat("#", (1<<20)+1))
	receipt, _ = source.Receipt(testCommit, "large.py", large)
	if _, err := Parse(context.Background(), "test", "test", receipt, large); err == nil {
		t.Fatal("ignored byte bound")
	}
}
