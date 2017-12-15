#!/bin/bash
set -ex
cd "$( dirname "${BASH_SOURCE[0]}" )"
. ../../variables

ETCD_MASTERS=$@
[[ -z "$ETCD_MASTERS" ]] && exit 1

# wait for master to be initialized
while [[ ! -f /etc/kubernetes/admin.conf ]]; do sleep 5;done
grep KUBECONFIG /root/.bashrc || echo "export KUBECONFIG=/etc/kubernetes/admin.conf" >> /root/.bashrc
source /root/.bashrc

until kubectl get nodes | grep "$(hostname)[[:space:]]*Ready[[:space:]]*";do
	echo "Waiting for node to be ready";
	sleep 5
done

# get a healthy master
NODE_OK=$(kubectl get nodes $ETCD_MASTERS | grep Ready | grep -v $(hostname) | gawk '{print $1}' | head -1)
[[ -z "$NODE_OK" ]] && exit 2
SSL_OPTS="--cacert=/etc/kubernetes/pki/ca.crt --cert=/etc/kubernetes/pki/client.crt --key=/etc/kubernetes/pki/client-key.pem --endpoints=$NODE_OK:2379"
echo "will work with master $NODE_OK"
# be sure that etcd-cluster was already started here
while [[ ! -f /etc/kubernetes/manifests/etcd-cluster.yaml ]]; do sleep 1;done
#wait for etcd to start in order to check if it's in the correct cluster
while [[ -z $DOCKER_ID ]];do DOCKER_ID=$(docker ps | grep k8s_etcd_etcd-cluster-$(hostname) | grep "Up" | gawk '{print $1}'); sleep 5;done
#wait for some logs after start
sleep 5
docker logs --tail 10 $DOCKER_ID 2>&1 | grep "request cluster ID mismatch" || exit 0

# readd the new member in the old cluster
OLD_ID=$(kubectl exec -i -n kube-system etcd-cluster-$NODE_OK -- sh -c "ETCDCTL_API=3 etcdctl $SSL_OPTS member list" | grep $(hostname) | gawk -F\, '{print $1}')
[[ -z "$OLD_ID" ]] && exit 3
kubectl exec -i -n kube-system etcd-cluster-$NODE_OK -- sh -c "ETCDCTL_API=3 etcdctl $SSL_OPTS member remove $OLD_ID"
kubectl exec -i -n kube-system etcd-cluster-$NODE_OK -- sh -c "ETCDCTL_API=3 etcdctl $SSL_OPTS member add $(hostname) --peer-urls=https://$(hostname):7001"

# stop etcd member
/bin/mv /etc/kubernetes/manifests/etcd-cluster.yaml ~/
rm -rf /var/lib/etcd/*
# init the new member
function init_etcd {
    ETCD_MASTERS_A=($ETCD_MASTERS)
    INIT_CLUSTER=()
    local IFS=","
    for i in "${ETCD_MASTERS_A[@]}"; do INIT_CLUSTER+=($i=https://$i:7001); done
    INIT_CLUSTER="${INIT_CLUSTER[*]}"
    INIT_CFG="--initial-cluster $INIT_CLUSTER --initial-advertise-peer-urls=https://$(hostname):7001 --initial-cluster-state=existing"
    docker run -i --net=host -v /var/lib/etcd/:/var/lib/etcd/ $KUBE_ETCD_IMAGE sh -c \
    	"timeout etcd --name $(hostname) --data-dir=/var/lib/etcd/  --peer-auto-tls=true \
		--advertise-client-urls=https://$(hostname):2380 --listen-peer-urls=https://0.0.0.0:7001 $INIT_CFG" 2>&1 | \
		grep 'etcdmain: ready to serve client requests'
}
init_etcd
/bin/mv ~/etcd-cluster.yaml /etc/kubernetes/manifests/
