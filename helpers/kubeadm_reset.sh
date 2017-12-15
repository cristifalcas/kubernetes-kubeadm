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

systemctl stop docker
lvremove /dev/mapper/docker-pool00  -y
rm -rf /var/lib/docker/
lvcreate -T docker/pool00 -l +100%FREE --poolmetadatasize 500M --wipesignatures y
mkdir -p /var/lib/docker/devicemapper/devicemapper
systemctl start docker

yum remove -y kubeadm kubectl kubelet kubernetes-cni \
	helm cfssl \
	python-certifi python2-kubernetes python-netifaces \
	python2-google-auth python-dateutil PyYAML python-requests \
	python-setuptools python-six python-urllib3 python-jinja2 \
	python-websocket-client python2-psuti

./make_template/install.sh
systemctl restart docker kubelet network
