#!/bin/bash
set -ex

cd "$( dirname "${BASH_SOURCE[0]}" )"
. ../../variables
mode="${1:-create}"

KUBE_PKI="/etc/kubernetes/pki/"
# we get tiller.csr and tiller-key.pem
cfssl genkey tiller-cert.json | cfssljson -bare $KUBE_PKI/tiller

REQ=$(cat $KUBE_PKI/tiller.csr | base64 | tr -d '\n')
sed "s/\(.*request: \).*/\1$REQ/" tiller-csr.yaml -i

kubectl $mode -f tiller-csr.yaml

if [[ $mode == "delete" ]]; then
	kubectl $mode secret -n kube-system tiller-secret
	kubectl $mode deployment -n kube-system tiller-deploy
	kubectl $mode serviceaccount --namespace kube-system tiller
	kubectl $mode clusterrolebinding tiller
	rm -rf /root/.helm/
	exit 0
fi

kubectl certificate approve tiller-csr
# cert is not available instantly
while [[ -z "$CRT" ]]; do
	CRT=$(kubectl get csr tiller-csr -o jsonpath='{.status.certificate}')
	sleep 1
done
echo $CRT | base64 -d > $KUBE_PKI/tiller.crt

rm -f $KUBE_PK/tiller.csr
KEY=$(openssl rsa -check -noout -modulus -in $KUBE_PKI/tiller-key.pem | head -1)
CRT=$(openssl x509 -noout -modulus -in $KUBE_PKI/tiller.crt)
[[ $KEY == $CRT ]] || exit 1

[[ -n $TILLER_IMAGE ]] && TILLER_IMAGE_ARGS="--tiller-image $TILLER_IMAGE"
[[ -n $HELM_REPO ]] && TILLER_IMAGE_ARGS="$TILLER_IMAGE_ARGS --stable-repo-url https://$HELM_REPO/helm/"

helm init \
 	--node-selectors='node-role.kubernetes.io/master=' \
	--override 'spec.template.spec.tolerations[0].key=node-role.kubernetes.io/master' \
	--override 'spec.template.spec.tolerations[0].effect=NoSchedule' \
	--override 'spec.template.spec.tolerations[0].operator=Exists' \
	--service-account tiller \
	--tiller-tls \
	--tiller-tls-verify \
	--tls-ca-cert     $KUBE_PKI/ca.crt \
	--tiller-tls-cert $KUBE_PKI/tiller.crt \
	--tiller-tls-key  $KUBE_PKI/tiller-key.pem \
	$TILLER_IMAGE_ARGS \
	--debug
# keys are kept in tiller-secret
rm -f $KUBE_PKI/tiller-key.pem
rm -f $KUBE_PKI/tiller.crt

kubectl $mode serviceaccount --namespace kube-system tiller
kubectl $mode clusterrolebinding tiller --clusterrole=cluster-admin --serviceaccount=kube-system:tiller

# HELM_TLS="--tls --tls-ca-cert /etc/kubernetes/pki/ca.crt --tls-cert /etc/kubernetes/pki/client.crt --tls-key /etc/kubernetes/pki/client-key.pem"
# helm version $HELM_TLS --debug
