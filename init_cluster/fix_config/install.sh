#!/bin/bash
set -ex

VIP=$1
[[ -z "$VIP" ]] && exit 1

function wait_for_api() {
	until kubectl get nodes | grep "$(hostname)[[:space:]]*Ready[[:space:]]*";do
		echo "Waiting for node to be ready";
		sleep 5
	done
}

wait_for_api
kubectl config set clusters.kubernetes.server https://$VIP:6443 --kubeconfig /etc/kubernetes/admin.conf
kubectl config set clusters.kubernetes.server https://$VIP:6443 --kubeconfig /etc/kubernetes/kubelet.conf
kubectl config set clusters.kubernetes.server https://$VIP:6443 --kubeconfig /etc/kubernetes/controller-manager.conf
kubectl config set clusters.kubernetes.server https://$VIP:6443 --kubeconfig /etc/kubernetes/scheduler.conf

# we changed from IP to ELB hostname. Check if ELB is ready
wait_for_api
tmpfile=$(mktemp /tmp/kube-yaml.XXXXXX)

kubectl get cm cluster-info -n kube-public -o yaml > $tmpfile
sed "s#\([[:space:]]\+server: https://\).*#\1$VIP:6443#" $tmpfile -i
kubectl delete -f $tmpfile
kubectl create -f $tmpfile

kubectl get cm kube-proxy -n kube-system -o yaml > $tmpfile
sed "s#\([[:space:]]\+server: https://\).*#\1$VIP:6443#" $tmpfile -i
kubectl delete -f $tmpfile
kubectl create -f $tmpfile

rm -f $tmpfile

# in aws the elb can change the ip, so we force the apiservers to advertise with the local ip
echo "remove apiserver " $(grep -- '--advertise-address' /etc/kubernetes/manifests/kube-apiserver.yaml)
sed -i '/.*--advertise-address=/d' /etc/kubernetes/manifests/kube-apiserver.yaml

# Wait until cluster is up again
wait_for_api
