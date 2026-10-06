package prodsupport

import (
	"fmt"
	"strings"

	"github.com/jeisenman/q2_bench/agents/oms"
)

// WorkloadKind identifies an Airflow workload category.
type WorkloadKind string

const (
	SparkBatch     WorkloadKind = "spark_batch"
	ContainerBatch WorkloadKind = "container_batch"
	OtherWorkload  WorkloadKind = "other"
)

var (
	sparkOperators = map[string]struct{}{
		"DatabricksRunNowOperator": {}, "DatabricksSubmitRunOperator": {},
		"SparkKubernetesOperator": {}, "SparkSubmitOperator": {},
	}
	containerOperators = map[string]struct{}{
		"BashOperator": {}, "KubernetesPodOperator": {}, "PythonOperator": {},
	}
)

// AirflowTaskMetadata is task metadata from the Airflow task endpoint.
type AirflowTaskMetadata struct {
	DAGID        string
	TaskID       string
	OperatorName string
}

// Validate rejects incomplete metadata.
func (m AirflowTaskMetadata) Validate() error {
	for name, value := range map[string]string{
		"dag_id": m.DAGID, "task_id": m.TaskID, "operator_name": m.OperatorName,
	} {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("%s must not be empty", name)
		}
	}
	return nil
}

// ClassifyWorkload classifies the exact Airflow operator class.
func ClassifyWorkload(metadata AirflowTaskMetadata) WorkloadKind {
	parts := strings.Split(metadata.OperatorName, ".")
	operator := parts[len(parts)-1]
	if _, exists := sparkOperators[operator]; exists {
		return SparkBatch
	}
	if _, exists := containerOperators[operator]; exists {
		return ContainerBatch
	}
	return OtherWorkload
}

// OMSEvidenceRoute is the regional OMS destination for a Spark workload.
type OMSEvidenceRoute struct {
	WorkspaceName string
	Table         string
}

// RouteOMSEvidence routes only Spark jobs to regional OMS.
func RouteOMSEvidence(workload WorkloadKind, region Region) *OMSEvidenceRoute {
	if workload != SparkBatch {
		return nil
	}
	omsRegion := oms.US
	if region == CA02 {
		omsRegion = oms.CA
	}
	workspace, err := oms.ResolveWorkspace(oms.Production, omsRegion)
	if err != nil {
		return nil
	}
	return &OMSEvidenceRoute{WorkspaceName: workspace.Name, Table: oms.OMSTable}
}
