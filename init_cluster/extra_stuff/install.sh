#!/bin/bash
set -ex
cd "$( dirname "${BASH_SOURCE[0]}" )"
. ../../variables

case "$1" in
start)
	echo "Start config"
	cp -r ./copy_beggining/* /
;;
end)		
	echo "End config"
	cp -r ./copy_end/* /
	grep KUBECONFIG /root/.bashrc || echo "export KUBECONFIG=/etc/kubernetes/admin.conf" >> /root/.bashrc
;;
*)
	echo "Unknown " $1
	exit 1
;;
esac
