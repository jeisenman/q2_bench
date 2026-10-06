package prodsupport

import (
	"context"
	"fmt"
	"sort"
	"sync"
	"time"
)

// AirflowFailureSource discovers failures.
type AirflowFailureSource interface {
	DiscoverFailures(context.Context, time.Time) ([]AirflowFailure, error)
}

// RegionalAirflowFailureSource supports explicitly scoped regional discovery.
type RegionalAirflowFailureSource interface {
	DiscoverRegionFailures(context.Context, Region, time.Time) ([]AirflowFailure, error)
}

// AirflowChecker filters region, time window, and duplicate failures.
type AirflowChecker struct {
	Source  AirflowFailureSource
	Regions []Region
}

// Check returns unique selected failures ending at or after the lower bound.
func (c AirflowChecker) Check(
	ctx context.Context,
	startAt, endAt time.Time,
) ([]AirflowFailure, error) {
	if startAt.IsZero() || endAt.IsZero() {
		return nil, fmt.Errorf("Airflow check boundaries must be timezone-aware")
	}
	if !endAt.After(startAt) {
		return nil, fmt.Errorf("Airflow check end must be later than start")
	}
	regions := c.Regions
	if regions == nil {
		regions = []Region{US01, CA02}
	}
	if len(regions) == 0 {
		return nil, fmt.Errorf("Airflow checker requires at least one region")
	}
	var failures []AirflowFailure
	var err error
	if regional, ok := c.Source.(RegionalAirflowFailureSource); ok {
		batches := make([][]AirflowFailure, len(regions))
		errors := make([]error, len(regions))
		var wait sync.WaitGroup
		for index, region := range regions {
			wait.Add(1)
			go func() {
				defer wait.Done()
				batches[index], errors[index] = regional.DiscoverRegionFailures(
					ctx,
					region,
					startAt,
				)
			}()
		}
		wait.Wait()
		for index, batchErr := range errors {
			if batchErr != nil {
				return nil, batchErr
			}
			failures = append(failures, batches[index]...)
		}
	} else {
		failures, err = c.Source.DiscoverFailures(ctx, startAt)
		if err != nil {
			return nil, err
		}
	}
	selected := make(map[string]AirflowFailure)
	allowed := make(map[Region]struct{}, len(regions))
	for _, region := range regions {
		allowed[region] = struct{}{}
	}
	for _, failure := range failures {
		if _, exists := allowed[failure.Region]; !exists ||
			failure.EndAt.Before(startAt) {
			continue
		}
		selected[failure.FailureID()] = failure
	}
	result := make([]AirflowFailure, 0, len(selected))
	for _, failure := range selected {
		result = append(result, failure)
	}
	sort.Slice(result, func(left, right int) bool {
		return failureSortKey(result[left]) < failureSortKey(result[right])
	})
	return result, nil
}

// ClusterHealthSource reads regional cluster health.
type ClusterHealthSource interface {
	InspectHealth(
		context.Context,
		Region,
		time.Time,
		time.Time,
	) (RegionalClusterHealth, error)
}

// CheckClusterHealth reads selected regions concurrently.
func CheckClusterHealth(
	ctx context.Context,
	source ClusterHealthSource,
	regions []Region,
	startAt, endAt time.Time,
) ([]RegionalClusterHealth, error) {
	if regions == nil {
		regions = []Region{US01, CA02}
	}
	if len(regions) == 0 {
		return nil, fmt.Errorf("cluster checker requires at least one region")
	}
	results := make([]RegionalClusterHealth, len(regions))
	errors := make([]error, len(regions))
	var wait sync.WaitGroup
	for index, region := range regions {
		wait.Add(1)
		go func() {
			defer wait.Done()
			results[index], errors[index] = source.InspectHealth(ctx, region, startAt, endAt)
		}()
	}
	wait.Wait()
	for _, err := range errors {
		if err != nil {
			return nil, err
		}
	}
	return results, nil
}
