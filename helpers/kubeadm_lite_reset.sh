#!/bin/bash
set -x
cd "$( dirname "${BASH_SOURCE[0]}" )"
export KUBECONFIG=/etc/kubernetes/kubelet.conf
timeout 5 kubectl delete node $(hostname)
kubeadm reset
rm -rf /var/lib/etcd /var/lib/cni/ /etc/kubernetes /etc/keepalived /etc/kube-flannel/ /root/admin.conf
ip link set flannel.1 down
ip link delete flannel.1
ip link set cni0 down
yum install bridge-utils -y
brctl delbr cni0

cd ..
git add .
git stash
git pull --no-edit
systemctl restart docker kubelet network
