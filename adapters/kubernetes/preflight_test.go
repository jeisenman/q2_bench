package kubernetes

import (
	"context"
	"errors"
	"strings"
	"testing"
)

func TestPreflightVerifiesAuthorizationAndMetricsAPI(t *testing.T) {
	t.Parallel()
	calls := 0
	source := NewSource(func(
		_ context.Context,
		_ string,
		args ...string,
	) ([]byte, error) {
		calls++
		if strings.Contains(strings.Join(args, " "), "auth can-i") {
			return []byte("yes\n"), nil
		}
		return []byte(`{"kind":"APIResourceList"}`), nil
	})
	if err := source.Preflight(context.Background(), "l3-us01", "scheduler"); err != nil {
		t.Fatal(err)
	}
	if calls != 2 {
		t.Fatalf("calls = %d", calls)
	}
}

func TestPreflightRejectsMissingMetricsPermission(t *testing.T) {
	t.Parallel()
	source := NewSource(func(
		context.Context,
		string,
		...string,
	) ([]byte, error) {
		return []byte("no\n"), nil
	})
	err := source.Preflight(context.Background(), "l3-us01", "scheduler")
	if err == nil || !strings.Contains(err.Error(), "cannot read pod metrics") {
		t.Fatalf("error = %v", err)
	}
}

func TestPreflightReportsMetricsAPIFailure(t *testing.T) {
	t.Parallel()
	calls := 0
	source := NewSource(func(
		context.Context,
		string,
		...string,
	) ([]byte, error) {
		calls++
		if calls == 1 {
			return []byte("yes"), nil
		}
		return nil, errors.New("metrics unavailable")
	})
	err := source.Preflight(context.Background(), "l3-us01", "scheduler")
	if err == nil || !strings.Contains(err.Error(), "Metrics API is unavailable") {
		t.Fatalf("error = %v", err)
	}
}
