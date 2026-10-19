package airflow

import (
	"context"
	"fmt"
	"net/url"
	"strconv"
	"sync"
	"time"

	"github.com/jeisenman/q2_bench/workflows/prodsupport"
)

// RegionConfig binds Airflow credentials to one production region.
type RegionConfig struct {
	Region      prodsupport.Region
	Credentials Credentials
}

// Source discovers failures and retrieves exact evidence.
type Source struct {
	Regions   []RegionConfig
	Transport Transport
	Sleep     func(context.Context, time.Duration) error
}

// NewSource validates and constructs an Airflow source.
func NewSource(regions []RegionConfig, transport Transport) *Source {
	if transport == nil {
		transport = HTTPTransport{}
	}
	return &Source{
		Regions: append([]RegionConfig(nil), regions...), Transport: transport,
	}
}

// DiscoverFailures queries all configured regions concurrently.
func (s *Source) DiscoverFailures(
	ctx context.Context,
	since time.Time,
) ([]prodsupport.AirflowFailure, error) {
	if since.IsZero() {
		return nil, fmt.Errorf("Airflow discovery cutoff must be timezone-aware")
	}
	batches := make([][]prodsupport.AirflowFailure, len(s.Regions))
	errors := make([]error, len(s.Regions))
	var wait sync.WaitGroup
	for index, config := range s.Regions {
		wait.Add(1)
		go func() {
			defer wait.Done()
			batches[index], errors[index] = s.discoverRegion(ctx, config, since)
		}()
	}
	wait.Wait()
	failures := make([]prodsupport.AirflowFailure, 0)
	for index, err := range errors {
		if err != nil {
			return nil, err
		}
		failures = append(failures, batches[index]...)
	}
	return failures, nil
}

// DiscoverRegionFailures queries one explicitly selected region.
func (s *Source) DiscoverRegionFailures(
	ctx context.Context,
	region prodsupport.Region,
	since time.Time,
) ([]prodsupport.AirflowFailure, error) {
	if since.IsZero() {
		return nil, fmt.Errorf("Airflow discovery cutoff must be timezone-aware")
	}
	config, err := s.configFor(region)
	if err != nil {
		return nil, err
	}
	return s.discoverRegion(ctx, config, since)
}

// FetchLog retrieves the exact task-attempt log.
func (s *Source) FetchLog(
	ctx context.Context,
	failure prodsupport.AirflowFailure,
) (string, error) {
	config, err := s.configFor(failure.Region)
	if err != nil {
		return "", err
	}
	parts := []string{
		"dags", failure.DAGID, "dagRuns", failure.RunID, "taskInstances",
		failure.TaskID, "logs", strconv.Itoa(failure.TryNumber),
	}
	path := "/api/v1"
	for _, part := range parts {
		path += "/" + url.PathEscape(part)
	}
	response, err := RequestWithTransientRetry(
		ctx,
		s.Transport,
		config.Credentials,
		"GET",
		path,
		nil,
		s.Sleep,
	)
	if err != nil {
		return "", err
	}
	switch typed := response.(type) {
	case string:
		return typed, nil
	case map[string]any:
		if content, ok := typed["content"].(string); ok {
			return content, nil
		}
	}
	return "", fmt.Errorf("Airflow task log response must contain text content")
}

// FetchTaskMetadata retrieves exact operator metadata.
func (s *Source) FetchTaskMetadata(
	ctx context.Context,
	failure prodsupport.AirflowFailure,
) (prodsupport.AirflowTaskMetadata, error) {
	config, err := s.configFor(failure.Region)
	if err != nil {
		return prodsupport.AirflowTaskMetadata{}, err
	}
	path := fmt.Sprintf(
		"/api/v1/dags/%s/tasks/%s",
		url.PathEscape(failure.DAGID),
		url.PathEscape(failure.TaskID),
	)
	response, err := RequestWithTransientRetry(
		ctx,
		s.Transport,
		config.Credentials,
		"GET",
		path,
		nil,
		s.Sleep,
	)
	if err != nil {
		return prodsupport.AirflowTaskMetadata{}, err
	}
	payload, ok := response.(map[string]any)
	if !ok {
		return prodsupport.AirflowTaskMetadata{}, fmt.Errorf(
			"Airflow task metadata response must be an object",
		)
	}
	operator, _ := payload["operator_name"].(string)
	if operator == "" {
		if classRef, ok := payload["class_ref"].(map[string]any); ok {
			operator, _ = classRef["class_name"].(string)
		}
	}
	metadata := prodsupport.AirflowTaskMetadata{
		DAGID: failure.DAGID, TaskID: failure.TaskID, OperatorName: operator,
	}
	if err := metadata.Validate(); err != nil {
		return prodsupport.AirflowTaskMetadata{}, fmt.Errorf(
			"Airflow task metadata response is missing operator_name",
		)
	}
	return metadata, nil
}

