package oms

import (
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

const OMSTable = "DI_Scheduling_CL"

// JobQueryParameters identifies one workload attempt.
type JobQueryParameters struct {
	Region    Region
	ClientID  string
	RunID     string
	TaskID    string
	TryNumber int
	StartAt   time.Time
	Table     string
}

// JobQuery contains executable KQL and routing metadata.
type JobQuery struct {
	WorkspaceName string
	Table         string
	WindowStart   time.Time
	WindowEnd     time.Time
	KQL           string
}

// BuildJobQuery creates one exact OMS query for the workload's UTC target window.
func BuildJobQuery(parameters JobQueryParameters) (JobQuery, error) {
	if parameters.StartAt.IsZero() {
		return JobQuery{}, fmt.Errorf("start_at must not be zero")
	}
	if parameters.TryNumber < 1 {
		return JobQuery{}, fmt.Errorf("try_number_d must be positive")
	}
	for name, value := range map[string]string{
		"client_id_g": parameters.ClientID,
		"run_id_s":    parameters.RunID,
		"task_id_s":   parameters.TaskID,
	} {
		if strings.TrimSpace(value) == "" {
			return JobQuery{}, fmt.Errorf("%s must not be empty", name)
		}
	}
	table := parameters.Table
	if table == "" {
		table = OMSTable
	}
	if table != OMSTable {
		return JobQuery{}, fmt.Errorf("table must be %s", OMSTable)
	}
	if parameters.Region != US && parameters.Region != CA {
		return JobQuery{}, fmt.Errorf("unsupported OMS region: %q", parameters.Region)
	}
	utc := parameters.StartAt.UTC()
	windowStart := time.Date(utc.Year(), utc.Month(), utc.Day(), 5, 0, 0, 0, time.UTC)
	windowEnd := windowStart.Add(24 * time.Hour)
	workspace, err := ResolveWorkspace(Production, parameters.Region)
	if err != nil {
		return JobQuery{}, err
	}
	kql := strings.Join([]string{
		table,
		"// target date",
		fmt.Sprintf("| where window_start_t == datetime('%s')", windowStart.Format("2006-01-02T15:04Z")),
		fmt.Sprintf("| where client_id_g == %s", quote(parameters.ClientID)),
		fmt.Sprintf("| where run_id_s == %s", quote(parameters.RunID)),
		fmt.Sprintf("| where task_id_s == %s", quote(parameters.TaskID)),
		fmt.Sprintf("| where try_number_d == %d", parameters.TryNumber),
		"| project TimeGenerated, message_s, level_s, pod_name_s",
		"| order by TimeGenerated asc",
	}, "\n")
	return JobQuery{
		WorkspaceName: workspace.Name, Table: table,
		WindowStart: windowStart, WindowEnd: windowEnd, KQL: kql,
	}, nil
}

func quote(value string) string {
	encoded, _ := json.Marshal(value)
	return string(encoded)
}
