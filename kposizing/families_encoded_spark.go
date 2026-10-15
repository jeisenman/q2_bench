package kposizing

import "fmt"

func (e *Estimator) estimateCompressedBase64JSON(profile Profile) (familyEstimate, error) {
	encoded, err := requiredPositive(profile.EncodedBytes, "encoded_bytes")
	if err != nil {
		return familyEstimate{}, err
	}
	decoded, output, expansionEvidence, expansionAssumptions, err := e.resolveEncodedExpansion(
		profile,
		encoded,
	)
	if err != nil {
		return familyEstimate{}, err
	}
	transient := uint64(0)
	if profile.MaxRowDecodeTransientBytes != nil {
		transient = *profile.MaxRowDecodeTransientBytes
	}
	uploadBytes, uploadEvidence, err := e.uploadSerialization(profile)
	if err != nil {
		return familyEstimate{}, err
	}
	evidence := []string{fmt.Sprintf("encoded_bytes=%d", encoded)}
	evidence = append(evidence, expansionEvidence...)
	if profile.MaxRowDecodeTransientBytes != nil {
		evidence = append(
			evidence,
			fmt.Sprintf("max_row_decode_transient_bytes=%d", transient),
		)
	}
	evidence = append(evidence, uploadEvidence...)
	assumptions := []string{
		fmt.Sprintf("baseline_bytes=%d", e.config.BaselineBytes),
		fmt.Sprintf(
			"serialization_factor=%s of concurrent output chunk bytes",
			e.config.SerializationFactor,
		),
	}
	assumptions = append(assumptions, expansionAssumptions...)
	return familyEstimate{
		unit: RequestedUnitRunner,
		components: []Component{
			baselineComponent(e.config.BaselineBytes),
			{Name: "encoded_source_frame", Bytes: encoded},
			{Name: "decoded_object", Bytes: decoded},
			{Name: "output_object", Bytes: output},
			{Name: "max_row_decode_transient", Bytes: transient},
			{Name: "upload_serialization", Bytes: uploadBytes},
		},
		evidence:    evidence,
		assumptions: assumptions,
		warnings: []string{
			"compressed bytes alone are not safe memory evidence; decoded and output objects overlap",
		},
	}, nil
}

func (e *Estimator) resolveEncodedExpansion(
	profile Profile,
	encoded uint64,
) (uint64, uint64, []string, []string, error) {
	if profile.DecodedBytes != nil && *profile.DecodedBytes == 0 {
		return 0, 0, nil, nil, fmt.Errorf("decoded_bytes must be greater than zero")
	}
	if profile.OutputBytes != nil && *profile.OutputBytes == 0 {
		return 0, 0, nil, nil, fmt.Errorf("output_bytes must be greater than zero")
	}
	if profile.ExpansionRatio == nil &&
		(profile.DecodedBytes == nil || profile.OutputBytes == nil) {
		return 0, 0, nil, nil, fmt.Errorf(
			"decoded_bytes and output_bytes are required unless expansion_ratio bounds missing values",
		)
	}
	var bound uint64
	evidence := []string{}
	assumptions := []string{}
	if profile.ExpansionRatio != nil {
		var err error
		bound, err = ceilMultiply("encoded expansion bound", encoded, *profile.ExpansionRatio)
		if err != nil {
			return 0, 0, nil, nil, err
		}
		if profile.DecodedBytes != nil && *profile.DecodedBytes > bound {
			return 0, 0, nil, nil, fmt.Errorf(
				"decoded_bytes %d exceeds expansion_ratio bound %d",
				*profile.DecodedBytes,
				bound,
			)
		}
		if profile.OutputBytes != nil && *profile.OutputBytes > bound {
			return 0, 0, nil, nil, fmt.Errorf(
				"output_bytes %d exceeds expansion_ratio bound %d",
				*profile.OutputBytes,
				bound,
			)
		}
		evidence = append(evidence, fmt.Sprintf("expansion_ratio=%s", profile.ExpansionRatio))
		assumptions = append(
			assumptions,
			fmt.Sprintf(
				"expansion_ratio=%s is an upper bound for decoded and output bytes",
				profile.ExpansionRatio,
			),
		)
	}
	decoded := bound
	if profile.DecodedBytes != nil {
		decoded = *profile.DecodedBytes
		evidence = append(evidence, fmt.Sprintf("decoded_bytes=%d", decoded))
	}
	output := bound
	if profile.OutputBytes != nil {
		output = *profile.OutputBytes
		evidence = append(evidence, fmt.Sprintf("output_bytes=%d", output))
	}
	return decoded, output, evidence, assumptions, nil
}

