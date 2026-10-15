package kposizing

const (
	configuredPodCondition = "selected when reviewed operator args provide container_resources"
	backfillPodCondition   = configuredPodCondition + "; backfill selects this route"
	sparkCondition         = "selected when a reviewed Spark configuration override is present; backfill selects this route"
	largePodCondition      = "selected when resource_tags.size contains \"large\""
)

func staticJobTemplates() []JobTemplate {
	return []JobTemplate{
		historicalLatestTemplate(),
		raTemplate(
			"get_core_loan_amortization_tables",
			FamilyChunkedPandas,
			"PL_RelationshipAwareness/Core/CoreLoanAmortizationTables", "Primary", "v1.1",
			"DatabaseOutput/dbStagingCoreLoanAmortizationTables.csv",
			400_000, 400_000, 10, AuxiliaryInputUnchanged,
			k8sOnlyRoutes(FamilyChunkedPandas),
			[]string{"core_loan_amortization_tables"},
		),
		raTemplate(
			"get_assumption_sets",
			FamilyCompressedBase64JSON,
			"PL_RelationshipAwareness/Assumptions/AssumptionSets", "Primary", "v1.0",
			"ApplicationInput/AssumptionSets.csv",
			0, 800, 10, AuxiliaryInputNone,
			batchPodRoutes(FamilyCompressedBase64JSON, backfillPodCondition),
			[]string{"assumption_sets"},
		),
		copyTemplate(
			"assumption_sets_to_internal_adls",
			"PL_RelationshipAwareness/Assumptions/AssumptionSets", "Primary", "v1.0",
			backfillPodCondition,
		),
		copyTemplate(
			"assumption_sets_to_client_datamart_adls",
			"PL_RelationshipAwareness/Assumptions/AssumptionSets", "Primary", "v1.0",
			backfillPodCondition,
		),
		raTemplate(
			"get_other_financial_statement_breakdown",
			FamilyChunkedPandas,
			"PL_RelationshipAwareness/Core/OtherFinancialStatementsBreakdown", "Primary", "v1.0",
			"DatabaseOutput/dbStagingOtherAccountFinancialStatementBreakdowns.csv",
			150_000, 150_000, 10, AuxiliaryInputUnchanged,
			sparkRoutes(FamilyChunkedPandas, configuredPodCondition),
			[]string{"other_financial_statement_breakdown"},
		),
		raTemplate(
			"get_loan_financial_statement_breakdown",
			FamilyChunkedPandas,
			"PL_RelationshipAwareness/Core/LoanFinancialStatementsBreakdown", "Primary", "v1.0",
			"DatabaseOutput/dbStagingLoanFinancialStatementBreakdowns.csv",
			150_000, 150_000, 10, AuxiliaryInputUnchanged,
			sparkRoutes(FamilyChunkedPandas, configuredPodCondition),
			[]string{"loan_financial_statement_breakdown"},
		),
		raTemplate(
			"get_core_deposit_accounts",
			FamilyChangeDetectionConcat,
			"PL_RelationshipAwareness/Core/CoreDepositAccounts", "Primary", "v2.3",
			"DatabaseOutput/dbStagingCoreDepositAccounts.csv",
			0, 20_000, 10, AuxiliaryInputUnchangedConditional,
			sparkRoutes(FamilyChangeDetectionConcat, configuredPodCondition),
			[]string{"core_deposit_accounts"},
		),
		raTemplate(
			"get_data_eng_core_deposit_account_metadata",
			FamilyWholeFilePandas,
			"PL_RelationshipAwareness/Core/DataEngCoreDepositAccountMetadata", "Primary", "v1.0",
			"DataEngineering/DataEngCoreDepositAccountMetadata.csv",
			0, 100_000, 10, AuxiliaryInputNone,
			sparkRoutes(FamilyWholeFilePandas, configuredPodCondition),
			[]string{"data_eng_core_deposit_account_metadata"},
		),
		auditCopyTemplate(
			"high_quality_core_deposit_accounts_copy_client",
			"PL_RelationshipAwareness/Core/CoreDepositAccounts",
			[]string{"high_quality_core_deposit_accounts_cp_to_client"},
			"dags/precisionlender/dags/task_groups/derived/high_quality_core_deposit_accounts.py",
			"get_high_quality_core_deposit_accounts",
		),
		auditCopyTemplate(
			"monthly_core_deposit_accounts_copy_client",
			"PL_RelationshipAwareness/Core/CoreDepositAccountsMonthly",
			[]string{"monthly_core_deposit_accounts_cp_to_client"},
			"dags/precisionlender/dags/task_groups/derived/monthly_core_deposit_accounts.py",
			"get_monthly_core_deposit_accounts",
		),
		raTemplate(
			"get_treasury_financial_statement_breakdown",
			FamilyChunkedPandas,
			"PL_RelationshipAwareness/Core/TreasuryFinancialStatementBreakdown", "Primary", "v1.2",
			"DatabaseOutput/dbStagingTreasuryFinancialStatementBreakdowns.csv",
			300_000, 300_000, 10, AuxiliaryInputUnchanged,
			batchPodRoutes(FamilyChunkedPandas, configuredPodCondition),
			[]string{"treasury_financial_statement_breakdown"},
		),
		raTemplate(
			"get_core_other_accounts",
			FamilyChangeDetectionConcat,
			"PL_RelationshipAwareness/Core/CoreOtherAccounts", "Primary", "v2.1",
			"DatabaseOutput/dbStagingCoreOtherAccounts.csv",
			0, 18_305, 10, AuxiliaryInputUnchangedConditional,
			batchPodRoutes(FamilyChangeDetectionConcat, largePodCondition),
			[]string{"core_other_accounts"},
		),
		raTemplate(
			"get_data_eng_core_other_account_metadata",
			FamilyWholeFilePandas,
			"PL_RelationshipAwareness/Core/DataEngCoreOtherAccountMetadata", "Primary", "v1.0",
			"DataEngineering/DataEngCoreOtherAccountMetadata.csv",
			0, 100_000, 10, AuxiliaryInputNone,
			batchPodRoutes(FamilyWholeFilePandas, configuredPodCondition),
			[]string{"data_eng_core_other_account_metadata"},
		),
		raTemplate(
			"get_commercial_loan_products",
			FamilyCompressedBase64JSON,
			"PL_RelationshipAwareness/Assumptions/CommercialLoanProducts", "Primary", "v1.1",
			"ApplicationInput/CommercialLoanProducts.csv",
			0, 800, 10, AuxiliaryInputNone,
			batchPodRoutes(FamilyCompressedBase64JSON, configuredPodCondition),
			[]string{"commercial_loan_products"},
		),
		legacyTreasuryCopyTemplate(),
		legacyTreasuryGetTemplate(),
		legacyDepositFinancialStatementTemplate(),
	}
}

