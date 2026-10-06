package prodsupport

import (
	"fmt"
	"regexp"
	"strconv"
	"strings"
	"time"
)

const OperationalHour = 5

var (
	datePattern     = regexp.MustCompile(`\b(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})\b`)
	runStartPattern = regexp.MustCompile(
		`(?i)run/date_start\s+(\d{4}-\d{2}-\d{2})[,\s]+(\d{2}:\d{2}:\d{2})\s+UTC`,
	)
	usPattern = regexp.MustCompile(`(?i)\b(?:us|us-01|united states)\b`)
	caPattern = regexp.MustCompile(`(?i)\b(?:ca|ca-02|canada)\b`)
)

// QueryWindow is one resolved Airflow failure query boundary.
type QueryWindow struct {
	OperationalDate time.Time
	FailedSince     time.Time
	Source          string
}

// ResolveQueryWindow resolves explicit and relative prompts at 05:00 UTC.
func ResolveQueryWindow(prompt string, reference time.Time) (QueryWindow, error) {
	if reference.IsZero() {
		return QueryWindow{}, fmt.Errorf("reference time must be timezone-aware")
	}
	reference = reference.UTC()
	if match := runStartPattern.FindStringSubmatch(prompt); len(match) == 3 {
		failedSince, err := time.Parse("2006-01-02 15:04:05", match[1]+" "+match[2])
		if err != nil {
			return QueryWindow{}, err
		}
		failedSince = failedSince.UTC()
		return QueryWindow{
			OperationalDate: day(failedSince), FailedSince: failedSince,
			Source: "run_date_start",
		}, nil
	}
	if match := datePattern.FindStringSubmatch(prompt); len(match) == 4 {
		month, _ := strconv.Atoi(match[1])
		dayValue, _ := strconv.Atoi(match[2])
		year, _ := strconv.Atoi(match[3])
		if year < 100 {
			year += 2000
		}
		requested := time.Date(year, time.Month(month), dayValue, 0, 0, 0, 0, time.UTC)
		if requested.Month() != time.Month(month) || requested.Day() != dayValue {
			return QueryWindow{}, fmt.Errorf("invalid operational date")
		}
		return QueryWindow{
			OperationalDate: requested, FailedSince: anchor(requested),
			Source: "explicit_date",
		}, nil
	}
	daysBack := 1
	source := "default"
	if strings.Contains(strings.ToLower(prompt), "yesterday") {
		daysBack = 2
		source = "yesterday"
	}
	operationalDate := day(reference).AddDate(0, 0, -daysBack)
	return QueryWindow{
		OperationalDate: operationalDate, FailedSince: anchor(operationalDate),
		Source: source,
	}, nil
}

// Scope is the selected production region set.
type Scope struct {
	Regions []Region
}

// ResolveScope resolves US, CA, or both; generic requests default to both.
func ResolveScope(prompt string) Scope {
	usRequested := usPattern.MatchString(prompt)
	caRequested := caPattern.MatchString(prompt)
	switch {
	case usRequested && !caRequested:
		return Scope{Regions: []Region{US01}}
	case caRequested && !usRequested:
		return Scope{Regions: []Region{CA02}}
	default:
		return Scope{Regions: []Region{US01, CA02}}
	}
}

// Validate rejects empty and duplicate regional scopes.
func (s Scope) Validate() error {
	if len(s.Regions) == 0 {
		return fmt.Errorf("production-support scope must include a region")
	}
	seen := make(map[Region]struct{}, len(s.Regions))
	for _, region := range s.Regions {
		if _, exists := seen[region]; exists {
			return fmt.Errorf("production-support scope contains duplicate regions")
		}
		if region != US01 && region != CA02 {
			return fmt.Errorf("production-support scope contains unsupported region %q", region)
		}
		seen[region] = struct{}{}
	}
	return nil
}

func day(value time.Time) time.Time {
	utc := value.UTC()
	return time.Date(utc.Year(), utc.Month(), utc.Day(), 0, 0, 0, 0, time.UTC)
}

func anchor(value time.Time) time.Time {
	return time.Date(value.Year(), value.Month(), value.Day(), OperationalHour, 0, 0, 0, time.UTC)
}
