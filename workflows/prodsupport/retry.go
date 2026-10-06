package prodsupport

import (
	"fmt"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

var (
	numberPattern    = regexp.MustCompile(`\b\d+\b`)
	exclusionPattern = regexp.MustCompile(`(?i)(?:don't|do not|except|exclude)\s+(?:do\s+)?(.*)`)
	caDirection      = regexp.MustCompile(`(?i)\bca(?:-?02)?\b`)
	usDirection      = regexp.MustCompile(`(?i)\bus(?:-?01)?\b`)
)

// RetryBatch contains tasks sharing one regional DAG run.
type RetryBatch struct {
	Region  Region   `json:"region"`
	DAGID   string   `json:"dag_id"`
	RunID   string   `json:"run_id"`
	TaskIDs []string `json:"task_ids"`
}

// RetryTaskReference identifies one Airflow-selected task and state.
type RetryTaskReference struct {
	Region Region `json:"region"`
	DAGID  string `json:"dag_id"`
	RunID  string `json:"run_id"`
	TaskID string `json:"task_id"`
	State  string `json:"state"`
}

// SelectRetryCandidates selects candidates by ordinal, region, and exclusions.
func SelectRetryCandidates(
	direction string,
	candidates []RetryCandidate,
) ([]RetryCandidate, error) {
	lowered := strings.ToLower(direction)
	if !strings.Contains(lowered, "retry") && !strings.Contains(lowered, "follow up") {
		return nil, fmt.Errorf("follow-up direction must request retry or follow up")
	}
	exclusion := exclusionPattern.FindStringSubmatchIndex(direction)
	includedText := direction
	excludedText := ""
	if len(exclusion) >= 4 {
		includedText = direction[:exclusion[0]]
		excludedText = direction[exclusion[2]:exclusion[3]]
	}
	included := numbers(includedText)
	excluded := numbers(excludedText)
	var region Region
	if caDirection.MatchString(lowered) {
		region = CA02
	} else if usDirection.MatchString(lowered) {
		region = US01
	}
	known := make(map[int]struct{}, len(candidates))
	selected := make([]RetryCandidate, 0, len(candidates))
	for _, candidate := range candidates {
		known[candidate.Number] = struct{}{}
		_, explicitlyIncluded := included[candidate.Number]
		_, explicitlyExcluded := excluded[candidate.Number]
		if (len(included) == 0 || explicitlyIncluded) && !explicitlyExcluded &&
			(region == "" || candidate.Region == region) {
			selected = append(selected, candidate)
		}
	}
	unknown := make([]int, 0)
	for number := range included {
		if _, exists := known[number]; !exists {
			unknown = append(unknown, number)
		}
	}
	for number := range excluded {
		if _, exists := known[number]; !exists {
			unknown = append(unknown, number)
		}
	}
	if len(unknown) > 0 {
		sort.Ints(unknown)
		values := make([]string, len(unknown))
		for index, value := range unknown {
			values[index] = strconv.Itoa(value)
		}
		return nil, fmt.Errorf("unknown retry candidate numbers: %s", strings.Join(values, ", "))
	}
	if len(selected) == 0 {
		return nil, fmt.Errorf("follow-up direction selected no retry candidates")
	}
	return selected, nil
}

// RetryBatches groups selected tasks into exact regional DAG-run requests.
func RetryBatches(candidates []RetryCandidate) []RetryBatch {
	type key struct {
		region Region
		dagID  string
		runID  string
	}
	grouped := make(map[key][]string)
	keys := make([]key, 0)
	for _, candidate := range candidates {
		group := key{candidate.Region, candidate.DAGID, candidate.RunID}
		if _, exists := grouped[group]; !exists {
			keys = append(keys, group)
		}
		if !contains(grouped[group], candidate.TaskID) {
			grouped[group] = append(grouped[group], candidate.TaskID)
		}
	}
	sort.Slice(keys, func(left, right int) bool {
		leftKey := fmt.Sprintf("%s\x00%s\x00%s", keys[left].region, keys[left].dagID, keys[left].runID)
		rightKey := fmt.Sprintf("%s\x00%s\x00%s", keys[right].region, keys[right].dagID, keys[right].runID)
		return leftKey < rightKey
	})
	batches := make([]RetryBatch, len(keys))
	for index, group := range keys {
		batches[index] = RetryBatch{
			Region: group.region, DAGID: group.dagID, RunID: group.runID,
			TaskIDs: append([]string(nil), grouped[group]...),
		}
	}
	return batches
}

func numbers(value string) map[int]struct{} {
	result := make(map[int]struct{})
	for _, match := range numberPattern.FindAllString(value, -1) {
		number, _ := strconv.Atoi(match)
		result[number] = struct{}{}
	}
	return result
}

func contains(values []string, value string) bool {
	for _, candidate := range values {
		if candidate == value {
			return true
		}
	}
	return false
}