func historicalLatestTemplate() JobTemplate {
	return JobTemplate{
		Job:           "relationship_signals_time_series_agg_cp_to_snowflake",
		Aliases:       []string{"relationship_signals_time_series_agg_to_snowflake"},
		DefaultRunner: RunnerBatch,
		DefaultFamily: FamilyStorageAPICopy,
		RunnerChoices: storageRunnerChoices(),
		InputMode:     InputModeHistoricalLatest,
		InputNote: "HistoricalLatest selects the full VersionPartition root with no DatePartition; " +
			"collect recursive file_bytes for the full root and largest_file_bytes from that same root, " +
			"never latest-DatePartition evidence.",
		Source: SourceIdentity{
			Dataset: "PL_RelationshipAwareness/Relationships/RelationshipSignalsTimeSeriesAgg",
			Stage:   "Derived",
			Version: "v1.0",
		},
		AuxiliaryInput: AuxiliaryInputNone,
		Provenance: []ProvenanceRef{
			inventoryRef(),
			{
				Repository: "di-pipelines",
				File:       "dags/precisionlender/dags/task_groups/derived/relationship_signals.py",
				Symbol:     "relationship_signals_time_series_agg_cp_to_snowflake",
			},
			storageAPIRef(),
			byteCopyAPIRef(),
			resourceAllocationRef("relationship_signals_time_series_agg_cp_to_snowflake"),
		},
	}
}

func raTemplate(
	job string,
	family TransformationFamily,
	dataset string,
	stage string,
	version string,
	file string,
	chunkRows uint64,
	outputChunkRows uint64,
	uploadConcurrency int,
	auxiliary AuxiliaryInputPolicy,
	routes []RunnerChoice,
	aliases []string,
) JobTemplate {
	provenance := []ProvenanceRef{
		inventoryRef(),
		raJobsRef(),
		uploadImplementationRef(),
	}
	if job != "get_treasury_assumptions" {
		provenance = append(provenance, resourceAllocationRef(job))
	}
	return JobTemplate{
		Job:               job,
		Aliases:           aliases,
		DefaultRunner:     routes[0].Runner,
		DefaultFamily:     family,
		RunnerChoices:     populateRARunnerChoices(job, family, auxiliary, routes),
		InputMode:         InputModeRAFile,
		Source:            SourceIdentity{Dataset: dataset, Stage: stage, Version: version, File: file},
		AuxiliaryInput:    auxiliary,
		ChunkRows:         chunkRows,
		OutputChunkRows:   outputChunkRows,
		UploadConcurrency: uploadConcurrency,
		Provenance:        provenance,
	}
}

