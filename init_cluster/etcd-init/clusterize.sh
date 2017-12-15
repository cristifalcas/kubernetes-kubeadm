#!/bin/bash
IFS=',' read -r -a array <<< "$masters"
array=( "${array[@]/$HOSTNAME}" )
SSL_OPTS="--cacert=/etc/kubernetes/pki/ca.crt --cert=/etc/kubernetes/pki/client.crt --key=/etc/kubernetes/pki/client-key.pem --endpoints=$HOSTNAME:2379"
here=etcd-init-$HOSTNAME-$HOSTNAME
spin=("-" "\\" "|" "/")
var=0

for master in ${array[@]};do
	echo "Waiting for etcd-init pod on node $master..."
	until kubectl get pods -n kube-system etcd-init-$master-$master &> /dev/null;do
		#var=$((var + 1)) && x=$(echo $var%4|bc)
		#echo -en "\rWaiting for etcd-init pod on node $master..." "${spin[$x]}"
		echo "Waiting for etcd-init pod on node $master..."
		sleep 5
	done
	echo "Adding member $master to etcd cluster..."
	until kubectl exec -i -n kube-system $here -- sh -c "ETCDCTL_API=3 etcdctl $SSL_OPTS member add --peer-urls=https://$master:7001 $master" &> /dev/null;do
		#var=$((var + 1)) && x=$(echo $var%4|bc)
		#echo -en "\rAdding member $master to etcd cluster..." "${spin[$x]}"
		echo "Adding member $master to etcd cluster..."
		sleep 3
	done
	echo "Waiting for etcd cluster to be healthy again..."
	until kubectl exec -i -n kube-system $here -- sh -c "ETCDCTL_API=3 etcdctl $SSL_OPTS endpoint health" &> /dev/null;do
		#var=$((var + 1)) && x=$(echo $var%4|bc)
		#echo -en "\rWaiting for etcd cluster to be healthy again..." "${spin[$var]}"
		echo "Waiting for etcd cluster to be healthy again..."
		sleep 3
	done
done

echo "Done clusterizing the etcd servers."
