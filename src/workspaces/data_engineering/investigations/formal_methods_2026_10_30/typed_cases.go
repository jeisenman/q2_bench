package main

import "github.com/jeisenman/q2_bench/workflows/formalmethod"

func typedCase(m formalmethod.Method) formalmethod.CaseRecipe {
	b := formalmethod.Bindings{Tables: map[string][]formalmethod.Row{}, Scalars: map[string]any{}}
	schemas := map[string]string{}
	switch m.Function {
	case "add_officer_codes":
		b.Tables["opportunity_level"] = []formalmethod.Row{{"OwnerId": "A", "DatePartition": "20261001"}, {"OwnerId": "missing", "DatePartition": "20261001"}, {"OwnerId": nil, "DatePartition": "20261001"}}
		b.Tables["users"] = []formalmethod.Row{{"UserId": "A", "UserOfficerCodes": "FIRST", "DatePartition": "20261001"}, {"UserId": "A", "UserOfficerCodes": "SECOND", "DatePartition": "20261001"}, {"UserId": "A", "UserOfficerCodes": "OLD", "DatePartition": "20260930"}}
		schemas["opportunity_level"] = "OwnerId string, DatePartition string"
		schemas["users"] = "UserId string, UserOfficerCodes string, DatePartition string"
	case "join_regions_users":
		b.Tables["regions"] = []formalmethod.Row{{"RegionId": "R", "RegionName": "First", "DatePartition": "20261001"}, {"RegionId": "R", "RegionName": "Second", "DatePartition": "20261001"}}
		b.Tables["users"] = []formalmethod.Row{{"UserId": "A", "UserHomeRegionId": "R", "DatePartition": "20261001"}, {"UserId": "B", "UserHomeRegionId": "R", "DatePartition": "20260930"}}
		schemas["regions"] = "RegionId string, RegionName string, DatePartition string"
		schemas["users"] = "UserId string, UserHomeRegionId string, DatePartition string"
	case "clean_core_accounts_relationships":
		b.Tables["raw_relationships"] = []formalmethod.Row{{"Id": "R1", "ExternalIdentifier": "E", "Name": "First"}, {"Id": "R2", "ExternalIdentifier": "E", "Name": "Second"}}
		b.Tables["core_account"] = []formalmethod.Row{{"AccountId": "A", "RelationshipExternalIdentifier": "E"}, {"AccountId": "B", "RelationshipExternalIdentifier": "missing"}, {"AccountId": "C", "RelationshipExternalIdentifier": nil}}
		schemas["raw_relationships"] = "Id string, ExternalIdentifier string, Name string"
		schemas["core_account"] = "AccountId string, RelationshipExternalIdentifier string"
	case "filter_for_financial_statement_type_is_strategic":
		b.Tables["df"] = []formalmethod.Row{{"FinancialStatementType": "Strategic"}, {"FinancialStatementType": "FTP"}, {"FinancialStatementType": nil}}
		schemas["df"] = "FinancialStatementType string"
	case "filter_loans_fs":
		b.Tables["core_loans_fs"] = []formalmethod.Row{{"DaysSinceSave": float64(-1), "FinancialStatementTypeEnum": float64(0)}, {"DaysSinceSave": float64(30), "FinancialStatementTypeEnum": float64(0)}, {"DaysSinceSave": float64(31), "FinancialStatementTypeEnum": float64(0)}, {"DaysSinceSave": float64(1), "FinancialStatementTypeEnum": float64(1)}, {"DaysSinceSave": nil, "FinancialStatementTypeEnum": float64(0)}}
		b.Scalars["max_age_days"] = float64(0)
		b.Scalars["fs_type"] = float64(0)
		schemas["core_loans_fs"] = "DaysSinceSave double, FinancialStatementTypeEnum double"
	case "filter_opportunities":
		rows := []formalmethod.Row{}
		for _, date := range []any{"2026-10-01", "2026-11-01", "2025-10-29", "2025-10-28", nil} {
			rows = append(rows, formalmethod.Row{"LastModified": date, "OpportunityIsDeleted": false, "ScenarioType": "Pipeline", "OpportunityStageStatus": "ClosedWon", "AccountType": "Commercial"})
		}
		for _, change := range []formalmethod.Row{{"OpportunityIsDeleted": true}, {"OpportunityIsDeleted": nil}, {"ScenarioType": "Alternative"}, {"OpportunityStageStatus": "ClosedLost"}, {"AccountType": "Deposit"}} {
			r := formalmethod.Row{"LastModified": "2026-10-01", "OpportunityIsDeleted": false, "ScenarioType": "Pipeline", "OpportunityStageStatus": "ClosedWon", "AccountType": "Commercial"}
			for k, v := range change {
				r[k] = v
			}
			rows = append(rows, r)
		}
		b.Tables["opp_data"] = rows
		b.Scalars["max_age_days"] = float64(365)
		b.Scalars["window_start"] = "2026-10-29"
		schemas["opp_data"] = "LastModified string, OpportunityIsDeleted boolean, ScenarioType string, OpportunityStageStatus string, AccountType string"
	}
	return recipe(m, "typed-inputs-null-and-boundaries", b, schemas)
}
