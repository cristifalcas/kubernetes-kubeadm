#!/bin/sh
exit 0

# vars saved in cluster:
kubectl get cm kubeconf -n kube-system -o json | jq -r '.data | to_entries[] | .key' | sort

# get files saved from the init master
kubectl get cm kubeconf -n kube-system -o json | jq '.data."kubeconf"'| sed s/\"//g  | base64 -d | tar xvf -  -C /tmp/

kubectl get cm copy-config -n kube-system -o yaml
masters=$(kubectl get cm kubeconf -n kube-system -o json | jq '.data.masters')
CLUSTER_DOMAIN=$(kubectl get cm kubeconf -n kube-system -o json | jq '.data.CLUSTER_DOMAIN')
SRV_NETWORK=$(kubectl get cm kubeconf -n kube-system -o json | jq '.data.SRV_NETWORK')
SRV_NETWORK_SIZE=$(kubectl get cm kubeconf -n kube-system -o json | jq '.data.SRV_NETWORK_SIZE')
vip=$(kubectl get cm kubeconf -n kube-system -o json | jq '.data.vip')