// HasSuccessWithin checks for the same DAG and task in a bounded success window.
func (s *Source) HasSuccessWithin(
	ctx context.Context,
	failure prodsupport.AirflowFailure,
	startAt, endAt time.Time,
) (bool, error) {
	if startAt.IsZero() || endAt.IsZero() {
		return false, fmt.Errorf("Airflow success window must be timezone-aware")
	}
	if !endAt.After(startAt) {
		return false, fmt.Errorf("Airflow success window end must be later than its start")
	}
	config, err := s.configFor(failure.Region)
	if err != nil {
		return false, err
	}
	payload := map[string]any{
		"dag_ids": []string{failure.DAGID}, "task_ids": []string{failure.TaskID},
		"state": []string{"success"}, "end_date_gte": formatUTC(startAt),
		"end_date_lte": formatUTC(endAt), "page_limit": 100, "page_offset": 0,
	}
	offset := 0
	for {
		response, requestErr := RequestWithTransientRetry(
			ctx,
			s.Transport,
			config.Credentials,
			"POST",
			"/api/v1/dags/~/dagRuns/~/taskInstances/list",
			payload,
			s.Sleep,
		)
		if requestErr != nil {
			return false, requestErr
		}
		page, total, pageErr := taskInstances(response)
		if pageErr != nil {
			return false, pageErr
		}
		for _, item := range page {
			end, parseErr := parseTimestamp(item["end_date"])
			if parseErr == nil &&
				fmt.Sprint(item["dag_id"]) == failure.DAGID &&
				fmt.Sprint(item["task_id"]) == failure.TaskID &&
				!end.Before(startAt) && end.Before(endAt) {
				return true, nil
			}
		}
		offset += len(page)
		if len(page) == 0 || offset >= total {
			return false, nil
		}
		payload["page_offset"] = offset
	}
}

// ExecuteRetry revalidates and clears an exact approved retry batch.
func (s *Source) ExecuteRetry(
	ctx context.Context,
	batch prodsupport.RetryBatch,
	approvalID string,
) ([]prodsupport.RetryTaskReference, error) {
	config, err := s.configFor(batch.Region)
	if err != nil {
		return nil, err
	}
	return ExecuteRetry(
		ctx,
		batch,
		approvalID,
		config.Credentials,
		s.Transport,
		func(ctx context.Context, taskID string) (any, error) {
			path := fmt.Sprintf(
				"/api/v1/dags/%s/dagRuns/%s/taskInstances/%s",
				url.PathEscape(batch.DAGID),
				url.PathEscape(batch.RunID),
				url.PathEscape(taskID),
			)
			return RequestWithTransientRetry(
				ctx,
				s.Transport,
				config.Credentials,
				"GET",
				path,
				nil,
				s.Sleep,
			)
		},
	)
}

// PlanDependencyRerun returns an exact non-failed downstream dry-run selection.
func (s *Source) PlanDependencyRerun(
	ctx context.Context,
	batch prodsupport.RetryBatch,
) ([]prodsupport.RetryTaskReference, error) {
	config, err := s.configFor(batch.Region)
	if err != nil {
		return nil, err
	}
	runState, err := s.GetDAGRunState(
		ctx,
		batch.Region,
		batch.DAGID,
		batch.RunID,
	)
	if err != nil {
		return nil, err
	}
	return PlanDependencyRerun(
		ctx,
		batch,
		config.Credentials,
		s.Transport,
		runState,
	)
}

