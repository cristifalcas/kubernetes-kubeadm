#!/bin/bash
set -e
set -x
cd "$( dirname "${BASH_SOURCE[0]}" )"
mode="${1:-create}"
. ../../variables

kubectl $mode -f clusterrole.yaml
kubectl $mode -f clusterrolebinding.yaml
kubectl $mode -f configmap.yaml
kubectl $mode -f serviceaccount.yaml
kubectl $mode -f daemonset.yaml
