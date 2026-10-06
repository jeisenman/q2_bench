package domain

import (
	"fmt"
	"regexp"
	"strings"
)

var (
	cortexNamespace = regexp.MustCompile(`(?i)\bSNOWFLAKE\s*\.\s*CORTEX\s*\.`)
	commentBlock    = regexp.MustCompile(`(?s)/\*.*?\*/`)
	commentLine     = regexp.MustCompile(`--[^\n]*`)
	stringLiteral   = regexp.MustCompile(`'(?:[^']|'')*'`)
)

// PortabilityRule describes a construct that differs across warehouse backends.
type PortabilityRule struct {
	Name     string
	Pattern  *regexp.Regexp
	Guidance string
}

// PortabilityRules is the ordered set of cross-backend SQL restrictions.
var PortabilityRules = []PortabilityRule{
	{
		Name:    "cortex_call",
		Pattern: cortexNamespace,
		Guidance: "Cortex is model inference and is never deterministic. " +
			"Use the CortexInference port instead of embedding it in a query.",
	},
	{
		Name:     "variant_colon_path",
		Pattern:  regexp.MustCompile(`[A-Za-z_][A-Za-z0-9_]*\s*:\s*[A-Za-z_]`),
		Guidance: "Use arrow access such as payload->>'region' instead of payload:region.",
	},
	{
		Name:     "lateral_flatten",
		Pattern:  regexp.MustCompile(`(?i)\bLATERAL\s+FLATTEN\b`),
		Guidance: "Use unnest(...) instead of LATERAL FLATTEN.",
	},
	{
		Name:     "object_construct",
		Pattern:  regexp.MustCompile(`(?i)\bOBJECT_CONSTRUCT\s*\(`),
		Guidance: "Build JSON with json_object(...) instead of OBJECT_CONSTRUCT.",
	},
	{
		Name:    "dateadd_bare_part",
		Pattern: regexp.MustCompile(`(?i)\bDATEADD\s*\(\s*(year|quarter|month|week|day|hour|minute|second)\b`),
		Guidance: "DATEADD takes a bare date part that no macro can accept. " +
			"Use an INTERVAL expression instead.",
	},
	{
		Name:    "nondeterministic_clock",
		Pattern: regexp.MustCompile(`(?i)\b(CURRENT_TIMESTAMP|CURRENT_DATE|LOCALTIMESTAMP|SYSDATE|GETDATE|NOW)\b`),
		Guidance: "Reading the clock makes a result depend on when it ran. " +
			"Pass the operational window as a bound parameter instead.",
	},
	{
		Name:     "nondeterministic_value",
		Pattern:  regexp.MustCompile(`(?i)\b(RANDOM|RANDSTR|UUID_STRING|SEQ[1248])\s*\(`),
		Guidance: "Random and sequence values cannot be reproduced. Use fixture data.",
	},
}

// SQLPortabilityError reports every cross-backend violation in a statement.
type SQLPortabilityError struct {
	Violations []string
}

func (e *SQLPortabilityError) Error() string {
	return "statement is not portable across environments: " +
		strings.Join(e.Violations, "; ")
}

// StripSQLNoise removes comments and string literals before rule matching.
func StripSQLNoise(statement string) string {
	scanned := commentBlock.ReplaceAllString(statement, " ")
	scanned = commentLine.ReplaceAllString(scanned, " ")
	return stringLiteral.ReplaceAllString(scanned, "''")
}

// PortabilityViolations returns one message for each violated rule.
func PortabilityViolations(statement string) []string {
	scanned := StripSQLNoise(statement)
	violations := make([]string, 0)
	for _, rule := range PortabilityRules {
		if rule.Pattern.MatchString(scanned) {
			violations = append(violations, fmt.Sprintf("%s: %s", rule.Name, rule.Guidance))
		}
	}
	return violations
}

// RequirePortable rejects empty and cross-backend-incompatible SQL.
func RequirePortable(statement string) error {
	if strings.TrimSpace(statement) == "" {
		return fmt.Errorf("statement must not be empty")
	}
	violations := PortabilityViolations(statement)
	if len(violations) > 0 {
		return &SQLPortabilityError{Violations: violations}
	}
	return nil
}

// IsCortexCall reports whether the statement invokes Cortex inference.
func IsCortexCall(statement string) bool {
	return cortexNamespace.MatchString(StripSQLNoise(statement))
}
