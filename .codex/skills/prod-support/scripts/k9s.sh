#!/usr/bin/env bash

set -euo pipefail

TENANT_ID="f06d459b-d935-4ad7-a9d3-a82343c4c9da"
SUBSCRIPTION_ID="71aa0ec0-8411-43a2-9908-ddd2add764eb"
RESOURCE_GROUP="pl-group-us-l3aks-prod-01"
CLUSTER_NAME="pl-aks-us-l3aks-prod-01"
KUBE_CONTEXT="l3-us01"

az login --tenant "$TENANT_ID"
az account set --subscription "$SUBSCRIPTION_ID"

az aks get-credentials \
  --resource-group "$RESOURCE_GROUP" \
  --name "$CLUSTER_NAME" \
  --subscription "$SUBSCRIPTION_ID" \
  --context "$KUBE_CONTEXT" \
  --format exec \
  --overwrite-existing

kubelogin convert-kubeconfig \
  --context "$KUBE_CONTEXT" \
  --login azurecli

kubectl config use-context "$KUBE_CONTEXT"

exec k9s --context "$KUBE_CONTEXT"
