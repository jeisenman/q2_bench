// Command prepare creates synthetic differential cases from the compiled inventory.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"sort"
	"strings"
	"time"

	"github.com/jeisenman/q2_bench/workflows/formalmethod"
)

func main() {
	if err := prepare(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func prepare() error {
	inventory := flag.String("inventory", "var/lineage/formal-methods-20261030/inventory.json", "compiled source inventory")
	original := flag.String("original", "lineage/formal-cases/d2p.json", "existing opportunity cases")
	output := flag.String("output", "var/lineage/formal-methods-20261030/cases.json", "generated recipes")
	flag.Parse()
	var report formalmethod.Inventory
	b, err := os.ReadFile(*inventory)
	if err != nil {
		return err
	}
	if err = json.Unmarshal(b, &report); err != nil {
		return err
	}
	var cases []formalmethod.CaseRecipe
	b, err = os.ReadFile(*original)
	if err != nil {
		return err
	}
	if err = json.Unmarshal(b, &cases); err != nil {
		return err
	}
	for _, file := range report.Files {
		for _, m := range file.Methods {
			if m.Status != "compiled" || m.Function == "filter_account_level" {
				continue
			}
			generated, err := fixtures(m)
			if err != nil {
				return err
			}
			cases = append(cases, generated...)
		}
	}
	encoded, err := json.MarshalIndent(cases, "", "  ")
	if err != nil {
		return err
	}
	if err = os.WriteFile(*output, encoded, 0600); err != nil {
		return err
	}
	return json.NewEncoder(os.Stdout).Encode(map[string]any{"cases": len(cases), "output": *output})
}

func recipe(m formalmethod.Method, label string, b formalmethod.Bindings, schemas map[string]string) formalmethod.CaseRecipe {
	tables := []string{}
	for _, p := range m.Parameters {
		if p.Kind == formalmethod.Table {
			tables = append(tables, p.Name)
		}
	}
	return formalmethod.CaseRecipe{ID: m.Source.Path + ":" + m.Function + ":" + label, Commit: m.Source.Commit, Path: m.Source.Path, Function: m.Function, Tables: tables, Bindings: b, SparkSchemas: schemas}
}

func fixtures(m formalmethod.Method) ([]formalmethod.CaseRecipe, error) {
	switch m.Function {
	case "add_officer_codes", "join_regions_users", "clean_core_accounts_relationships", "filter_opportunities", "filter_loans_fs", "filter_for_financial_statement_type_is_strategic":
		return []formalmethod.CaseRecipe{typedCase(m)}, nil
	case "add_summary_columns_to_core_deposits", "add_summary_columns_to_core_others":
		return summaryCases(m), nil
	case "add_delivery_window_start_stats":
		return startCases(m), nil
	case "calculate_delivery_window_stats":
		return windowCases(m), nil
	case "join_datasets":
		return []formalmethod.CaseRecipe{joinCase(m)}, nil
	case "filter_to_time_window":
		rows := []formalmethod.Row{}
		for _, date := range []any{float64(20260930), float64(20261001), float64(20261015), float64(20261029), float64(20261030), nil} {
			rows = append(rows, formalmethod.Row{"DatePartition": date})
		}
		return []formalmethod.CaseRecipe{recipe(m, "inclusive-boundaries", formalmethod.Bindings{Tables: map[string][]formalmethod.Row{"data": rows}, Scalars: map[string]any{"earliest_date": float64(20261001), "latest_date": float64(20261029)}}, map[string]string{"data": "DatePartition double"})}, nil
	case "create_roe_and_pct_columns", "create_scorecard", "reduce", "cost_of_funds_percent_loan", "cost_of_funds_percent_deposits":
		return []formalmethod.CaseRecipe{numericCase(m)}, nil
	default:
		return nil, fmt.Errorf("compiled method %s in %s lacks comparison fixtures", m.Function, m.Source.Path)
	}
}

func summaryCases(m formalmethod.Method) []formalmethod.CaseRecipe {
	key, kind, value := "RelationshipGuid", "DepositType", "Balance"
	if strings.Contains(m.Source.Path, "other_products") {
		key = "TopLevelParentRelationshipId"
		kind = "OtherType"
		value = "StrategicNetIncome"
	}
	param := m.Parameters[0].Name
	rows := []formalmethod.Row{{key: "A", "DatePartition": "20261001", kind: "TYPE", value: float64(100)}, {key: "A", "DatePartition": "20261001", kind: "TYPE", value: float64(50)}, {key: "A", "DatePartition": "20261001", kind: "OTHER", value: float64(25)}, {key: nil, "DatePartition": "20261001", kind: "TYPE", value: float64(10)}}
	schema := map[string]string{param: key + " string, DatePartition string, " + kind + " string, " + value + " double"}
	normal := recipe(m, "grouping-and-null-keys", formalmethod.Bindings{Tables: map[string][]formalmethod.Row{param: rows}}, schema)
	empty := recipe(m, "empty-with-schema", formalmethod.Bindings{Tables: map[string][]formalmethod.Row{param: {}}, Schemas: map[string][]string{param: {key, "DatePartition", kind, value}}}, schema)
	return []formalmethod.CaseRecipe{normal, empty}
}

func startCases(m formalmethod.Method) []formalmethod.CaseRecipe {
	other := strings.Contains(m.Source.Path, "other_products")
	kind, measure := "DepositType", "CoreBalancePerDepositProductType"
	if other {
		kind = "OtherType"
		measure = "CoreNetIncomePerOtherType"
	}
	close, _ := time.Parse("2006-01-02", "2026-01-01")
	cases := []formalmethod.CaseRecipe{}
	for _, empty := range []bool{false, true} {
		rows := []formalmethod.Row{}
		days := []int{0, 1, 1, 36 * 30, 36*30 + 1}
		if empty {
			days = []int{0, 36*30 + 1}
		}
		for i, day := range days {
			rows = append(rows, formalmethod.Row{"OpportunityId": "A", kind: "TYPE", "OpportunityCloseDate": "2026-01-01", "OpportunityLastModified": "2026-10-01", "DatePartitionDate": close.AddDate(0, 0, day).Format("2006-01-02"), measure: float64(100 + i)})
		}
		base := []formalmethod.Row{{"OpportunityId": "A", kind: "TYPE"}, {"OpportunityId": "A", kind: "TYPE"}, {"OpportunityId": "missing", kind: "TYPE"}}
		scalars := map[string]any{"max_delivery_window_months": float64(36)}
		if other {
			scalars["metric"] = "NetIncome"
		}
		b := formalmethod.Bindings{Tables: map[string][]formalmethod.Row{"d2p": base, "forstats": rows}, Scalars: scalars}
		schemas := map[string]string{"d2p": "OpportunityId string, " + kind + " string", "forstats": "OpportunityId string, " + kind + " string, OpportunityCloseDate string, OpportunityLastModified string, DatePartitionDate string, " + measure + " double"}
		cases = append(cases, recipe(m, fmt.Sprintf("empty-window-%t", empty), b, schemas))
	}
	return cases
}

func numericCase(m formalmethod.Method) formalmethod.CaseRecipe {
	fields := map[string]bool{}
	var walk func(*formalmethod.Expression)
	walk = func(e *formalmethod.Expression) {
		if e.Op == "column" {
			fields[e.Name] = true
		}
		if e.Op == "col" {
			var name string
			if json.Unmarshal(e.Args[0].Value, &name) == nil {
				fields[name] = true
			}
		}
		for _, x := range e.Args {
			walk(x)
		}
		for _, x := range e.Keywords {
			walk(x)
		}
	}
	for _, s := range m.Steps {
		walk(s.Expression)
	}
	names := []string{}
	for name := range fields {
		names = append(names, name)
	}
	sort.Strings(names)
	rows := []formalmethod.Row{}
	for _, value := range []any{float64(2), float64(0), nil} {
		r := formalmethod.Row{}
		for _, name := range names {
			r[name] = value
		}
		rows = append(rows, r)
	}
	schema := []string{}
	for _, name := range names {
		schema = append(schema, "`"+name+"` double")
	}
	param := m.Parameters[0].Name
	return recipe(m, "positive-zero-null", formalmethod.Bindings{Tables: map[string][]formalmethod.Row{param: rows}}, map[string]string{param: strings.Join(schema, ", ")})
}

func windowCases(m formalmethod.Method) []formalmethod.CaseRecipe {
	other := strings.Contains(m.Source.Path, "other_products")
	kind, measure := "DepositType", "CoreBalancePerDepositProductType"
	if other {
		kind = "OtherType"
		measure = "CoreNetIncomePerOtherType"
	}
	cases := []formalmethod.CaseRecipe{}
	close, _ := time.Parse("2006-01-02", "2026-01-01")
	for _, months := range []int{6, 12, 24, 36} {
		for _, zero := range []bool{false, true} {
			records := []formalmethod.Row{}
			for _, days := range []int{0, 1, 2, months*30 - 1, months * 30, months*30 + 1} {
				weight := float64(1)
				if zero {
					weight = 0
				}
				records = append(records, formalmethod.Row{"OpportunityId": "A", kind: "TYPE", "CloseDateDate": "2026-01-01", "DatePartitionDate": close.AddDate(0, 0, days).Format("2006-01-02"), measure: float64(100), "DaysInEffect": weight})
			}
			base := []formalmethod.Row{{"OpportunityId": "A", kind: "TYPE"}, {"OpportunityId": "A", kind: "TYPE"}, {"OpportunityId": "missing", kind: "TYPE"}}
			scalars := map[string]any{"months_in_window": float64(months)}
			if other {
				scalars["metric"] = "NetIncome"
			}
			bindings := formalmethod.Bindings{Tables: map[string][]formalmethod.Row{"d2p_with_stats_start": base, "forstats_window": records}, Scalars: scalars}
			schema := map[string]string{"d2p_with_stats_start": "OpportunityId string, " + kind + " string", "forstats_window": "OpportunityId string, " + kind + " string, CloseDateDate string, DatePartitionDate string, " + measure + " double, DaysInEffect double"}
			cases = append(cases, recipe(m, fmt.Sprintf("window-%d-zero-weight-%t", months, zero), bindings, schema))
		}
	}
	return cases
}

func joinCase(m formalmethod.Method) formalmethod.CaseRecipe {
	tables := map[string][]formalmethod.Row{
		"user_data":     {{"user_id": "A", "security_profile_id": "S", "region_id": "R"}, {"user_id": "B", "security_profile_id": "S", "region_id": "R"}, {"user_id": "C", "security_profile_id": "missing", "region_id": "R"}},
		"security_data": {{"security_profile_id": "S", "security_profile": "Standard"}},
		"region_data":   {{"region_id": "R", "region": "North"}},
		"login_data":    {{"user_id": "A", "login": "1"}, {"user_id": "A", "login": "2"}},
	}
	schemas := map[string]string{"user_data": "user_id string, security_profile_id string, region_id string", "security_data": "security_profile_id string, security_profile string", "region_data": "region_id string, region string", "login_data": "user_id string, login string"}
	return recipe(m, "fanout-and-unmatched", formalmethod.Bindings{Tables: tables}, schemas)
}
