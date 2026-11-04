package dataingress

import (
	"context"
	"github.com/jeisenman/q2_bench/workflows/formallineage/source"
	"testing"
)

func TestIngressBoundary(t *testing.T) {
	b := []byte("class EngineCalls { void Run() { client.Calculate(); } }")
	pin := "0123456789012345678901234567890123456789"
	receipt, _ := source.Receipt(pin, "EngineCalls.cs", b)
	result, err := Parse(context.Background(), "pl-dataingress", receipt, b)
	if err != nil || result.PredictionReady || len(result.Declarations) != 1 {
		t.Fatalf("ingress %v %+v", err, result)
	}
	if _, err := Parse(context.Background(), "pl-application", receipt, b); err == nil {
		t.Fatal("accepted application outside proxy boundary")
	}
	receipt, _ = source.Receipt(pin, "PrecisionLender.Common.Engine.Proxy/ServiceWrappers/Wrapper.cs", b)
	if _, err := Parse(context.Background(), "pl-application", receipt, b); err != nil {
		t.Fatal(err)
	}
	receipt, _ = source.Receipt(pin, "EngineCalls.py", b)
	if _, err := Parse(context.Background(), "pl-dataingress", receipt, b); err == nil {
		t.Fatal("accepted wrong language")
	}
}
