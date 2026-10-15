package kposizing

import "fmt"

func (e *Estimator) estimateChunkedPandas(profile Profile) (familyEstimate, error) {
	changed, unchanged, err := sourcePair(profile)
	if err != nil {
		return familyEstimate{}, err
	}
	rowWidth, err := requiredPositive(profile.InMemoryRowWidthBytes, "in_memory_row_width_bytes")
	if err != nil {
		return familyEstimate{}, err
	}
	chunkRows, err := requiredPositive(profile.ChunkRows, "chunk_rows")
	if err != nil {
		return familyEstimate{}, err
	}
	effectiveChunkRows := chunkRows
	if profile.RowCount != nil {
		if *profile.RowCount == 0 {
			return familyEstimate{}, fmt.Errorf("row_count must be greater than zero when supplied")
		}
		effectiveChunkRows = min(*profile.RowCount, chunkRows)
	}
	rawChunk, err := checkedMultiply("pandas chunk bytes", effectiveChunkRows, rowWidth)
	if err != nil {
		return familyEstimate{}, err
	}
	frameBytes, err := ceilMultiply("pandas frame copies", rawChunk, e.config.FrameCopies)
	if err != nil {
		return familyEstimate{}, err
	}
	uploadBytes, uploadEvidence, err := e.uploadSerialization(profile)
	if err != nil {
		return familyEstimate{}, err
	}
	evidence := []string{
		fmt.Sprintf("changed_source_bytes=%d", changed),
		fmt.Sprintf("unchanged_source_bytes=%d", unchanged),
		fmt.Sprintf("chunk_rows=%d", chunkRows),
		fmt.Sprintf("effective_chunk_rows=%d", effectiveChunkRows),
		fmt.Sprintf("in_memory_row_width_bytes=%d", rowWidth),
	}
	effectiveAssumption := "effective_chunk_rows=chunk_rows because row_count was not supplied"
	if profile.RowCount != nil {
		evidence = append(evidence, fmt.Sprintf("row_count=%d", *profile.RowCount))
		effectiveAssumption = "effective_chunk_rows=min(row_count,chunk_rows)"
	}
	evidence = append(evidence, uploadEvidence...)
	warnings := []string{
		"chunked reads do not bound source-cache memory; whole changed and unchanged sources are included",
	}
	if profile.RowCount != nil {
		warnings = append(
			warnings,
			fmt.Sprintf("row_count=%d primarily drives chunk count and duration", *profile.RowCount),
		)
	}
	return familyEstimate{
		unit: RequestedUnitRunner,
		components: []Component{
			baselineComponent(e.config.BaselineBytes),
			{Name: "changed_source_cache", Bytes: changed},
			{Name: "unchanged_source_cache", Bytes: unchanged},
			{Name: "chunk_frame_copies", Bytes: frameBytes},
			{Name: "upload_serialization", Bytes: uploadBytes},
		},
		evidence: evidence,
		assumptions: []string{
			fmt.Sprintf("baseline_bytes=%d", e.config.BaselineBytes),
			fmt.Sprintf("frame_copies=%s of one in-memory chunk", e.config.FrameCopies),
			effectiveAssumption,
			fmt.Sprintf(
				"serialization_factor=%s of concurrent output chunk bytes",
				e.config.SerializationFactor,
			),
		},
		warnings: warnings,
	}, nil
}

func (e *Estimator) estimateWholeFilePandas(profile Profile) (familyEstimate, error) {
	sourceBytes, sourceName, err := largestFileEvidence(profile)
	if err != nil {
		return familyEstimate{}, err
	}
	expanded, err := requiredPositive(profile.ExpandedBytes, "expanded_bytes")
	if err != nil {
		return familyEstimate{}, err
	}
	if err := validateExpandedRows(profile, expanded); err != nil {
		return familyEstimate{}, err
	}
	concatBytes, err := ceilMultiply("whole-file concat bytes", expanded, e.config.ConcatFactor)
	if err != nil {
		return familyEstimate{}, err
	}
	uploadBytes, uploadEvidence, err := e.uploadSerialization(profile)
	if err != nil {
		return familyEstimate{}, err
	}
	evidence := []string{
		fmt.Sprintf("%s=%d", sourceName, sourceBytes),
		fmt.Sprintf("expanded_bytes=%d", expanded),
	}
	evidence = append(evidence, uploadEvidence...)
	return familyEstimate{
		unit: RequestedUnitRunner,
		components: []Component{
			baselineComponent(e.config.BaselineBytes),
			{Name: "source_cache", Bytes: sourceBytes},
			{Name: "expanded_concat_frames", Bytes: concatBytes},
			{Name: "upload_serialization", Bytes: uploadBytes},
		},
		evidence: evidence,
		assumptions: []string{
			fmt.Sprintf("baseline_bytes=%d", e.config.BaselineBytes),
			fmt.Sprintf("concat_factor=%s of expanded input bytes", e.config.ConcatFactor),
			fmt.Sprintf(
				"serialization_factor=%s of concurrent output chunk bytes",
				e.config.SerializationFactor,
			),
		},
		warnings: durationWarnings(
			profile,
			"dataset total and file count primarily drive duration when files are processed sequentially",
		),
	}, nil
}

