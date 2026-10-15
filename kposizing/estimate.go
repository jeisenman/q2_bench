package kposizing

import "fmt"

type familyEstimate struct {
	unit        RequestedUnit
	components  []Component
	cluster     *ClusterContext
	evidence    []string
	assumptions []string
	warnings    []string
}

// Estimate validates a workload and returns its deterministic recommendation.
func (e *Estimator) Estimate(workload Workload) (Estimate, error) {
	if e == nil {
		return Estimate{}, fmt.Errorf("estimator must not be nil")
	}
	if err := validateWorkload(workload, e.config); err != nil {
		return Estimate{}, fmt.Errorf("invalid workload: %w", err)
	}
	family, err := e.estimateFamily(workload)
	if err != nil {
		return Estimate{}, fmt.Errorf("estimate %s: %w", workload.Family, err)
	}
	peak, err := sumComponents(family.components)
	if err != nil {
		return Estimate{}, err
	}
	headroom, err := ceilMultiply("headroom bytes", peak, e.config.Headroom)
	if err != nil {
		return Estimate{}, err
	}
	requested, err := checkedAdd("requested memory", peak, headroom)
	if err != nil {
		return Estimate{}, err
	}
	tier, err := e.roundTier(requested)
	if err != nil {
		return Estimate{}, err
	}
	recommendedCPU, cpuRationale, err := validateCPU(workload)
	if err != nil {
		return Estimate{}, err
	}

	assumptions := append([]string(nil), family.assumptions...)
	assumptions = append(
		assumptions,
		fmt.Sprintf("headroom=%s of peak bytes, rounded upward", e.config.Headroom),
		"recommended tier is the smallest configured tier not below requested bytes",
	)
	warnings := append([]string(nil), family.warnings...)
	warnings = append(
		warnings,
		"memory sizing does not imply a CPU change; CPU changes require explicit evidence",
	)

	return Estimate{
		Job:                  workload.Job,
		Runner:               workload.Runner,
		Family:               workload.Family,
		RequestedUnit:        family.unit,
		Components:           append([]Component(nil), family.components...),
		PeakBytes:            peak,
		HeadroomBytes:        headroom,
		RequestedBytes:       requested,
		RecommendedTierBytes: tier,
		CurrentCPUMilli:      workload.CurrentCPUMilli,
		RecommendedCPUMilli:  recommendedCPU,
		CPURationale:         cpuRationale,
		Cluster:              family.cluster,
		Evidence:             nonNilStrings(family.evidence),
		Assumptions:          nonNilStrings(assumptions),
		Warnings:             nonNilStrings(warnings),
	}, nil
}

func (e *Estimator) estimateFamily(workload Workload) (familyEstimate, error) {
	switch workload.Family {
	case FamilyStorageAPICopy:
		return e.estimateStorageAPICopy(workload.Profile)
	case FamilyThreadedByteCopy:
		return e.estimateThreadedByteCopy(workload.Profile)
	case FamilyChunkedPandas:
		return e.estimateChunkedPandas(workload.Profile)
	case FamilyWholeFilePandas:
		return e.estimateWholeFilePandas(workload.Profile)
	case FamilyChangeDetectionConcat:
		return e.estimateChangeDetectionConcat(workload.Profile)
	case FamilyCompressedBase64JSON:
		return e.estimateCompressedBase64JSON(workload.Profile)
	case FamilyParquetToCSV:
		return e.estimateParquetToCSV(workload.Profile)
	case FamilySparkCSVIngestion:
		return e.estimateSparkCSVIngestion(workload.Profile)
	default:
		return familyEstimate{}, fmt.Errorf("transformation family %q is unsupported", workload.Family)
	}
}

func (e *Estimator) roundTier(requested uint64) (uint64, error) {
	for _, tier := range e.config.SupportedTiersBytes {
		if tier >= requested {
			return tier, nil
		}
	}
	return 0, &TierExceededError{
		RequestedBytes:   requested,
		LargestTierBytes: e.config.SupportedTiersBytes[len(e.config.SupportedTiersBytes)-1],
	}
}

func sumComponents(components []Component) (uint64, error) {
	values := make([]uint64, len(components))
	for index, component := range components {
		values[index] = component.Bytes
	}
	peak, err := sumBytes("peak memory", values)
	if err != nil {
		return 0, err
	}
	return peak, nil
}

func nonNilStrings(values []string) []string {
	if values == nil {
		return []string{}
	}
	return values
}

func baselineComponent(bytes uint64) Component {
	return Component{Name: "baseline", Bytes: bytes}
}
