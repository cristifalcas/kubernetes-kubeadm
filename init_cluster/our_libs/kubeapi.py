# https://fossies.org/linux/salt/salt/modules/kubernetes.py
import json, kubernetes, socket, sys, os, tarfile, io, base64, yaml, re, logging
from our_libs import logger
from jinja2 import Template
from pprint import pprint
from subprocess import check_call
from kubernetes.client.rest import ApiException
from time import sleep

namespace = 'kube-system'
config_to_ignore = ['^/etc/kubernetes/kubeadm_file.yaml$',
                    '^/etc/kubernetes/kubelet.conf$',
                    '^/etc/kubernetes/pki/ca.crt$',
                    '^/etc/kubernetes/pki/apiserver.*',
                   ]

class Worky():
    def __init__(self, variables, exit_code):
        self.log = logging.getLogger(__name__)
        self.log.info("Init kubeapi")
        self.exit_code = exit_code
        self.variables = variables
        self.client = None
        self.apiv1 = None
        self.v1ext = None
        self.hostname = socket.getfqdn()
        self.etcd_servers = [self.hostname]


    def connect(self):
        self.log.info("Connecting to kubernetes cluster")
        kubernetes.config.load_kube_config('/etc/kubernetes/admin.conf')
        config = kubernetes.client.Configuration()
        if not config.api_client:
            config.api_client = kubernetes.client.ApiClient()
        self.client = config.api_client
        self.apiv1 = kubernetes.client.CoreV1Api(self.client)
        self.v1ext = kubernetes.client.ExtensionsV1beta1Api(self.client)
        self.batchv1 = kubernetes.client.BatchV1Api(self.client)


    def wait_for_masters(self):
        self.log.info("Waiting for all masters to join")
        masters = list(self.variables['masters'])
        masters.remove(self.variables['my_hostname'])
        while True:
            if len(masters) == 0:
                break
            for node in self.apiv1.list_node(include_uninitialized = True).items:
                if node.metadata.name in masters:
                    masters.remove(node.metadata.name)
            self.log.info("Still waiting to join the following masters: %s" %masters)
            sleep(1.0)
        self.log.info("All masters joined")


    def __delete_existing_configmap(self, configmap_name):
        self.log.info("Check if configmap already exists.")
        cm_exists = False
        for cm in self.apiv1.list_namespaced_config_map(namespace=namespace).items:
            if configmap_name == cm.metadata.name:
                cm_exists = True
                break

        if cm_exists:
            self.log.info("Delete the configmap.")
            old_body = kubernetes.client.V1DeleteOptions()
            self.apiv1.delete_namespaced_config_map(name=configmap_name, namespace=namespace, body=old_body)


    def __list_kubernetes_dir(self):
        # get kubernets and keepalived config files
        kubeconfig_all = []
        for root, subdirs, files in os.walk('/etc/kubernetes/'):
            kubeconfig_all.extend([os.path.join(root, s) for s in files])
        for root, subdirs, files in os.walk('/etc/keepalived/'):
            kubeconfig_all.extend([os.path.join(root, s) for s in files])

        kubeconfig = []
        for file in kubeconfig_all:
            skip_file = False
            for file_regex in config_to_ignore:
                if re.search(r"%s"%file_regex, file):
                    skip_file = True
                    break
            if not skip_file:
                kubeconfig.append(file)
        return kubeconfig


    def __tar_files(self, kubeconfig):
        # make a tar archive
        tarFileIo = io.BytesIO()
        tar = tarfile.open(fileobj=tarFileIo, mode='w')
        for name in kubeconfig:
            tar.add(name)
        tar.close()
        return tarFileIo.getvalue()
        

    def __vars_to_string(self):
        # all init vars to string:
        vars_str = {}
        for k,v in self.variables.iteritems():
            if type(v) == list:
                vars_str.update({k: ','.join(v)})
            elif type(v) == int:
                vars_str.update({k: str(v)})
            elif type(v) == bool:
                vars_str.update({k: str(v)})
            elif type(v) == str:
                vars_str.update({k: v})
            else:
                self.log.error("Unknown type: " + str(type(v)))
                self.log.info(self.variables)
                sys.exit(self.exit_code.get('ERR_CFG_TYPE'))
        return vars_str


    def kubeconfig_to_configmap(self):
        self.log.info("Loading config files to kubernetes")
        configmap_name = 'kubeconf'

        # create a config map
        body = kubernetes.client.V1ConfigMap()
        body.metadata = kubernetes.client.V1ObjectMeta()
        body.metadata.name = configmap_name
        self.__delete_existing_configmap(configmap_name)

        tarfile = self.__tar_files(self.__list_kubernetes_dir())
        body.data = {configmap_name: base64.b64encode(tarfile)}
        body.data.update(self.__vars_to_string())

        self.log.info("Create configmap.")
        api_response = self.apiv1.create_namespaced_config_map(namespace=namespace, body=body)


    def cleanup(self):
        self.log.info("Create a cleanup job for each master")
        body = kubernetes.client.V1Job()
        jobs = []
        with open(os.path.join(os.path.dirname(__file__), "job.yaml.template")) as f:
            src = Template(f.read())
            for host in self.variables['masters']:
                dest = src.render({'host':host, 'ALPINE_IMAGE':self.variables['ALPINE_IMAGE']})
                job=yaml.load(dest)
                api_response = self.batchv1.create_namespaced_job(body=job, namespace=namespace)
                self.log.info("Job created. status='%s'" % str(api_response.status))

                jobs.append("init-cleanup-" + host)

        self.log.info("Wait for all jobs to complete")
        # we are expecting some timeouts here when we switch etcds
        while True:
            try:
                if len(jobs) == 0:
                    break
                self.log.info("Waiting for jobs %s" % jobs)
                # create some jobs that move the etcd config to cluster
                for job in self.batchv1.list_namespaced_job(namespace=namespace, include_uninitialized = True).items:
                    if job.metadata.name not in jobs:
                        continue
                    if job.status.failed:
                        self.log.error("One job failed: %s" % job)
                        sys.exit(self.exit_code.get('ERR_JOB_FAILED'))
                    if job.status.active:
                        continue
                    if job.status.succeeded and job.status.conditions:
                        for condition in job.status.conditions:
                            if condition.status == 'True' and condition.type == 'Complete': 
                                jobs.remove(job.metadata.name)
                                self.log.info("One job finished successfully: %s" % job.metadata.name)
                            else:
                                self.log.error("One job has wrong conditions: %s" % job)
                                sys.exit(self.exit_code.get('ERR_JOB_COND'))
            except ApiException as e:
                if not re.search(r"(Reason: Gateway Timeout)|(etcdserver: request timed out)", "%s"%e, re.MULTILINE):
                    raise e 
                self.log.info("We got a timeout exception. Still working: %s" %e)
            sleep(5.0)
        self.log.info("All jobs completed")

