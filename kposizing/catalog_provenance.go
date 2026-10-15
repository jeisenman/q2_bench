package kposizing

func inventoryRef() ProvenanceRef {
	return ProvenanceRef{
		Repository: "qtwo_bench",
		File:       "src/workspaces/data_engineering/skills/prod-support/scripts/build_kpo_size_notebook.py",
		Symbol:     "JOB_SOURCES",
	}
}

func raJobsRef() ProvenanceRef {
	return ProvenanceRef{
		Repository: "di-pipelines",
		File:       "dags/precisionlender/dags/task_groups/main/ra_jobs.py",
		Symbol:     "get_ra_jobs",
	}
}

func resourceAllocationRef(job string) ProvenanceRef {
	symbol := ""
	switch job {
	case "relationship_signals_time_series_agg_cp_to_snowflake":
		symbol = "RELATIONSHIP_SIGNALS_TIME_SERIES_AGG_CP_TO_SNOWFLAKE_ARGS"
	case "get_core_loan_amortization_tables":
		symbol = "CORE_LOAN_AMORTIZATION_OPERATOR_ARGS"
	case "get_assumption_sets":
		symbol = "ASSUMPTION_SETS_OPERATOR_ARGS"
	case "assumption_sets_to_internal_adls", "assumption_sets_to_client_datamart_adls":
		symbol = "ASSUMPTION_SETS_COPY_OPERATOR_ARGS"
	case "get_other_financial_statement_breakdown":
		symbol = "OTHER_FINANCIAL_STATEMENT_BREAKDOWN_ARGS and GET_OTHER_FINANCIAL_STATEMENT_BREAKDOWN_SPARK_CONF_OVERRIDES"
	case "get_loan_financial_statement_breakdown":
		symbol = "LOAN_FINANCIAL_STATEMENT_BREAKDOWN_ARGS and GET_LOAN_FINANCIAL_STATEMENT_BREAKDOWN_SPARK_CONF_OVERRIDES"
	case "get_core_deposit_accounts", "get_data_eng_core_deposit_account_metadata":
		symbol = "CORE_DEPOSIT_ACCOUNTS_ARGS and GET_CORE_DEPOSIT_ACCOUNTS_SPARK_CONF_OVERRIDES"
	case "high_quality_core_deposit_accounts_copy_client":
		symbol = "CORE_DEPOSIT_ACCOUNTS_COPY_ARGS"
	case "monthly_core_deposit_accounts_copy_client":
		symbol = "MONTHLY_CORE_DEPOSIT_ACCOUNTS_COPY_CLIENT_ARGS"
	case "get_treasury_financial_statement_breakdown":
		symbol = "TREASURY_FINANCIAL_STATEMENT_BREAKDOWN_ARGS"
	case "get_core_other_accounts", "get_data_eng_core_other_account_metadata":
		symbol = "CORE_OTHER_ACCOUNTS_OPERATOR_ARGS"
	case "get_commercial_loan_products":
		symbol = "COMMERCIAL_LOAN_PRODUCTS_ARGS"
	case "get_deposit_financial_statement_breakdown":
		symbol = "GET_DEPOSIT_FINANCIAL_STATEMENT_BREAKDOWN_SPARK_CONF_OVERRIDES"
	default:
		panic("unsupported resource-allocation catalog job " + job)
	}
	return ProvenanceRef{
		Repository: "di-pipelines",
		File:       "dag-utils/resource_allocation.py",
		Symbol:     symbol,
	}
}

func uploadImplementationRef() ProvenanceRef {
	return ProvenanceRef{
		Repository: "di-pyjobs",
		File:       "di_pyjobs/action/upload.py",
		Symbol:     "BytesToAdlsUpload.MAX_WORKERS",
	}
}

func adlsCopyJobRef() ProvenanceRef {
	return ProvenanceRef{
		Repository: "di-pyjobs",
		File:       "di_pyjobs/job/standard/batch.py",
		Symbol:     "AdlsToAdlsCopy",
	}
}

