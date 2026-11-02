package main

import (
	"context"
	"strings"
	"testing"
)

func TestLineageCLIRejectsMissingAndIrrelevantInputs(t *testing.T) {
	for _, tc := range []struct {
		args []string
		want string
	}{
		{[]string{"lineage"}, "requires build"},
		{[]string{"lineage", "compare"}, "explicit --base"},
		{[]string{"lineage", "build", "--repo", "invalid"}, "name=checkout"},
		{[]string{"lineage", "build", "--repo", "di=one", "--repo", "di=two"}, "unique"},
		{[]string{"lineage", "show", "extra"}, "positional"},
		{[]string{"lineage", "compare", "--dry-run"}, "not supported"},
		{[]string{"lineage", "backfill"}, "explicit --snapshot"},
	} {
		err := run(context.Background(), tc.args)
		if err == nil || !strings.Contains(err.Error(), tc.want) {
			t.Errorf("%v: %v; want %s", tc.args, err, tc.want)
		}
	}
}
