package workflowharness

import "github.com/jeisenman/q2_bench/domain"

func domainAttributes(definition Definition, stageCount int) domain.Attributes {
	return domain.Attributes{
		{Name: "workflow_name", Value: definition.Name},
		{Name: "workflow_version", Value: definition.Version},
		{Name: "workflow_stage_count", Value: stageCount},
	}
}
