package formalmethod

import "fmt"

var scenarioTitles = map[string]string{
	"predicates": "Predicate thresholds and Boolean alternatives",
	"nulls":      "Null, blank, and missing-value behavior",
	"joins":      "Matched, unmatched, and composite join keys",
	"duplicates": "Duplicate multiplicity, grouping, and tied records",
	"dates":      "Date, window, ordering, and cast boundaries",
	"empty":      "Empty inputs and missing required datasets",
	"schema":     "Projection, dropped columns, and schema failures",
	"branches":   "Conditional branches, fallbacks, and errors",
	"arithmetic": "Numeric extremes, zero weights, and aggregation",
	"effects":    "Output datasets, copy destinations, and replay effects",
}

func scenarioCheck(c BoundaryClause, family string) BoundaryCheck {
	check := BoundaryCheck{ClauseID: c.ID}
	switch family {
	case "predicates":
		check.Given = "For each literal threshold, supply below, exactly equal, and above values; for > 0 include -1, 0, and 1. For equality or membership include matching and nonmatching values. Vary each Boolean operand independently while holding others so it can affect the result."
		check.Assert = "Compare exact retained row identities and duplicate counts with the source predicate, including strict versus inclusive boundaries and SQL UNKNOWN."
	case "nulls":
		check.Given = "Set each referenced field to null individually, then all to null; for strings also use empty, whitespace, case variants, and an unknown code. Keep other required fields valid."
		check.Assert = "Check source-specific row retention or fallback values; do not equate null with zero, blank, false, or a missing column."
	case "joins":
		check.Given = "Use matching keys, left-only keys, right-only keys, null keys on both sides, and a composite key matching all but one component."
		check.Assert = "For INNER retain only matches; for LEFT retain every left row with null right values when unmatched. Check the declared join mode, all key components, output schema, and complete row multiplicity."
	case "duplicates":
		check.Given = "Repeat identical rows; create 1:many and many:many keys, distinct rows sharing a key, null groups, and ties in every ordering field."
		check.Assert = "Check source-defined fan-out, grouping, and deduplication. If a tied survivor is unspecified, assert the permissible result set and report nondeterminism rather than inventing a winner."
	case "dates":
		check.Given = "Use one unit before, exactly at, and one unit after each cutoff; include future and null dates, malformed strings, month/year ends, leap day, and equal timestamps in a partition."
		check.Assert = "Check inclusive/exclusive window edges, ordering direction, partition isolation, timezone, and declared cast/error behavior. Determine the unit from source before binding fixtures."
	case "empty":
		check.Given = "Empty each input separately while preserving its schema, then empty all inputs; separately omit a required dataset and a required column."
		check.Assert = "Check empty output versus deliberate skip versus raised error, with exact output schema. Missing datasets and missing columns must not silently become ordinary empty relations."
	case "schema":
		check.Given = "Include kept, dropped, and unrelated columns; null values; an absent named column; renamed-column collisions; and conflicting non-key join columns."
		check.Assert = "Compare exact output column names and values; dropping a column must not drop its rows. Check failures against the source engine's behavior."
	case "branches":
		check.Given = "Exercise true and false outcomes independently, null/unknown conditions, each fallback, missing configuration, empty results, and declared error/exit paths."
		check.Assert = "Check which branch executes, which output ports are emitted, and which error/skip outcome occurs. Unsupported or unreachable branches remain explicit coverage gaps."
	case "arithmetic":
		check.Given = "Use -1, 0, 1, fractional values, mixed signs, all-null groups, a zero denominator/weight, cancellation to zero, and representable numeric extremes."
		check.Assert = "Compare sums, minima/maxima, averages, casts, and null/error results without rounding away differences; distinguish Python scalar errors from Spark ANSI-off null results."
	case "effects":
		check.Given = "Bind synthetic client, run date, dataset versions, and copy destinations; test output present/empty, each dispatch guard, replay, and prior target state. Intercept every physical write."
		check.Assert = "Compare emitted dataset identities, versions, partitions, row bags, write modes, and attached internal/client copies. No production write is part of a test."
	}
	check.Given = fmt.Sprintf("At %s:%d (%s): %s", c.Source.Path, c.Line, c.Kind, check.Given)
	return check
}

func planJobScenarios(job *BoundaryJob) {
	checks := map[string][]BoundaryCheck{}
	for _, c := range job.Clauses {
		for _, family := range c.Families {
			checks[family] = append(checks[family], BoundaryCheck{ClauseID: c.ID})
		}
	}
	// Every unit still needs context, input failure, and output-effect tests even
	// when its local source contains no explicit filter or write call.
	for _, family := range []string{"empty", "effects"} {
		checks[family] = append(checks[family], BoundaryCheck{Given: "For " + job.EntryPoint + ", bind the complete runner context and all declared inputs, including attached copy tasks.", Assert: scenarioCheck(BoundaryClause{}, family).Assert})
	}
	for _, family := range boundaryFamilies {
		if len(checks[family]) == 0 {
			continue
		}
		contextChecks := []BoundaryCheck{}
		count := 0
		for _, check := range checks[family] {
			if check.ClauseID == "" {
				contextChecks = append(contextChecks, check)
			} else {
				count++
			}
		}
		job.Scenarios = append(job.Scenarios, BoundaryScenario{ID: family, Title: scenarioTitles[family], Status: "planned_not_executed", Checks: contextChecks, ClauseFamily: family, ClauseChecks: count})
	}
}