func copyTemplate(job string, dataset string, stage string, version string, podCondition string) JobTemplate {
	provenance := []ProvenanceRef{
		inventoryRef(),
		raJobsRef(),
		adlsCopyJobRef(),
		byteCopyRef(),
	}
	if job != "treasury_assumptions_to_internal_adls" {
		provenance = append(provenance, resourceAllocationRef(job))
	}
	return JobTemplate{
		Job:             job,
		DefaultRunner:   RunnerBatch,
		DefaultFamily:   FamilyThreadedByteCopy,
		RunnerChoices:   populateCopyRunnerChoices(batchPodRoutes(FamilyThreadedByteCopy, podCondition)),
		InputMode:       InputModeDatedHDM,
		Source:          SourceIdentity{Dataset: dataset, Stage: stage, Version: version},
		AuxiliaryInput:  AuxiliaryInputNone,
		CopyConcurrency: 10,
		Provenance:      provenance,
	}
}

func legacyTreasuryCopyTemplate() JobTemplate {
	template := copyTemplate(
		"treasury_assumptions_to_internal_adls",
		"PL_RelationshipAwareness/Assumptions/TreasuryAssumptions",
		"Primary",
		"v1.0",
		largePodCondition,
	)
	template.Provenance = []ProvenanceRef{raJobsRef(), adlsCopyJobRef(), byteCopyRef()}
	return template
}

func legacyTreasuryGetTemplate() JobTemplate {
	template := raTemplate(
		"get_treasury_assumptions",
		FamilyCompressedBase64JSON,
		"PL_RelationshipAwareness/Assumptions/TreasuryAssumptions", "Primary", "v1.0",
		"ApplicationInput/TreasuryAssumptions.csv",
		0, 100_000, 10, AuxiliaryInputNone,
		batchPodRoutes(FamilyCompressedBase64JSON, largePodCondition),
		[]string{"treasury_assumptions"},
	)
	template.Provenance = []ProvenanceRef{
		raJobsRef(),
		{
			Repository: "di-pipelines",
			File:       "de-jobs/src/datamart/jobs/ra/treasury_assumptions/to_datamart.py",
			Symbol:     "GetTreasuryAssumptions",
		},
		uploadImplementationRef(),
	}
	return template
}

func legacyDepositFinancialStatementTemplate() JobTemplate {
	template := raTemplate(
		"get_deposit_financial_statement_breakdown",
		FamilyChangeDetectionConcat,
		"PL_RelationshipAwareness/Core/DepositFinancialStatementsBreakdown", "Primary", "v1.1",
		"DatabaseOutput/dbStagingDepositFinancialStatementBreakdowns.csv",
		0, 100_000, 10, AuxiliaryInputUnchangedConditional,
		sparkRoutes(FamilyChangeDetectionConcat, largePodCondition),
		[]string{"deposit_financial_statement_breakdown"},
	)
	template.Provenance = []ProvenanceRef{
		raJobsRef(),
		{
			Repository: "di-pipelines",
			File:       "de-jobs/src/datamart/jobs/ra/deposit_financial_statement_breakdown/to_datamart.py",
			Symbol:     "GetDepositFinancialStatementBreakdown",
		},
		{
			Repository: "di-pipelines",
			File:       "ds-jobs/src/datascience_jobs/jobs/primary_ingestion/ra/deposit_financial_statement_breakdown.py",
			Symbol:     "DepositFinancialStatementBreakdownIngestion",
		},
		uploadImplementationRef(),
		resourceAllocationRef("get_deposit_financial_statement_breakdown"),
	}
	return template
}

func auditCopyTemplate(
	job string,
	dataset string,
	aliases []string,
	file string,
	symbol string,
) JobTemplate {
	return JobTemplate{
		Job:           job,
		Aliases:       aliases,
		DefaultRunner: RunnerBatch,
		DefaultFamily: FamilyParquetToCSV,
		RunnerChoices: populateAuditRunnerChoices(
			batchPodRoutes(FamilyParquetToCSV, configuredPodCondition),
		),
		InputMode:         InputModeAuditSelected,
		InputNote:         "Source partitions are selected from dataset audit records.",
		Source:            SourceIdentity{Dataset: dataset, Stage: "Derived", Version: "v3.6"},
		AuxiliaryInput:    AuxiliaryInputNone,
		OutputChunkRows:   500_000,
		UploadConcurrency: 10,
		Provenance: []ProvenanceRef{
			inventoryRef(),
			{Repository: "di-pipelines", File: file, Symbol: symbol},
			parquetToCSVRef(),
			uploadImplementationRef(),
			resourceAllocationRef(job),
		},
	}
}

func k8sOnlyRoutes(family TransformationFamily) []RunnerChoice {
	return []RunnerChoice{{Runner: RunnerK8sPod, Family: family}}
}

func batchPodRoutes(family TransformationFamily, podCondition string) []RunnerChoice {
	return []RunnerChoice{
		{Runner: RunnerBatch, Family: family},
		{Runner: RunnerK8sPod, Family: family, Condition: podCondition},
	}
}

func sparkRoutes(family TransformationFamily, podCondition string) []RunnerChoice {
	return []RunnerChoice{
		{Runner: RunnerBatch, Family: family},
		{Runner: RunnerK8sPod, Family: family, Condition: podCondition},
		{Runner: RunnerSpark, Family: FamilySparkCSVIngestion, Condition: sparkCondition},
	}
}
