#!/bin/bash
set -e
cd "$( dirname "${BASH_SOURCE[0]}" )"
. ../../variables

[[ -z $KUBE_ETCD_IMAGE ]] && exit 1
KUBEDIR=/etc/kubernetes/manifests
mkdir -p $KUBEDIR

echo "Put ourselfs in front of masters"
IFS=',' read -r -a array <<< "$masters"
MY_HOSTNAME=$(hostname)
echo "My hostname is $MY_HOSTNAME"
array=( "$MY_HOSTNAME ${array[@]/$MY_HOSTNAME}" )
echo ${array[@]}
state=new;

for master in ${array[@]};do
	etcd_cluster="$etcd_cluster,$master=https://$master:7001"
	eval "echo -e \"$(cat etcd-init.yaml.template)\"" | sed s'/--initial-cluster=,/--initial-cluster=/' > $KUBEDIR/etcd-init-$master.yaml
	state=existing
done

sed "s#KUBE_ETCD_IMAGE#$KUBE_ETCD_IMAGE#" etcd-cluster.yaml.template > $KUBEDIR/etcd-cluster.yaml
