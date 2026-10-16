package mcpapi

import (
	"context"
	"fmt"
	"strconv"
	"strings"
	"unicode/utf8"

	"github.com/google/jsonschema-go/jsonschema"
	"github.com/jeisenman/q2_bench/src/workspaces/data_engineering/kposizing"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

const bytesPerGiB = uint64(1024 * 1024 * 1024)
const maxKPOJobTemplates = 18

type kpoSizingInput struct {
	JobTemplate string             `json:"job_template,omitempty" jsonschema:"Optional canonical KPO job name or documented alias"`
	Workload    kposizing.Workload `json:"workload" jsonschema:"KPO workload and measured family-specific evidence"`
}

type kpoSizingOutput struct {
	Estimate         kposizing.Estimate     `json:"estimate"`
	EffectiveConfig  kposizing.Config       `json:"effective_config"`
	HumanReadableGiB kpoSizingGiB           `json:"human_readable_gib"`
	JobTemplate      *kposizing.JobTemplate `json:"job_template,omitempty"`
}

type kpoJobTemplatesInput struct {
	Job string `json:"job,omitempty" jsonschema:"Optional canonical KPO job name or documented alias"`
}

type kpoJobTemplatesOutput struct {
	Templates []kposizing.JobTemplate `json:"templates,omitempty"`
	Template  *kposizing.JobTemplate  `json:"template,omitempty"`
}

type kpoSizingGiB struct {
	RequestedUnit             kposizing.RequestedUnit `json:"requested_unit"`
	Components                []kpoComponentGiB       `json:"components"`
	Peak                      string                  `json:"peak"`
	Headroom                  string                  `json:"headroom"`
	Requested                 string                  `json:"requested"`
	RecommendedTier           string                  `json:"recommended_tier"`
	SupportedTiers            []string                `json:"supported_tiers"`
	EstimatedSparkClusterPeak string                  `json:"estimated_spark_cluster_peak,omitempty"`
}

type kpoComponentGiB struct {
	Name string `json:"name"`
	GiB  string `json:"gib"`
}

type kpoSizingAPI struct {
	estimator *kposizing.Estimator
}

func registerKPOSizing(server *mcp.Server) error {
	config := kposizing.DefaultConfig()
	estimator, err := kposizing.NewEstimator(config)
	if err != nil {
		return fmt.Errorf("register KPO sizing tool: %w", err)
	}
	sizingSchema, templatesSchema, err := kpoInputSchemas(config)
	if err != nil {
		return fmt.Errorf("register KPO sizing tool: %w", err)
	}
	api := &kpoSizingAPI{estimator: estimator}
	mcp.AddTool(server, &mcp.Tool{
		Name: "estimate_kpo_resources",
		Description: "Return a deterministic, static KPO memory and CPU planning estimate " +
			"from measured workload evidence and optional verified job-template defaults.",
		InputSchema: sizingSchema,
		Annotations: kpoReadOnlyAnnotations(),
	}, api.estimate)
	mcp.AddTool(server, &mcp.Tool{
		Name: "get_kpo_job_templates",
		Description: "List the bounded verified KPO job-template catalog or resolve one " +
			"canonical job name or documented alias.",
		InputSchema: templatesSchema,
		Annotations: kpoReadOnlyAnnotations(),
	}, api.getJobTemplates)
	return nil
}

func (a *kpoSizingAPI) estimate(
	_ context.Context,
	_ *mcp.CallToolRequest,
	input kpoSizingInput,
) (*mcp.CallToolResult, kpoSizingOutput, error) {
	workload := input.Workload
	var appliedTemplate *kposizing.JobTemplate
	name, err := boundedKPOJobName(input.JobTemplate, "job_template")
	if err != nil {
		return nil, kpoSizingOutput{}, err
	}
	if name != "" {
		var err error
		workload, err = kposizing.ApplyJobTemplateDefaults(name, workload)
		if err != nil {
			return nil, kpoSizingOutput{}, fmt.Errorf("apply KPO job template %q: %w", name, err)
		}
		template, lookupErr := kposizing.LookupJobTemplate(name)
		if lookupErr != nil {
			return nil, kpoSizingOutput{}, fmt.Errorf(
				"resolve applied KPO job template %q: %w",
				name,
				lookupErr,
			)
		}
		appliedTemplate = &template
	}
	estimate, err := a.estimator.Estimate(workload)
	if err != nil {
		return nil, kpoSizingOutput{}, fmt.Errorf("estimate KPO resources: %w", err)
	}
	config := a.estimator.Config()
	return nil, kpoSizingOutput{
		Estimate:         estimate,
		EffectiveConfig:  config,
		HumanReadableGiB: makeKPOSizingGiB(estimate, config),
		JobTemplate:      appliedTemplate,
	}, nil
}

func (a *kpoSizingAPI) getJobTemplates(
	_ context.Context,
	_ *mcp.CallToolRequest,
	input kpoJobTemplatesInput,
) (*mcp.CallToolResult, kpoJobTemplatesOutput, error) {
	job, err := boundedKPOJobName(input.Job, "job")
	if err != nil {
		return nil, kpoJobTemplatesOutput{}, err
	}
	if job == "" {
		templates := kposizing.ListJobTemplates()
		if len(templates) > maxKPOJobTemplates {
			return nil, kpoJobTemplatesOutput{}, fmt.Errorf(
				"KPO job-template catalog contains %d entries; MCP maximum is %d",
				len(templates),
				maxKPOJobTemplates,
			)
		}
		return nil, kpoJobTemplatesOutput{Templates: templates}, nil
	}
	template, err := kposizing.LookupJobTemplate(job)
	if err != nil {
		return nil, kpoJobTemplatesOutput{}, fmt.Errorf("get KPO job template: %w", err)
	}
	return nil, kpoJobTemplatesOutput{Template: &template}, nil
}

func kpoInputSchemas(config kposizing.Config) (*jsonschema.Schema, *jsonschema.Schema, error) {
	sizing, err := jsonschema.For[kpoSizingInput](nil)
	if err != nil {
		return nil, nil, fmt.Errorf("build sizing input schema: %w", err)
	}
	templates, err := jsonschema.For[kpoJobTemplatesInput](nil)
	if err != nil {
		return nil, nil, fmt.Errorf("build job-template input schema: %w", err)
	}
	workload, err := kpoSchemaProperty(sizing, "workload")
	if err != nil {
		return nil, nil, err
	}
	workload.Required = []string{"current_cpu_milli", "profile"}
	profile, err := kpoSchemaProperty(workload, "profile")
	if err != nil {
		return nil, nil, err
	}
	cpuEvidenceField, err := kpoSchemaProperty(workload, "cpu_evidence")
	if err != nil {
		return nil, nil, err
	}
	cpuEvidence, err := kpoSchemaObject(sizing, cpuEvidenceField)
	if err != nil {
		return nil, nil, fmt.Errorf("build input schema: cpu_evidence: %w", err)
	}
	rationale, err := kpoSchemaProperty(cpuEvidence, "rationale")
	if err != nil {
		return nil, nil, err
	}
	jobLimit := kposizing.MaxJobNameLength
	fileLimit := config.MaxFileEvidence
	rationaleLimit := kposizing.MaxCPURationaleLength
	rationale.MaxLength = &rationaleLimit
	for _, property := range []struct {
		schema *jsonschema.Schema
		name   string
	}{
		{sizing, "job_template"},
		{workload, "job"},
		{templates, "job"},
	} {
		field, fieldErr := kpoSchemaProperty(property.schema, property.name)
		if fieldErr != nil {
			return nil, nil, fieldErr
		}
		field.MaxLength = &jobLimit
	}
	for _, name := range []string{"file_bytes", "top_concurrent_file_bytes"} {
		field, fieldErr := kpoSchemaProperty(profile, name)
		if fieldErr != nil {
			return nil, nil, fieldErr
		}
		field.MaxItems = &fileLimit
	}
	return sizing, templates, nil
}

func kpoSchemaProperty(schema *jsonschema.Schema, name string) (*jsonschema.Schema, error) {
	property := schema.Properties[name]
	if property == nil {
		return nil, fmt.Errorf("build input schema: property %q is missing", name)
	}
	return property, nil
}

func kpoSchemaObject(
	root *jsonschema.Schema,
	schema *jsonschema.Schema,
) (*jsonschema.Schema, error) {
	if len(schema.Properties) > 0 {
		return schema, nil
	}
	if schema.Ref != "" {
		target, err := kpoSchemaRef(root, schema.Ref)
		if err != nil {
			return nil, err
		}
		return kpoSchemaObject(root, target)
	}
	for _, branches := range [][]*jsonschema.Schema{schema.AnyOf, schema.OneOf} {
		for _, branch := range branches {
			object, err := kpoSchemaObject(root, branch)
			if err == nil {
				return object, nil
			}
		}
	}
	return nil, fmt.Errorf("nullable schema has no object definition")
}

func kpoSchemaRef(root *jsonschema.Schema, ref string) (*jsonschema.Schema, error) {
	for _, prefix := range []struct {
		value string
		defs  map[string]*jsonschema.Schema
	}{
		{"#/$defs/", root.Defs},
		{"#/definitions/", root.Definitions},
	} {
		if name, ok := strings.CutPrefix(ref, prefix.value); ok {
			if schema := prefix.defs[name]; schema != nil {
				return schema, nil
			}
		}
	}
	return nil, fmt.Errorf("unsupported local schema reference %q", ref)
}

func boundedKPOJobName(value string, field string) (string, error) {
	if utf8.RuneCountInString(value) > kposizing.MaxJobNameLength {
		return "", fmt.Errorf(
			"%s must not exceed %d Unicode code points",
			field,
			kposizing.MaxJobNameLength,
		)
	}
	return strings.TrimSpace(value), nil
}

func kpoReadOnlyAnnotations() *mcp.ToolAnnotations {
	closedWorld := false
	return &mcp.ToolAnnotations{
		DestructiveHint: &closedWorld,
		IdempotentHint:  true,
		OpenWorldHint:   &closedWorld,
		ReadOnlyHint:    true,
	}
}

func makeKPOSizingGiB(estimate kposizing.Estimate, config kposizing.Config) kpoSizingGiB {
	components := make([]kpoComponentGiB, len(estimate.Components))
	for index, component := range estimate.Components {
		components[index] = kpoComponentGiB{
			Name: component.Name,
			GiB:  formatGiB(component.Bytes),
		}
	}
	tiers := make([]string, len(config.SupportedTiersBytes))
	for index, tier := range config.SupportedTiersBytes {
		tiers[index] = formatGiB(tier)
	}
	output := kpoSizingGiB{
		RequestedUnit:   estimate.RequestedUnit,
		Components:      components,
		Peak:            formatGiB(estimate.PeakBytes),
		Headroom:        formatGiB(estimate.HeadroomBytes),
		Requested:       formatGiB(estimate.RequestedBytes),
		RecommendedTier: formatGiB(estimate.RecommendedTierBytes),
		SupportedTiers:  tiers,
	}
	if estimate.Cluster != nil {
		output.EstimatedSparkClusterPeak = formatGiB(
			estimate.Cluster.EstimatedClusterPeakBytes,
		)
	}
	return output
}

func formatGiB(bytes uint64) string {
	value := float64(bytes) / float64(bytesPerGiB)
	return strconv.FormatFloat(value, 'f', 3, 64) + " GiB"
}
