#!/bin/bash
set -ex
cd "$( dirname "${BASH_SOURCE[0]}" )"
mode="${1:-create}"

KUBE_PKI="/etc/kubernetes/pki/"
# we get client.csr and client-key.pem
cfssl genkey client-cert.json | cfssljson -bare $KUBE_PKI/client

REQ=$(cat $KUBE_PKI/client.csr | base64 | tr -d '\n')
sed "s/\(.*request: \).*/\1$REQ/" generic_client_csr.yaml -i

kubectl $mode -f generic_client_csr.yaml

if [[ $mode == "create" ]]; then
	kubectl certificate approve generic-client-csr

	# cert is not available instantly
	while [[ -z "$CRT" ]]; do
		CRT=$(kubectl get csr generic-client-csr -o jsonpath='{.status.certificate}')
		sleep 1
	done
	echo $CRT | base64 -d > $KUBE_PKI/client.crt
fi

rm -f $KUBE_PK/client.csr
KEY=$(openssl rsa -check -noout -modulus -in $KUBE_PKI/client-key.pem | head -1)
CRT=$(openssl x509 -noout -modulus -in $KUBE_PKI/client.crt)
[[ $KEY == $CRT ]] || exit 1