func (e *Estimator) estimateParquetToCSV(profile Profile) (familyEstimate, error) {
	partition, err := requiredPositive(profile.LargestPartitionBytes, "largest_partition_bytes")
	if err != nil {
		return familyEstimate{}, err
	}
	expanded, err := requiredPositive(
		profile.ExpandedPartitionBytes,
		"expanded_partition_bytes",
	)
	if err != nil {
		return familyEstimate{}, err
	}
	partitionCount, err := requiredPositive(profile.PartitionCount, "partition_count")
	if err != nil {
		return familyEstimate{}, err
	}
	if profile.DatasetBytes != nil && *profile.DatasetBytes < partition {
		return familyEstimate{}, fmt.Errorf(
			"dataset_bytes %d cannot be smaller than largest_partition_bytes %d",
			*profile.DatasetBytes,
			partition,
		)
	}
	concatBytes, err := ceilMultiply(
		"parquet expanded concat bytes",
		expanded,
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
		fmt.Sprintf("largest_partition_bytes=%d", partition),
		fmt.Sprintf("expanded_partition_bytes=%d", expanded),
		fmt.Sprintf("partition_count=%d", partitionCount),
	}
	evidence = append(evidence, uploadEvidence...)
	warnings := []string{
		fmt.Sprintf(
			"partition_count=%d primarily drives duration because selected partitions are processed sequentially",
			partitionCount,
		),
	}
	if profile.DatasetBytes != nil {
		warnings = append(
			warnings,
			fmt.Sprintf("dataset_bytes=%d is duration evidence, not an aggregate peak term", *profile.DatasetBytes),
		)
	}
	return familyEstimate{
		unit: RequestedUnitRunner,
		components: []Component{
			baselineComponent(e.config.BaselineBytes),
			{Name: "largest_parquet_partition", Bytes: partition},
			{Name: "expanded_partition_concat", Bytes: concatBytes},
			{Name: "upload_serialization", Bytes: uploadBytes},
		},
		evidence: evidence,
		assumptions: []string{
			fmt.Sprintf("baseline_bytes=%d", e.config.BaselineBytes),
			"only the largest selected partition contributes to peak because processing is sequential",
			fmt.Sprintf("concat_factor=%s of the expanded largest partition", e.config.ConcatFactor),
			fmt.Sprintf(
				"serialization_factor=%s of concurrent output chunk bytes",
				e.config.SerializationFactor,
			),
		},
		warnings: warnings,
	}, nil
}

func (e *Estimator) estimateSparkCSVIngestion(profile Profile) (familyEstimate, error) {
	executors, err := requiredConcurrency(profile.SparkExecutorCount, "spark_executor_count")
	if err != nil {
		return familyEstimate{}, err
	}
	tasks, err := requiredConcurrency(profile.SparkTasksPerExecutor, "spark_tasks_per_executor")
	if err != nil {
		return familyEstimate{}, err
	}
	partition, err := requiredPositive(profile.SparkPartitionBytes, "spark_partition_bytes")
	if err != nil {
		return familyEstimate{}, err
	}
	cast, err := requiredPresent(
		profile.SparkCastBufferBytesPerTask,
		"spark_cast_buffer_bytes_per_task",
	)
	if err != nil {
		return familyEstimate{}, err
	}
	write, err := requiredPresent(
		profile.SparkWriteBufferBytesPerTask,
		"spark_write_buffer_bytes_per_task",
	)
	if err != nil {
		return familyEstimate{}, err
	}
	shuffle, err := requiredPresent(
		profile.SparkShuffleBytesPerExecutor,
		"spark_shuffle_bytes_per_executor",
	)
	if err != nil {
		return familyEstimate{}, err
	}
	cache, err := requiredPresent(
		profile.SparkCacheBytesPerExecutor,
		"spark_cache_bytes_per_executor",
	)
	if err != nil {
		return familyEstimate{}, err
	}
	partitionWorking, err := ceilMultiply(
		"spark partition working bytes",
		partition,
		e.config.SparkCSVWorkingFactor,
	)
	if err != nil {
		return familyEstimate{}, err
	}
	perTask, err := checkedAdd("spark per-task bytes", partitionWorking, cast, write)
	if err != nil {
		return familyEstimate{}, err
	}
	taskBytes, err := checkedMultiply("spark concurrent task bytes", perTask, uint64(tasks))
	if err != nil {
		return familyEstimate{}, err
	}
	components := []Component{
		baselineComponent(e.config.SparkJVMBaselineBytes),
		{Name: "concurrent_task_working_sets", Bytes: taskBytes},
		{Name: "executor_shuffle", Bytes: shuffle},
		{Name: "executor_cache", Bytes: cache},
	}
	peak, err := sumComponents(components)
	if err != nil {
		return familyEstimate{}, err
	}
	clusterPeak, err := checkedMultiply("estimated Spark cluster peak", peak, uint64(executors))
	if err != nil {
		return familyEstimate{}, err
	}
	return familyEstimate{
		unit:       RequestedUnitExecutor,
		components: components,
		cluster: &ClusterContext{
			ExecutorCount:             executors,
			EstimatedClusterPeakBytes: clusterPeak,
		},
		evidence: []string{
			fmt.Sprintf("spark_executor_count=%d", executors),
			fmt.Sprintf("spark_tasks_per_executor=%d", tasks),
			fmt.Sprintf("spark_partition_bytes=%d", partition),
			fmt.Sprintf("spark_cast_buffer_bytes_per_task=%d", cast),
			fmt.Sprintf("spark_write_buffer_bytes_per_task=%d", write),
			fmt.Sprintf("spark_shuffle_bytes_per_executor=%d", shuffle),
			fmt.Sprintf("spark_cache_bytes_per_executor=%d", cache),
		},
		assumptions: []string{
			fmt.Sprintf("spark_jvm_baseline_bytes=%d per executor", e.config.SparkJVMBaselineBytes),
			fmt.Sprintf(
				"spark_csv_working_factor=%s of partition bytes per task",
				e.config.SparkCSVWorkingFactor,
			),
			"all configured tasks per executor may hold working memory concurrently",
		},
		warnings: []string{
			"recommended tier applies to each executor; cluster memory is context and is not rounded into one pod tier",
			"partition count and total input bytes primarily drive duration after per-executor concurrency is fixed",
		},
	}, nil
}
