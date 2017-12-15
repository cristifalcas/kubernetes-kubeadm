import subprocess, socket, sys, os, netifaces, urllib2, ssl, logging
from our_libs import logger
from jinja2 import Template
from distutils.version import LooseVersion, StrictVersion
from shutil import copyfile
from time import sleep

def run_command(cmd, log):
    log.info("Running command: " + " ".join(cmd))
    try:
        out = ""
        popen = subprocess.Popen(cmd, shell=False, stdout=subprocess.PIPE)
        while True:
            line = popen.stdout.readline()
            if not line: break
            out += line
            log.info(line.rstrip())
        popen.wait()
        log.info("Command terminated")
        if popen.returncode:
            log.error("Error running command: " + " ".join(cmd) + " has exited with error code " + str(popen.returncode))
            sys.exit(popen.returncode)
    except:
        raise
    return out


class Worky():
    def __init__(self, args, crt_dir, type, in_aws = False):
        self.log = logging.getLogger(__name__)
        self.log.info("Init worky")
        self.crt_dir = crt_dir
        kube_ver = run_command(["rpm", "-q", "--queryformat", "'%{VERSION}'", "kubeadm"], self.log).replace("'", "")
        StrictVersion(kube_ver)

        self.variables = {}
        self.variables['type'] = type
        self.variables['in_aws'] = in_aws
        self.variables['default_iface'] = self.__get_default_iface__()[0]
        # self.variables['my_ip'] = socket.gethostbyname(socket.getfqdn())
        self.variables['my_hostname'] = socket.getfqdn()
        self.variables['kube_ver'] = kube_ver
        if args.token:
            self.variables['token'] = args.token

        if args.masters:
            self.variables['masters'] = args.masters
        else:
            self.variables['masters'] = [self.variables['my_hostname']]

        if args.vip:
            self.variables['vip'] = args.vip

        self.variables['KUBE_ETCD_IMAGE'] = os.environ.get('KUBE_ETCD_IMAGE')
        self.variables['ALPINE_IMAGE'] = os.environ.get('ALPINE_IMAGE')
        self.variables['NOD_NETWORK_SPACE'] = os.environ.get('NOD_NETWORK_SPACE')
        self.variables['NOD_NETWORK_SPACE_SIZE'] = os.environ.get('NOD_NETWORK_SPACE_SIZE')
        self.variables['SRV_NETWORK'] = os.environ.get('SRV_NETWORK')
        self.variables['SRV_NETWORK_SIZE'] = os.environ.get('SRV_NETWORK_SIZE')
        self.variables['CLUSTER_DOMAIN'] = os.environ.get('CLUSTER_DOMAIN')

        self.log.info(self.variables)


    def get_variables(self):
        self.log.info("Get worky variables")
        return self.variables


    def install_common(self, extra_args=""):
        self.log.info("Installing common components")
        self.__extra_stuff__('start')
        self.__kubeadm_init__(extra_args)
        self.__install_network_plugin__()

        # fix config if vip is a hostname
        if 'vip' in self.variables:
            try:
                socket.inet_aton(self.variables['vip'])
            except socket.error:
                self.__fix_config__()
                self.__wait_for_api__()

        self.__install_client_cert__()
        self.__install_tiller__()
        self.__extra_stuff__('end')


    def install_external_etcd_server(self):
        self.log.info("Installing an external etcd server for bootstrap")
        os.environ['masters'] = ','.join(self.variables['masters'])
        output = run_command([os.path.join(self.crt_dir, "etcd-init/install.sh")], self.log)


    def clusterize_etcd_server(self):
        self.log.info("Clusterizing the etcd servers")
        os.environ['masters'] = ','.join(self.variables['masters'])
        output = run_command([os.path.join(self.crt_dir, "etcd-init/clusterize.sh")], self.log)


    def install_keepalived(self):
        self.log.info("Installing keepalived")
        if self.variables['in_aws']:
            self.log.error("We don't install keepalived in amazon")
            sys.exit(exit_code.get('ERR_GENERIC'))

        try:
            # is this an ip?
            socket.inet_aton(self.variables['vip'])
            vip_ip = self.variables['vip']
        except socket.error:
            # Not an ip
            vip_ip = socket.gethostbyname(self.variables['vip'])
        masters_ips = self.__hostnames_to_ip__(self.variables['masters'])

        router_id = (int(vip_ip.split('.')[-2]) + int(vip_ip.split('.')[-1])) % 255
        in_path = os.path.join(self.crt_dir, 'keepalived/keepalived.conf.template')
        out_path = os.path.join(self.crt_dir, 'keepalived/keepalived.conf')
        template = open(in_path, "r")
        src = Template(template.read())
        self.variables.update({
             'router_id': router_id,
             'vip_ip': vip_ip,
             'masters_ips': masters_ips,
            })
        result = src.render(self.variables)
        f = open(out_path, 'w', 0)
        f.write(result)
        f.close()

        output = run_command([os.path.join(self.crt_dir, "keepalived/install.sh")], self.log)


    def install_masters_installer(self):
        self.log.info("Install masters_installer")
        in_path = os.path.join(self.crt_dir, 'masters_installer/daemonset.yaml.template')
        out_path = os.path.join(self.crt_dir, 'masters_installer/daemonset.yaml')
        template = open(in_path, "r")
        src = Template(template.read())
        result = src.render(self.variables)
        f = open(out_path, 'w', 0)
        f.write(result)
        f.close()

        output = run_command([os.path.join(self.crt_dir, "masters_installer/install.sh")], self.log)


    def __hostnames_to_ip__(self, hosts):
        ips = []
        for host in hosts:
            ips.append(socket.gethostbyname(host))
        return ips


    def __kubeadm_init__(self, extra_args):
        self.log.info("Run kubeadm init")
        if not os.path.exists('/etc/kubernetes'):
            os.makedirs('/etc/kubernetes')
        # here we initialize the conf file for kubeadm and execute kubeadm
        in_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'kubeadm_file.yaml.template')
        out_path = '/etc/kubernetes/kubeadm_file.yaml'
        template = open(in_path, "r")
        src = Template(template.read())
        result = src.render(self.variables)
        f = open(out_path, 'w', 0)
        f.write(result)
        f.close()

        cmd = ["kubeadm", "init", "--config", out_path]
        cmd.extend(extra_args)
        output = run_command(cmd, self.log)
        os.environ['KUBECONFIG'] = '/etc/kubernetes/admin.conf'


    # https://stackoverflow.com/a/20925510/451348
    def __get_default_iface__(self):
        self.log.info("Find default iface")
        route = "/proc/net/route"
        with open(route) as f:
            for line in f.readlines():
                try:
                    iface, dest, gateway, flags, _, _, _, _, _, _, _, = line.strip().split()
                    if dest != '00000000' or not int(flags, 16) & 2:
                        continue
                    # https://nessy.info/?p=666
                    x = iter(gateway)
                    res = [str(int(''.join(i), 16)) for i in zip(x, x)]
                    gateway = '.'.join(res[::-1])
                    self.log.info("Found default iface %s with gateway %s" %(iface, gateway))
                    return iface, gateway
                except:
                    continue
        self.log.error("Could not find default iface")
        sys.exit(exit_code.get('ERR_IFACE'))


    def __fix_config__(self):
        self.log.info("Fixing admin.conf file (change server from ip to original value given)")
        output = run_command([os.path.join(self.crt_dir, "fix_config/install.sh"), self.variables['vip']], self.log)


    def __wait_for_api__(self):
        self.log.info("Trying to access the api server")
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        url = "https://" + self.variables['vip'] + ":6443/api/v1/namespaces/kube-public/configmaps/cluster-info"
        while True:
            try:
                urllib2.urlopen(url, timeout = 1, context=ctx)
                self.log.info("API server accessible.")
                break
            except Exception:
                self.log.info("API server not reacheable...")
                sleep(0.3)


    def __install_network_plugin__(self):
        self.log.info("install_network_plugin")
        output = run_command([os.path.join(self.crt_dir, "flannel/install.sh")], self.log)


    def __install_client_cert__(self):
        self.log.info("install generic client_cert")
        output = run_command([os.path.join(self.crt_dir, "client_cert/install.sh")], self.log)


    def __install_tiller__(self):
        self.log.info("install_tiller")
        output = run_command([os.path.join(self.crt_dir, "tiller/install.sh")], self.log)

    def __extra_stuff__(self, mode):
        self.log.info("installing stuff at %s", mode)
        output = run_command([os.path.join(self.crt_dir, "extra_stuff/install.sh"), mode], self.log)


