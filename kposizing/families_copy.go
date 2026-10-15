package kposizing

import "fmt"

func (e *Estimator) estimateStorageAPICopy(profile Profile) (familyEstimate, error) {
	largest, source, err := largestFileEvidence(profile)
	if err != nil {
		return familyEstimate{}, fmt.Errorf(
			"largest file evidence is required for the hybrid storage/API implementation: %w",
			err,
		)
	}
	sdkBuffer, err := ceilMultiply(
		"storage API SDK buffer",
		largest,
		e.config.SDKDuplication,
	)
	if err != nil {
		return familyEstimate{}, err
	}
	components := []Component{
		baselineComponent(e.config.BaselineBytes),
		{Name: "api_request_metadata", Bytes: e.config.APIMetadataBytes},
		{Name: "sdk_file_buffer", Bytes: sdkBuffer},
	}
	evidence := []string{fmt.Sprintf("%s=%d", source, largest)}
	assumptions := []string{
		fmt.Sprintf("baseline_bytes=%d", e.config.BaselineBytes),
		fmt.Sprintf("api_metadata_bytes=%d", e.config.APIMetadataBytes),
		fmt.Sprintf("sdk_duplication=%s of largest file bytes", e.config.SDKDuplication),
	}

	if profile.APIBufferBytes != nil {
		components = append(
			components,
			Component{Name: "explicit_api_buffer", Bytes: *profile.APIBufferBytes},
		)
		evidence = append(evidence, fmt.Sprintf("api_buffer_bytes=%d", *profile.APIBufferBytes))
	}
	warnings := durationWarnings(profile, "dataset total primarily drives copy duration, not peak memory")
	warnings = append(
		warnings,
		"the current hybrid implementation may materialize the largest file even when the remote API supports server-side copy",
	)
	if profile.APIBufferBytes == nil {
		warnings = append(
			warnings,
			"api_buffer_bytes was not supplied; only the required largest-file SDK buffer is modeled",
		)
	}
	return familyEstimate{
		unit:        RequestedUnitRunner,
		components:  components,
		evidence:    evidence,
		assumptions: assumptions,
		warnings:    warnings,
	}, nil
}

func (e *Estimator) estimateThreadedByteCopy(profile Profile) (familyEstimate, error) {
	concurrency := e.config.DefaultCopyConcurrency
	assumptions := []string{
		fmt.Sprintf("baseline_bytes=%d", e.config.BaselineBytes),
	}
	evidence := []string{}
	if profile.CopyConcurrency == nil {
		assumptions = append(
			assumptions,
			fmt.Sprintf(
				"copy_concurrency=%d from configured default",
				e.config.DefaultCopyConcurrency,
			),
		)
	} else {
		concurrency = *profile.CopyConcurrency
		evidence = append(evidence, fmt.Sprintf("copy_concurrency=%d", concurrency))
	}

	activeFiles, source, err := concurrentFileEvidence(profile, concurrency)
	if err != nil {
		return familyEstimate{}, err
	}
	activeBytes, err := sumBytes("active concurrent file bytes", activeFiles)
	if err != nil {
		return familyEstimate{}, err
	}
	buffer, err := ceilMultiply("threaded SDK buffers", activeBytes, e.config.SDKDuplication)
	if err != nil {
		return familyEstimate{}, err
	}
	evidence = append(
		evidence,
		fmt.Sprintf("%s_count=%d", source, len(activeFiles)),
		fmt.Sprintf("active_concurrent_file_bytes=%d", activeBytes),
	)
	assumptions = append(
		assumptions,
		fmt.Sprintf("sdk_duplication=%s of active concurrent file bytes", e.config.SDKDuplication),
	)
	return familyEstimate{
		unit: RequestedUnitRunner,
		components: []Component{
			baselineComponent(e.config.BaselineBytes),
			{Name: "concurrent_sdk_buffers", Bytes: buffer},
		},
		evidence:    evidence,
		assumptions: assumptions,
		warnings: durationWarnings(
			profile,
			"dataset total and file count primarily drive copy duration after peak concurrency is fixed",
		),
	}, nil
}

func largestFileEvidence(profile Profile) (uint64, string, error) {
	if profile.LargestFileBytes != nil {
		if *profile.LargestFileBytes == 0 {
			return 0, "", fmt.Errorf("largest_file_bytes must be greater than zero")
		}
		return *profile.LargestFileBytes, "largest_file_bytes", nil
	}
	if len(profile.FileBytes) > 0 {
		return profile.FileBytes[0], "file_bytes[0]", nil
	}
	return 0, "", fmt.Errorf("largest_file_bytes or descending file_bytes is required")
}

func concurrentFileEvidence(profile Profile, concurrency int) ([]uint64, string, error) {
	if len(profile.TopConcurrentFileBytes) > 0 {
		expected := concurrency
		if len(profile.FileBytes) > 0 {
			expected = min(concurrency, len(profile.FileBytes))
		}
		if len(profile.TopConcurrentFileBytes) != expected {
			return nil, "", fmt.Errorf(
				"top_concurrent_file_bytes contains %d values; expected exactly %d",
				len(profile.TopConcurrentFileBytes),
				expected,
			)
		}
		return profile.TopConcurrentFileBytes, "top_concurrent_file_bytes", nil
	}
	if len(profile.FileBytes) == 0 {
		return nil, "", fmt.Errorf(
			"top_concurrent_file_bytes or descending file_bytes is required",
		)
	}
	count := min(concurrency, len(profile.FileBytes))
	return profile.FileBytes[:count], "file_bytes", nil
}

func durationWarnings(profile Profile, message string) []string {
	if profile.DatasetBytes == nil {
		return []string{message + "; dataset_bytes was not supplied"}
	}
	return []string{
		fmt.Sprintf("dataset_bytes=%d is duration evidence; %s", *profile.DatasetBytes, message),
	}
}
