package kpomonitor

import (
	"fmt"
	"math"
	"strings"
)

const bytesPerGiB = float64(1024 * 1024 * 1024)

var sparklineRunes = []rune("▁▂▃▄▅▆▇█")

// GraphPoint is one graph-ready series value.
type GraphPoint struct {
	Sample     int     `json:"sample"`
	ObservedAt string  `json:"observed_at"`
	Series     string  `json:"series"`
	Value      float64 `json:"value"`
	Unit       string  `json:"unit"`
}

// MemoryGraph contains graph-ready values and a compact text rendering.
type MemoryGraph struct {
	Points  []GraphPoint `json:"points"`
	Preview string       `json:"preview"`
}

// BuildGraph renders total, driver, executor, and utilization trends.
func BuildGraph(samples []MemorySample) MemoryGraph {
	total := make([]float64, len(samples))
	driver := make([]float64, len(samples))
	executor := make([]float64, len(samples))
	utilization := make([]float64, len(samples))
	points := make([]GraphPoint, 0, len(samples)*4)
	for index, sample := range samples {
		total[index] = float64(sample.TotalMemoryBytes) / bytesPerGiB
		driver[index] = float64(sample.DriverMemoryBytes) / bytesPerGiB
		executor[index] = float64(sample.MaxExecutorMemoryBytes) / bytesPerGiB
		utilization[index] = sample.MaxUtilizationPercent
		for _, series := range []struct {
			name  string
			value float64
			unit  string
		}{
			{"total_memory", total[index], "GiB"},
			{"driver_memory", driver[index], "GiB"},
			{"max_executor_memory", executor[index], "GiB"},
			{"max_pod_utilization", utilization[index], "percent"},
		} {
			points = append(points, GraphPoint{
				Sample: index + 1, ObservedAt: sample.ObservedAt,
				Series: series.name, Value: series.value, Unit: series.unit,
			})
		}
	}
	lines := []string{"Memory profile (each row uses its own scale)"}
	lines = append(lines, graphLine("total GiB", total))
	lines = append(lines, graphLine("driver GiB", driver))
	lines = append(lines, graphLine("max executor GiB", executor))
	lines = append(lines, graphLine("max utilization %", utilization))
	return MemoryGraph{Points: points, Preview: strings.Join(lines, "\n")}
}

func graphLine(label string, values []float64) string {
	if len(values) == 0 {
		return fmt.Sprintf("%-18s no samples", label)
	}
	peak := 0.0
	for _, value := range values {
		if value > peak {
			peak = value
		}
	}
	var graph strings.Builder
	for _, value := range values {
		index := 0
		if peak > 0 {
			index = int(math.Round(value / peak * float64(len(sparklineRunes)-1)))
		}
		graph.WriteRune(sparklineRunes[index])
	}
	return fmt.Sprintf("%-18s %s peak %.3f", label, graph.String(), peak)
}
