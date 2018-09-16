#!/bin/bash
KUBE_VER=1.9.10

yum install -y aws kubectl-$KUBE_VER kubeadm-$KUBE_VER kubelet-$KUBE_VER

cat <<EOF > kubeadmin_conf.yaml
apiVersion: kubeadm.k8s.io/v1alpha1
kind: MasterConfiguration
kubernetesVersion: $(kubeadm version -o short)
cloudProvider: "aws"
networking:
  podSubnet: 10.240.0.0/13
  serviceSubnet: 10.255.0.0/22
controllerManagerExtraArgs:
  service-cluster-ip-range: 10.255.0.0/22
  configure-cloud-routes: "false"
  attach-detach-reconcile-sync-period: "1m0s"
etcd:
  endpoints:
  - https://$HOSTNAME:2379
  caFile: /etc/kubernetes/pki/ca.crt
  certFile: /etc/kubernetes/pki/apiserver-kubelet-client.crt
  keyFile: /etc/kubernetes/pki/apiserver-kubelet-client.key
EOF

kubeadm init --config ./kubeadmin_conf.yaml --skip-preflight-checks
kubectl apply -f https://raw.githubusercontent.com/coreos/flannel/v0.9.1/Documentation/kube-flannel.yml

kubectl apply -f "https://cloud.weave.works/k8s/net?k8s-version=$(kubectl version | base64 | tr -d '\n')"

curl -L https://storage.googleapis.com/kubernetes-helm/helm-v2.8.2-linux-amd64.tar.gz | tar xvz && \
    /bin/mv ./linux-amd64/helm /bin/helm && chmod +x /bin/helm
helm init  	--node-selectors='node-role.kubernetes.io/master=' \
	--override 'spec.template.spec.tolerations[0].key=node-role.kubernetes.io/master' \
	--override 'spec.template.spec.tolerations[0].effect=NoSchedule' \
	--override 'spec.template.spec.tolerations[0].operator=Exists' 
	--service-account tiller
kubectl create serviceaccount --namespace kube-system tiller
kubectl create clusterrolebinding tiller --clusterrole=cluster-admin --serviceaccount=kube-system:tiller
