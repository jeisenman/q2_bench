// Package airflow implements authenticated Airflow REST adapters.
package airflow

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

const (
	TransientMaxAttempts = 3
	TransientBackoff     = 30 * time.Second
)

// Credentials contains one Airflow endpoint and its basic-auth values.
type Credentials struct {
	Host     string
	Username string
	Password string
}

// Transport is the injectable Airflow HTTP boundary.
type Transport interface {
	Request(context.Context, Credentials, string, string, map[string]any) (any, error)
}

// HTTPStatusError reports a non-success Airflow response.
type HTTPStatusError struct {
	StatusCode int
	Body       string
}

func (e *HTTPStatusError) Error() string {
	return fmt.Sprintf("Airflow returned HTTP %d: %s", e.StatusCode, e.Body)
}

// HTTPTransport uses net/http with bounded responses and basic authentication.
type HTTPTransport struct {
	Client *http.Client
}

// Request executes one authenticated Airflow request.
func (t HTTPTransport) Request(
	ctx context.Context,
	config Credentials,
	method, path string,
	payload map[string]any,
) (any, error) {
	var body io.Reader
	if payload != nil {
		encoded, err := json.Marshal(payload)
		if err != nil {
			return nil, err
		}
		body = bytes.NewReader(encoded)
	}
	request, err := http.NewRequestWithContext(ctx, method, config.Host+path, body)
	if err != nil {
		return nil, err
	}
	authorization := base64.StdEncoding.EncodeToString(
		[]byte(config.Username + ":" + config.Password),
	)
	request.Header.Set("Authorization", "Basic "+authorization)
	request.Header.Set("Content-Type", "application/json")
	client := t.Client
	if client == nil {
		client = &http.Client{Timeout: 30 * time.Second}
	}
	response, err := client.Do(request)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	content, err := io.ReadAll(io.LimitReader(response.Body, 16<<20))
	if err != nil {
		return nil, err
	}
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return nil, &HTTPStatusError{
			StatusCode: response.StatusCode, Body: strings.TrimSpace(string(content)),
		}
	}
	if strings.Contains(response.Header.Get("Content-Type"), "application/json") {
		var decoded any
		if err := json.Unmarshal(content, &decoded); err != nil {
			return nil, fmt.Errorf("decode Airflow JSON response: %w", err)
		}
		return decoded, nil
	}
	return string(content), nil
}

// RequestWithTransientRetry retries gateway and service-unavailable failures.
func RequestWithTransientRetry(
	ctx context.Context,
	transport Transport,
	config Credentials,
	method, path string,
	payload map[string]any,
	sleep func(context.Context, time.Duration) error,
) (any, error) {
	if sleep == nil {
		sleep = sleepContext
	}
	for attempt := 0; attempt < TransientMaxAttempts; attempt++ {
		response, err := transport.Request(ctx, config, method, path, payload)
		if err == nil {
			return response, nil
		}
		statusError, transient := err.(*HTTPStatusError)
		if !transient ||
			(statusError.StatusCode != http.StatusBadGateway &&
				statusError.StatusCode != http.StatusServiceUnavailable) ||
			attempt == TransientMaxAttempts-1 {
			return nil, err
		}
		if err := sleep(ctx, TransientBackoff); err != nil {
			return nil, err
		}
	}
	panic("unreachable")
}

func sleepContext(ctx context.Context, duration time.Duration) error {
	timer := time.NewTimer(duration)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}