// ExecuteDependencyRerun clears one exact approved downstream selection.
func (s *Source) ExecuteDependencyRerun(
	ctx context.Context,
	batch prodsupport.RetryBatch,
	approvalID string,
) ([]prodsupport.RetryTaskReference, error) {
	config, err := s.configFor(batch.Region)
	if err != nil {
		return nil, err
	}
	runState, err := s.GetDAGRunState(
		ctx,
		batch.Region,
		batch.DAGID,
		batch.RunID,
	)
	if err != nil {
		return nil, err
	}
	return ExecuteDependencyRerun(
		ctx,
		batch,
		approvalID,
		config.Credentials,
		s.Transport,
		runState,
	)
}

func (s *Source) discoverRegion(
	ctx context.Context,
	config RegionConfig,
	since time.Time,
) ([]prodsupport.AirflowFailure, error) {
	payload := map[string]any{
		"state": []string{"failed"}, "end_date_gte": formatUTC(since),
		"page_limit": 1000, "page_offset": 0,
	}
	failures := make([]prodsupport.AirflowFailure, 0)
	for {
		response, err := RequestWithTransientRetry(
			ctx,
			s.Transport,
			config.Credentials,
			"POST",
			"/api/v1/dags/~/dagRuns/~/taskInstances/list",
			payload,
			s.Sleep,
		)
		if err != nil {
			return nil, err
		}
		page, total, err := taskInstances(response)
		if err != nil {
			return nil, err
		}
		for _, item := range page {
			failure, err := failureFromRecord(config.Region, item)
			if err != nil {
				return nil, err
			}
			failures = append(failures, failure)
		}
		if len(page) == 0 || len(failures) >= total {
			return failures, nil
		}
		payload["page_offset"] = len(failures)
	}
}

func (s *Source) configFor(region prodsupport.Region) (RegionConfig, error) {
	for _, config := range s.Regions {
		if config.Region == region {
			return config, nil
		}
	}
	return RegionConfig{}, fmt.Errorf("region is not configured: %s", region)
}

func taskInstances(response any) ([]map[string]any, int, error) {
	payload, ok := response.(map[string]any)
	if !ok {
		return nil, 0, fmt.Errorf("Airflow discovery response must be an object")
	}
	rawItems, itemsOK := payload["task_instances"].([]any)
	total, totalOK := integer(payload["total_entries"])
	if !itemsOK || !totalOK {
		return nil, 0, fmt.Errorf("Airflow discovery response is missing task instances")
	}
	items := make([]map[string]any, 0, len(rawItems))
	for _, raw := range rawItems {
		if item, ok := raw.(map[string]any); ok {
			items = append(items, item)
		}
	}
	return items, total, nil
}

func integer(value any) (int, bool) {
	switch typed := value.(type) {
	case int:
		return typed, true
	case int32:
		return int(typed), true
	case int64:
		return int(typed), true
	case float64:
		if typed != float64(int(typed)) {
			return 0, false
		}
		return int(typed), true
	default:
		return 0, false
	}
}

func failureFromRecord(
	region prodsupport.Region,
	value map[string]any,
) (prodsupport.AirflowFailure, error) {
	endAt, err := parseTimestamp(value["end_date"])
	if err != nil {
		return prodsupport.AirflowFailure{}, err
	}
	startAt := endAt
	if value["start_date"] != nil {
		startAt, err = parseTimestamp(value["start_date"])
		if err != nil {
			return prodsupport.AirflowFailure{}, err
		}
	}
	tryNumber := 1
	if raw, ok := value["try_number"].(float64); ok && raw > 0 {
		tryNumber = int(raw)
	}
	failure := prodsupport.AirflowFailure{
		Region: region, DAGID: fmt.Sprint(value["dag_id"]),
		RunID: fmt.Sprint(value["dag_run_id"]), TaskID: fmt.Sprint(value["task_id"]),
		StartAt: startAt, EndAt: endAt, TryNumber: tryNumber,
	}
	if err := failure.Validate(); err != nil {
		return prodsupport.AirflowFailure{}, err
	}
	return failure, nil
}

func parseTimestamp(value any) (time.Time, error) {
	text, ok := value.(string)
	if !ok {
		return time.Time{}, fmt.Errorf("Airflow timestamp must be text")
	}
	return time.Parse(time.RFC3339Nano, text)
}

func formatUTC(value time.Time) string {
	return value.UTC().Format(time.RFC3339)
}