#     def add_vip(self):
#         ip = self.variables['vip_ip']
#         iface = self.variables['default_iface']
#         log.info("Trying to add ip " + ip + " to interface " + iface)
#         exists = 0
#         addrs = netifaces.ifaddresses(iface)
#         for i in addrs[netifaces.AF_INET]:
#             if i['addr'] == ip and i['broadcast'] == ip:
#                 exists = 1
#                 log.info("Ip address already attached to iface.")
#                 break
#         if not exists:
#             run_command(["ip", "addr", "add", ip + "/32", "dev", iface], self.log)


#     def __rm_ip__(self):
#         ip = self.variables['vip_ip']
#         iface = self.variables['default_iface']
#         self.log.info("Removing ip " + ip + " from interface " + iface)
#         output = run_command(["ip", "addr", "del", ip + "/32", "dev", iface], self.log)


#     def kubeadm_create_certs(self):
#         self.log.info("Run kubeadm create_certs")
#         params = []
#         altnames = list(self.variables['masters'])
#         if StrictVersion(self.variables['kube_ver']) < StrictVersion("1.7.0"):
#             altnames.append(self.variables['vip'])
#         else:
#             params.append('--apiserver-advertise-address')
#             params.append(self.variables['vip'])
#         params.append('--cert-altnames')
#         params.append(','.join(altnames))
#         params.append('--dns-domain')
#         params.append(self.variables['CLUSTER_DOMAIN'])
#         params.append('--service-cidr')
#         params.append(self.variables['SRV_NETWORK'] + "/" + self.variables['SRV_NETWORK_SIZE'])
#         output = run_command(["kubeadm", "alpha", "phase", "certs", "selfsign"] + params, self.log)


# def start_services():
#     with open('/proc/1/cgroup') as f:
#         if re.search(r"^0::/init.scope$", f.read(), re.MULTILINE):
#             sysbus = dbus.SystemBus()
#             systemd1 = sysbus.get_object('org.freedesktop.systemd1', '/org/freedesktop/systemd1')
#             manager = dbus.Interface(systemd1, 'org.freedesktop.systemd1.Manager')
#             job = manager.RestartUnit('kubelet.service', 'fail')
#             job = manager.RestartUnit('docker.service', 'fail')
#         else:
#             log.info("We are in a container")
