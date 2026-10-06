// Package oms contains provider-neutral OMS agent behavior.
package oms

import (
	"fmt"
	"regexp"
	"strings"
)

// Environment identifies an OMS deployment environment.
type Environment string

const (
	Production  Environment = "production"
	Staging     Environment = "staging"
	Development Environment = "development"
)

// Region identifies an OMS region.
type Region string

const (
	US Region = "us"
	CA Region = "ca"
)

// Workspace identifies one Azure Log Analytics workspace.
type Workspace struct {
	Name           string
	WorkspaceID    string
	SubscriptionID string
}

var workspaces = map[[2]string]Workspace{
	{string(Production), string(US)}: {
		Name: "pl-oms-us-primary", WorkspaceID: "6220c6e1-57a3-49c2-901c-bb5e5106f2b0",
		SubscriptionID: "71aa0ec0-8411-43a2-9908-ddd2add764eb",
	},
	{string(Production), string(CA)}: {
		Name: "pl-oms-ca-primary", WorkspaceID: "2fc9684b-5d16-42f0-ab99-9dc044e4ea73",
		SubscriptionID: "71aa0ec0-8411-43a2-9908-ddd2add764eb",
	},
	{string(Staging), string(US)}: {
		Name: "pl-oms-preprod-primary", WorkspaceID: "10983741-32db-4a0f-8607-61558f19b657",
		SubscriptionID: "cde221ff-e7f4-4d39-be20-6f9d532cab60",
	},
	{string(Development), string(US)}: {
		Name: "pl-oms-preprod-primary", WorkspaceID: "10983741-32db-4a0f-8607-61558f19b657",
		SubscriptionID: "cde221ff-e7f4-4d39-be20-6f9d532cab60",
	},
}

// ResolveWorkspace returns the hardcoded workspace for a route.
func ResolveWorkspace(environment Environment, region Region) (Workspace, error) {
	workspace, exists := workspaces[[2]string{string(environment), string(region)}]
	if !exists {
		return Workspace{}, fmt.Errorf(
			"no OMS workspace is configured for environment=%q, region=%q",
			environment,
			region,
		)
	}
	return workspace, nil
}

// Query is one bounded KQL query.
type Query struct {
	KQL      string
	Timespan string
}

// Validate rejects blank or unbounded query inputs.
func (q Query) Validate() error {
	if strings.TrimSpace(q.KQL) == "" {
		return fmt.Errorf("kql must not be empty")
	}
	if strings.TrimSpace(q.Timespan) == "" {
		return fmt.Errorf("timespan must not be empty")
	}
	return nil
}

// QueryResult contains provider-neutral tabular query data.
type QueryResult struct {
	Columns []string `json:"columns"`
	Rows    [][]any  `json:"rows"`
}

var logTypePattern = regexp.MustCompile(`^[A-Za-z0-9_]+$`)

// LogRecord is one custom OMS log entry.
type LogRecord struct {
	LogType string
	Fields  map[string]any
}

// Validate checks the Data Collector API log type and payload.
func (r LogRecord) Validate() error {
	if strings.TrimSpace(r.LogType) == "" {
		return fmt.Errorf("log_type must not be empty")
	}
	if !logTypePattern.MatchString(r.LogType) {
		return fmt.Errorf("log_type must contain only letters, numbers, or underscores")
	}
	if len(r.Fields) == 0 {
		return fmt.Errorf("fields must not be empty")
	}
	return nil
}
