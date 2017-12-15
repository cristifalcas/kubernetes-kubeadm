#!/bin/bash
set -ex
cd "$( dirname "${BASH_SOURCE[0]}" )"
mode="${1:-create}"
. ../../variables

sed s/NOD_NETWORK_SPACE/$NOD_NETWORK_SPACE/ -i configmap.yaml
sed s/NOD_NETWORK_SPACE_SIZE/$NOD_NETWORK_SPACE_SIZE/ -i configmap.yaml
sed "s#FLANNEL_IMAGE#$FLANNEL_IMAGE#" -i daemonset.yaml

kubectl $mode -f clusterrole.yaml
kubectl $mode -f clusterrolebinding.yaml
kubectl $mode -f configmap.yaml
kubectl $mode -f serviceaccount.yaml
kubectl $mode -f daemonset.yaml