func byteCopyRef() ProvenanceRef {
	return ProvenanceRef{
		Repository: "di-pyjobs",
		File:       "di_pyjobs/action/move.py",
		Symbol:     "copy_adls_directory and MAX_COPY_THREADS",
	}
}

func storageAPIRef() ProvenanceRef {
	return ProvenanceRef{
		Repository: "di-pipelines",
		File:       "de-jobs/src/datamart/core/standard_jobs/adls_to_adls.py",
		Symbol:     "AdlsToAdlsCopyApi",
	}
}

func byteCopyAPIRef() ProvenanceRef {
	return ProvenanceRef{
		Repository: "di-pyjobs",
		File:       "di_pyjobs/action/move.py",
		Symbol:     "copy_adls_directory_api",
	}
}

func parquetToCSVRef() ProvenanceRef {
	return ProvenanceRef{
		Repository: "di-pipelines",
		File:       "de-jobs/src/datamart/core/standard_jobs/adls_to_adls.py",
		Symbol:     "ExternalSyncParquetToCsv",
	}
}

func storageRunnerChoices() []RunnerChoice {
	return populateChoices(
		batchPodRoutes(FamilyStorageAPICopy, configuredPodCondition),
		AuxiliaryInputNone,
		[]ProvenanceRef{storageAPIRef(), byteCopyAPIRef()},
	)
}

func populateCopyRunnerChoices(choices []RunnerChoice) []RunnerChoice {
	return populateChoices(
		choices,
		AuxiliaryInputNone,
		[]ProvenanceRef{adlsCopyJobRef(), byteCopyRef()},
	)
}

func populateAuditRunnerChoices(choices []RunnerChoice) []RunnerChoice {
	return populateChoices(
		choices,
		AuxiliaryInputNone,
		[]ProvenanceRef{parquetToCSVRef(), uploadImplementationRef()},
	)
}

func populateRARunnerChoices(
	job string,
	family TransformationFamily,
	defaultAuxiliary AuxiliaryInputPolicy,
	choices []RunnerChoice,
) []RunnerChoice {
	result := make([]RunnerChoice, len(choices))
	for index, choice := range choices {
		result[index] = choice
		if choice.Runner == RunnerSpark {
			result[index].AuxiliaryInput = AuxiliaryInputUnchanged
			result[index].Provenance = sparkProvenance(job)
			continue
		}
		result[index].AuxiliaryInput = defaultAuxiliary
		result[index].Provenance = raFamilyProvenance(job, family)
	}
	return result
}

func populateChoices(
	choices []RunnerChoice,
	auxiliary AuxiliaryInputPolicy,
	provenance []ProvenanceRef,
) []RunnerChoice {
	result := make([]RunnerChoice, len(choices))
	for index, choice := range choices {
		result[index] = choice
		result[index].AuxiliaryInput = auxiliary
		result[index].Provenance = append([]ProvenanceRef(nil), provenance...)
	}
	return result
}

func raFamilyProvenance(job string, family TransformationFamily) []ProvenanceRef {
	concrete := concreteRAJobRef(job)
	switch family {
	case FamilyChunkedPandas:
		return []ProvenanceRef{{
			Repository: "di-pipelines",
			File:       "de-jobs/src/datamart/core/standard_jobs/adls_to_adls_stream.py",
			Symbol:     "PandasChunkRunner and IncrementalCsvMoveWithChangeDetectionAndSchemaHandling",
		}, concrete}
	case FamilyWholeFilePandas:
		return []ProvenanceRef{{
			Repository: "di-pyjobs",
			File:       "di_pyjobs/job/standard/batch.py",
			Symbol:     "CsvMoveWithSchemaHandling",
		}, concrete}
	case FamilyChangeDetectionConcat:
		return []ProvenanceRef{{
			Repository: "di-pyjobs",
			File:       "di_pyjobs/job/standard/batch.py",
			Symbol:     "CsvMoveWithChangeDetectionAndSchemaHandling",
		}, concrete}
	case FamilyCompressedBase64JSON:
		return []ProvenanceRef{
			{
				Repository: "di-pipelines",
				File:       "de-jobs/src/datamart/transformations/aggregations.py",
				Symbol:     "csv_with_zip64_to_json",
			},
			concrete,
		}
	default:
		panic("unsupported RA catalog family " + string(family))
	}
}

