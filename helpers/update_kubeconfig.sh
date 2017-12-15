#!/bin/sh
set -xe
cd "$( dirname "${BASH_SOURCE[0]}" )"
. ../variables

yum install jq -y

sed -e "s#\(.*--service-cluster-ip-range=\).*#\1${SRV_NETWORK}/${SRV_NETWORK_SIZE}#" /etc/kubernetes/manifests/kube-apiserver.yaml -i
sed -e "s#\(.*--service-cluster-ip-range=\).*#\1${SRV_NETWORK}/${SRV_NETWORK_SIZE}#" /etc/kubernetes/manifests/kube-controller-manager.yaml -i
sed -e "s#\(.*--cluster-cidr=\).*#\1${NOD_NETWORK_SPACE}/${NOD_NETWORK_SPACE_SIZE}#" /etc/kubernetes/manifests/kube-controller-manager.yaml -i
sed -e "s#\(.*image: \).*#\1$KUBE_ETCD_IMAGE#" /etc/kubernetes/manifests/etcd-cluster.yaml -i

CONTENT=$(kubectl get cm kubeconf -n kube-system -o json)
CONTENT=$(jq '.data."NOD_NETWORK_SPACE" = env.NOD_NETWORK_SPACE' <<<"$CONTENT")
CONTENT=$(jq '.data."NOD_NETWORK_SPACE_SIZE" = env.NOD_NETWORK_SPACE_SIZE' <<<"$CONTENT")
CONTENT=$(jq '.data."SRV_NETWORK" = env.SRV_NETWORK' <<<"$CONTENT")
CONTENT=$(jq '.data."SRV_NETWORK_SIZE" = env.SRV_NETWORK_SIZE' <<<"$CONTENT")

export kubeconf=$(find /etc/kubernetes/ -type f ! -wholename '/etc/kubernetes/pki/apiserver*' -print0 | tar -cf - --null --files-from - | base64 -w 0)
CONTENT=$(jq '.data."kubeconf" = env.kubeconf' <<<"$CONTENT")

echo $CONTENT > /tmp/kubeconf.json
kubectl replace cm -f /tmp/kubeconf.json
