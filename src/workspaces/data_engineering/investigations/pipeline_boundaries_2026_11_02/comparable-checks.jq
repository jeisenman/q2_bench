# Verify the observed reproductions and negative controls, without calling
# application errors successful business-rule outputs.
(.results | length) == 9
and .source_modified == false
and .whole_job_coverage == false
and .results[0].status == "returned"
and .results[1].error_type == "ZeroDivisionError"
and .results[1].original_source_lines == [476]
and .results[2].error_type == "ZeroDivisionError"
and .results[2].original_source_lines == [489]
and (.results[3].output_rows | all(.StdLogTerm == null and .StdLogAmortizationTerm == 0))
and (.results[3].second_output_rows | all(.StdLogTerm == null and .StdLogAmortizationTerm == null))
and (.results[4].output_rows | all(.StdLogTerm == 0 and .StdLogAmortizationTerm == null))
and .results[5].output_rows[0].StdLogTerm == 0
and .results[5].output_rows[1].StdLogTerm == 1
and (.results[6].output_rows | all(.StdLogTerm == null))
and .results[7].output_rows[0].StdLogTerm == 0
and .results[7].output_rows[1].StdLogTerm == 1
and .results[8].observed_count == 2
