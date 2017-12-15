# General

This is currently for el7 only (redhat and clones).

The script was primarly made to install a kubernetes cluster with all images from a local docker registry.
If you want to boostrap a cluster with external images, rename variables.external to variables.  

Selinux should be disabled

# Configure the template #

    source ./variables
    yum install -y kernel docker iptables bind-utils kubelet-$KUBE_VERSION kubeadm-$KUBE_VERSION kubectl-$KUBE_VERSION
    printf '[Service]\nEnvironment="KUBELET_DNS_ARGS=--cluster-domain=%s --cluster-dns=%s"\n' \
            "$CLUSTER_DOMAIN"  "$CLUSTER_DNS" \
            > /etc/systemd/system/kubelet.service.d/20-dns-override.conf
    printf '[Service]\nEnvironment="KUBELET_EXTRA_ARGS=--image-pull-progress-deadline=10m --system-reserved=%s --pod-infra-container-image=%s"\n' \
            "$KUBELET_SYSTEM_RESERVED" "$PAUSE_IMAGE" \
            > /etc/systemd/system/kubelet.service.d/20-extra-args.conf

# Init the cluster #

## Variables ##

Check the variables file in order to update some configs.

Most important are:

* KUBE_VERSION (used during templating and cluster init)
* DOCKER_REGISTRY (used during templating): it configures from where docker will get images

Overwritable variables: KUBELET_SYSTEM_RESERVED, DOCKER_REGISTRY, HELM_REPO. Those can be updated by doing
"export DOCKER_REGISTRY=your-local-registry.company.com"

Variables can also be updated if you modify the value in the "variables" file.

You should leave most of them as is. 


## Scenarios ##
We force etcd to be on 0.0.0.0 with ssl

Single master, no vip

    ./init_cluster/install.py [--token 123456.1234567890abcdef]

Single master, with vip (for example one master in aws with elb)

    ./init_cluster/install.py --vip 10.160.24.100 [--token 123456.1234567890abcdef]

Full multi master setup

    ./init_cluster/install.py --vip 10.160.24.100 --masters master1,master2,master3 [--token 123456.1234567890abcdef]

VIP parameter:

* in aws does nothing (we expect an elb to exist)
* in vmware it adds keepalived

Init cluster:
- (in case of using vip and not in aws) install a keepalived pod on the master with our VIP
- we will use an external etcd cluster with tls
- install common components:
	- run kubeadm init
	- (in case of using vip as a hostname) fix config files and configmaps
	- create generic certificates with client extensions
	- install flannel
	- install tiller (this creates also new certificates for tiller)
- (in case of using vip) copy all pki and conf files to a configmap
- (in case of using vip) install our daemonset that will run only on masters and should initialize new masters
- (in case of using vip) clusterize the etcd-init servers
- create jobs for each master that will move the etcd servers from init to cluster
- copy all pki and conf files to a configmap (actually this updates the config info from inside kube with latest changes)

Etcd installation:
- we iterate over all masters (current node will be forced to be the first):
	- we make an etcd pod for each master with affinity for the respective master
	- each pod has in the etcd_cluster his own hostname and all previous masters
- kubelet will only start the etcd pod for the respective hostname
- at init time the etcd pod has in etcd_cluster only his own hostname (and has kind: PodERROR)
- after cluster bootstrap, a custom daemonset will add etcd manifests on all masters
- the rest of etcd servers will begin to start on the new masters
- we start "clusterizing" the etcd servers. For each master (except the init node):
	- wait for the pod to start
	- add the master as a new member inside the cluster from init pod
	- wait for cluster to be healthy again
- when we finish, a job will run on all masters, deleting the init etcd pods and installing the cluster pod (renaming kind: PodERROR to Pod)

Keepalived configuration:
- resolve vip to ip if neccessary
- resolve masters to ips
- router_id is calculated from vip ip: we sum la last 2 numbers and retrieve modulo
- write everything in keepalived.conf.template
- keepalived pod is setting the interface in the config file,
removes the script that autogenerates the config file from the image
and starts the server

Limitations:
- for etcd peers communications we use self signed certificates (--peer-auto-tls=true)
- because we add our keepalived/etcd pods before kubeadm is run, we need to run kubeadm with --skip-preflight-checks
- we don't expect for the masters ip to change if you are running on premise (vmware): keepalived is configured at init time
- if you replace a master in aws (same hostname, different ip, new os) you need to replace the old node. Run after join:
  "init_cluster/etcd-init/readd_member.sh master1 master2 master3"

Besides the initial node, there should be no difference between masters/workers for the administrator.

Just execute for all other nodes except the init one:

    kubeadm join --token 123456.1234567890abcdef $VIP:6443