func concreteRAJobRef(job string) ProvenanceRef {
	path, symbol := "", ""
	switch job {
	case "get_core_loan_amortization_tables":
		path, symbol = "core_loan_amortization_tables", "GetCoreLoanAmortizationTables"
	case "get_assumption_sets":
		path, symbol = "assumption_sets", "GetRaAssumptionSets"
	case "get_other_financial_statement_breakdown":
		path, symbol = "other_financial_statement_breakdown", "GetOtherFinancialStatementBreakdown"
	case "get_loan_financial_statement_breakdown":
		path, symbol = "loan_financial_statement_breakdown", "GetLoanFinancialStatementBreakdown"
	case "get_core_deposit_accounts":
		path, symbol = "core_deposit_accounts", "GetCoreDepositAccounts"
	case "get_data_eng_core_deposit_account_metadata":
		path, symbol = "data_eng_core_deposit_account_metadata", "GetDataEngCoreDepositAccountMetadata"
	case "get_treasury_financial_statement_breakdown":
		path, symbol = "treasury_financial_statement_breakdown", "GetTreasuryFinancialStatementBreakdown"
	case "get_core_other_accounts":
		path, symbol = "core_other_accounts", "GetCoreOtherAccounts"
	case "get_data_eng_core_other_account_metadata":
		path, symbol = "data_eng_core_other_account_metadata", "GetDataEngCoreOtherAccountMetadata"
	case "get_commercial_loan_products":
		path, symbol = "commercial_loan_products", "GetRaCommercialLoanProducts"
	case "get_treasury_assumptions":
		path, symbol = "treasury_assumptions", "GetTreasuryAssumptions"
	case "get_deposit_financial_statement_breakdown":
		path, symbol = "deposit_financial_statement_breakdown", "GetDepositFinancialStatementBreakdown"
	default:
		panic("unsupported RA catalog job " + job)
	}
	return ProvenanceRef{
		Repository: "di-pipelines",
		File:       "de-jobs/src/datamart/jobs/ra/" + path + "/to_datamart.py",
		Symbol:     symbol,
	}
}

func sparkProvenance(job string) []ProvenanceRef {
	path, symbol := "", ""
	switch job {
	case "get_core_deposit_accounts":
		path, symbol = "core_deposit_accounts.py", "CoreDepositAccountsIngestion"
	case "get_data_eng_core_deposit_account_metadata":
		path, symbol = "data_eng_core_deposit_account_metadata.py", "DataEngCoreDepositAccountMetadataIngestion"
	case "get_loan_financial_statement_breakdown":
		path, symbol = "loan_financial_statement_breakdown.py", "LoanFinancialStatementBreakdownIngestion"
	case "get_other_financial_statement_breakdown":
		path, symbol = "other_financial_statement_breakdown.py", "OtherFinancialStatementBreakdownIngestion"
	case "get_deposit_financial_statement_breakdown":
		path, symbol = "deposit_financial_statement_breakdown.py", "DepositFinancialStatementBreakdownIngestion"
	default:
		panic("unsupported Spark catalog job " + job)
	}
	return []ProvenanceRef{
		{
			Repository: "di-pipelines",
			File:       "ds-jobs/src/datascience_jobs/runner/spark_ra_csv_ingestion.py",
			Symbol:     "SparkRaCsvIngestionRunner",
		},
		{
			Repository: "di-pipelines",
			File:       "ds-jobs/src/datascience_jobs/jobs/primary_ingestion/ra/" + path,
			Symbol:     symbol,
		},
	}
}
