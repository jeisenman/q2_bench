// Package outbound defines reviewed non-secret integration targets.
package outbound

// DatabricksTarget identifies one workspace and optional SQL warehouse.
type DatabricksTarget struct {
	Name           string
	WorkspaceID    string
	SQLWarehouseID string
}

// SnowflakeTarget identifies one environment and its access modes.
type SnowflakeTarget struct {
	Environment string
	AccessModes []string
}

// ADLSTarget identifies one ADLS Gen2 storage account.
type ADLSTarget struct {
	Environment string
	AccountName string
}

// OMSTarget identifies one production Log Analytics workspace.
type OMSTarget struct {
	Region        string
	WorkspaceName string
}

// InitiativeSmokeTest declares external dependencies for one initiative.
type InitiativeSmokeTest struct {
	InitiativeID       string
	SourcePaths        []string
	RequiresDatabricks bool
	RequiresSnowflake  bool
	RequiresADLS       bool
}

var (
	DatabricksRAPreprod = DatabricksTarget{
		Name: "pl-databricks-us-rapreprod-01", WorkspaceID: "7628572648057993",
	}
	DatabricksProd = DatabricksTarget{
		Name: "pl-databricks-us-prod-01", WorkspaceID: "3510128597187204",
		SQLWarehouseID: "434de6917eea68b6",
	}
	DatabricksTargets = map[string]DatabricksTarget{
		"data_engineering": DatabricksProd,
		"ra":               DatabricksRAPreprod,
	}
	SnowflakeTargets = []SnowflakeTarget{
		{Environment: "alpha", AccessModes: []string{"python_connector", "cortex"}},
		{Environment: "staging", AccessModes: []string{"python_connector", "cortex"}},
		{Environment: "prod_us", AccessModes: []string{"python_connector", "cortex"}},
	}
	ADLSTargets = map[string]ADLSTarget{
		"dev":     {Environment: "dev", AccountName: "pladls2usdatamartdev"},
		"staging": {Environment: "staging", AccountName: "pladls2usdatamartpreprod"},
		"prod_us": {Environment: "prod_us", AccountName: "pladls2usdatamartprod"},
		"prod_ca": {Environment: "prod_ca", AccountName: "pladls2cacdatamartprod"},
	}
	OMSTargets = map[string]OMSTarget{
		"us": {Region: "us", WorkspaceName: "pl-oms-us-primary"},
		"ca": {Region: "ca", WorkspaceName: "pl-oms-ca-primary"},
	}
)

// InitiativeSmokeTests is the reviewed source-to-integration matrix.
var InitiativeSmokeTests = []InitiativeSmokeTest{
	{
		InitiativeID:       "l3_catch_up_trigger",
		SourcePaths:        []string{"dags/precisionlender/dags/l3_trigger_dag_catchup.py"},
		RequiresDatabricks: true, RequiresADLS: true,
	},
	{
		InitiativeID: "opportunity_guidance_sharing_de_3207",
		SourcePaths: []string{
			"de-jobs/src/datamart/jobs/snowflake/evolutions/v1_0_26_de_3207.py",
		},
		RequiresSnowflake: true,
	},
	{
		InitiativeID: "ra_dataeng_metadata_ingestion",
		SourcePaths: []string{
			"de-jobs/src/datamart/jobs/ra/data_eng_relationship_metadata/",
			"de-jobs/src/datamart/jobs/ra/data_eng_core_loan_account_metadata/",
			"de-jobs/src/datamart/jobs/ra/data_eng_core_deposit_account_metadata/",
			"de-jobs/src/datamart/jobs/ra/data_eng_core_other_account_metadata/",
		},
		RequiresDatabricks: true, RequiresADLS: true,
	},
}