func (e *Estimator) estimateChangeDetectionConcat(profile Profile) (familyEstimate, error) {
	changedSource, unchangedSource, err := sourcePair(profile)
	if err != nil {
		return familyEstimate{}, err
	}
	changedExpanded, err := requiredPresent(
		profile.ChangedExpandedBytes,
		"changed_expanded_bytes",
	)
	if err != nil {
		return familyEstimate{}, err
	}
	unchangedExpanded, err := requiredPresent(
		profile.UnchangedExpandedBytes,
		"unchanged_expanded_bytes",
	)
	if err != nil {
		return familyEstimate{}, err
	}
	if err := validateSourceExpansionPair(
		changedSource,
		changedExpanded,
		"changed",
	); err != nil {
		return familyEstimate{}, err
	}
	if err := validateSourceExpansionPair(
		unchangedSource,
		unchangedExpanded,
		"unchanged",
	); err != nil {
		return familyEstimate{}, err
	}
	totalExpanded, err := checkedAdd(
		"change-detection expanded bytes",
		changedExpanded,
		unchangedExpanded,
	)
	if err != nil {
		return familyEstimate{}, err
	}
	if totalExpanded == 0 {
		return familyEstimate{}, fmt.Errorf("changed and unchanged expanded bytes cannot both be zero")
	}
	concatBytes, err := ceilMultiply(
		"change-detection concat bytes",
		totalExpanded,
		e.config.ConcatFactor,
	)
	if err != nil {
		return familyEstimate{}, err
	}
	uploadBytes, uploadEvidence, err := e.uploadSerialization(profile)
	if err != nil {
		return familyEstimate{}, err
	}
	evidence := []string{
		fmt.Sprintf("changed_source_bytes=%d", changedSource),
		fmt.Sprintf("unchanged_source_bytes=%d", unchangedSource),
		fmt.Sprintf("changed_expanded_bytes=%d", changedExpanded),
		fmt.Sprintf("unchanged_expanded_bytes=%d", unchangedExpanded),
	}
	evidence = append(evidence, uploadEvidence...)
	return familyEstimate{
		unit: RequestedUnitRunner,
		components: []Component{
			baselineComponent(e.config.BaselineBytes),
			{Name: "changed_source_cache", Bytes: changedSource},
			{Name: "unchanged_source_cache", Bytes: unchangedSource},
			{Name: "expanded_concat_frames", Bytes: concatBytes},
			{Name: "upload_serialization", Bytes: uploadBytes},
		},
		evidence: evidence,
		assumptions: []string{
			fmt.Sprintf("baseline_bytes=%d", e.config.BaselineBytes),
			fmt.Sprintf("concat_factor=%s of changed plus unchanged expanded bytes", e.config.ConcatFactor),
			fmt.Sprintf(
				"serialization_factor=%s of concurrent output chunk bytes",
				e.config.SerializationFactor,
			),
		},
		warnings: []string{
			"both changed and unchanged source caches remain live during concat",
		},
	}, nil
}

func sourcePair(profile Profile) (uint64, uint64, error) {
	changed, err := requiredPresent(profile.ChangedSourceBytes, "changed_source_bytes")
	if err != nil {
		return 0, 0, err
	}
	unchanged, err := requiredPresent(profile.UnchangedSourceBytes, "unchanged_source_bytes")
	if err != nil {
		return 0, 0, err
	}
	total, err := checkedAdd("changed and unchanged source bytes", changed, unchanged)
	if err != nil {
		return 0, 0, err
	}
	if total == 0 {
		return 0, 0, fmt.Errorf("changed and unchanged source bytes cannot both be zero")
	}
	return changed, unchanged, nil
}

func validateSourceExpansionPair(source, expanded uint64, name string) error {
	if source == 0 && expanded != 0 {
		return fmt.Errorf("%s_expanded_bytes must be zero when %s_source_bytes is zero", name, name)
	}
	if source != 0 && expanded == 0 {
		return fmt.Errorf("%s_expanded_bytes must be greater than zero when source bytes are present", name)
	}
	return nil
}

func validateExpandedRows(profile Profile, expanded uint64) error {
	if profile.RowCount == nil && profile.InMemoryRowWidthBytes == nil {
		return nil
	}
	if profile.RowCount == nil || profile.InMemoryRowWidthBytes == nil {
		return fmt.Errorf(
			"row_count and in_memory_row_width_bytes must be supplied together for whole-file validation",
		)
	}
	rows, err := requiredPositive(profile.RowCount, "row_count")
	if err != nil {
		return err
	}
	width, err := requiredPositive(profile.InMemoryRowWidthBytes, "in_memory_row_width_bytes")
	if err != nil {
		return err
	}
	derived, err := checkedMultiply("row-derived expanded bytes", rows, width)
	if err != nil {
		return err
	}
	if derived != expanded {
		return fmt.Errorf(
			"expanded_bytes %d contradicts row_count*in_memory_row_width_bytes %d",
			expanded,
			derived,
		)
	}
	return nil
}

func (e *Estimator) uploadSerialization(profile Profile) (uint64, []string, error) {
	concurrency, err := requiredConcurrency(profile.UploadConcurrency, "upload_concurrency")
	if err != nil {
		return 0, nil, err
	}
	rows, err := requiredPositive(profile.OutputChunkRows, "output_chunk_rows")
	if err != nil {
		return 0, nil, err
	}
	width, err := requiredPositive(profile.OutputRowWidthBytes, "output_row_width_bytes")
	if err != nil {
		return 0, nil, err
	}
	chunkBytes, err := checkedMultiply("output chunk bytes", rows, width)
	if err != nil {
		return 0, nil, err
	}
	concurrentBytes, err := checkedMultiply(
		"concurrent output chunk bytes",
		chunkBytes,
		uint64(concurrency),
	)
	if err != nil {
		return 0, nil, err
	}
	serialized, err := ceilMultiply(
		"upload serialization bytes",
		concurrentBytes,
		e.config.SerializationFactor,
	)
	if err != nil {
		return 0, nil, err
	}
	return serialized, []string{
		fmt.Sprintf("upload_concurrency=%d", concurrency),
		fmt.Sprintf("output_chunk_rows=%d", rows),
		fmt.Sprintf("output_row_width_bytes=%d", width),
	}, nil
}
