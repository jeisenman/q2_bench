package local

import (
	"context"
	"testing"

	"github.com/jeisenman/q2_bench/domain"
)

func TestDatasetProviderFiltersAndBoundsRecords(t *testing.T) {
	t.Parallel()
	provider := DatasetProvider{Datasets: map[string][]domain.Attributes{
		"failures": {
			{{Name: "region", Value: "us"}, {Name: "id", Value: 1}},
			{{Name: "region", Value: "ca"}, {Name: "id", Value: 2}},
		},
	}}
	records, err := provider.FetchRecords(
		context.Background(),
		"failures",
		domain.Attributes{{Name: "region", Value: "ca"}},
		1,
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(records) != 1 || records[0][1].Value != 2 {
		t.Fatalf("records = %#v", records)
	}
}
