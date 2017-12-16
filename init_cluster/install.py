#!/bin/python

from __future__ import print_function
# logging needs to be imported before any other module has a chance to initialize it
import logging, sys, os, inspect, argparse, socket, distutils.dir_util, time, re, traceback, urllib2
from our_libs import logger

crt_dir = os.path.dirname(os.path.realpath(__file__))
log = logging.getLogger(__name__)

# error codes:
exit_code = {
             'ERR_GENERIC': 1,
             'ERR_ARGS': 2,
             'ERR_CMD': 3,
             'ERR_KUBE': 4,
             'ERR_CFG_TYPE': 5,
             'ERR_JOB_FAILED': 6,
             'ERR_JOB_COND': 7,
             'ERR_IFACE': 8,
}


def check_if_in_aws(args):
    if args.force_aws:
        return True

    meta = 'http://169.254.169.254/latest/meta-data/ami-id'
    try:
        urllib2.urlopen(meta, timeout = 1)
        return True
    except Exception:
        return False


def validate_masters(string):
    masters = string.split(',')
    return masters


def validate_token(string):
    if re.search(r"^([a-z0-9]{6})\.([a-z0-9]{16})$", string):
        return string
    else:
        log.critical("Token needs to be of the form '^([a-z0-9]{6})\\.([a-z0-9]{16})$'")
        sys.exit(exit_code.get('ERR_ARGS'))


def validate_bool(string):
    if string in ['True', 'true', '1', 't', 'y', 'yes']:
        return True
    else:
        return False


def init_argparse():
    parser = argparse.ArgumentParser(description='install a new kubernetes cluster or join the machine to an existing kubernetes cluster')
    parser.add_argument('--vip', type=str, required=False,
                    help='Virtual ip of the cluster. Usefull only with multiple masters.')
    parser.add_argument('--masters', type=validate_masters, required=False,
                    help='list of masters hostnames')
    parser.add_argument('--token', type=validate_token, required=False,
                    help='force a known kubernetes token')
    parser.add_argument('--force_aws', type=validate_bool, required=False, default=False,
                    help='force a known kubernetes token')
    return parser


def parse_arguments(args):
    if args.masters and len(args.masters) > 1 and not args.vip:
        # multiple masters and no vip
        log.critical("For multiple masters we need a vip.")
        sys.exit(exit_code.get('ERR_ARGS'))
    elif args.masters and len(args.masters) == 1:
        # only master
        log.critical("You don't need to set only one master.")
        sys.exit(exit_code.get('ERR_ARGS'))
    elif args.masters and not socket.getfqdn() in args.masters:
        # we should be in the masters list
        log.critical("Our hostname({}) should be in masters({}).".format(socket.getfqdn(), args.masters))
        sys.exit(exit_code.get('ERR_ARGS'))
    elif args.masters and not len(args.masters)%2:
        # wee need odd number of masters
        log.critical("There should be an odd number of hostnames, but we got {}".format(len(args.masters)))
        sys.exit(exit_code.get('ERR_ARGS'))
    elif not args.masters and not args.vip:
        # single master
        log.info("installing a cluster with a single master")
        return 'single'
    elif not args.masters and args.vip:
        # single master with vip (ex: amazon with elb)
        log.info("installing a cluster with one master and one vip: %s, %s", args.masters, args.vip)
        return 'vip'
    else:
        # multiple masters
        log.info("installing a cluster with the following masters: %s and this vip: %s", args.masters, args.vip)
        return 'vip'


def check_resources():
    import psutil
    nr_cpu = psutil.cpu_count(logical=True)
    mem_gb = psutil.virtual_memory().total/1024.0/1024/1024
    if nr_cpu < 2 or mem_gb < 3:
        main_dir = os.path.abspath(crt_dir + "/../")
        log.warning("#######################################")
        log.warning("The machine may have too few resources to start the cluster.")
        log.warning("If this is the case, try running %s/helpers/fix_config_small_machine.sh", main_dir)
        log.warning("#######################################")


def print_for_prometheus(type, args):
    log.info("Writing /opt/prometheus.var for prometheus.")
    if type == 'single':
        data_host = socket.getfqdn()
    else:
        data_host = args.vip

    f = open('/opt/prometheus.var', 'w', 0)
    f.write("\"{\\\"host\\\": \\\"%s\\\", \\\"port\\\": 30900, \\\"name\\\":\\\"prometheus-%s\\\"}\"" %(data_host, data_host))
    f.close()
    log.info("File /opt/prometheus.var has been written.")


def main():
    log.info("Main function")
    parser = init_argparse()
    args = parser.parse_args()
    type = parse_arguments(args)
    check_resources()
    in_aws = check_if_in_aws(args)
    extra_args = []
    from kubernetes.client.rest import ApiException
    from our_libs import worky, kubeapi
    c = worky.Worky(args, crt_dir, type, in_aws)
    k = kubeapi.Worky(c.get_variables(), exit_code)

    if type == 'vip' and not in_aws:
        log.info("We are not in aws, so we install a keepalived cluster")
        c.install_keepalived()

    # when using external etcds, kubeadm expects the servers to be started
    # we install a "cluster" with a single member at the beginning
    c.install_external_etcd_server()
    # because we create the manifests dir for etcd, we need to start kubeadm with skip-preflight-checks
    extra_args.append('--skip-preflight-checks')
    c.install_common(extra_args)
    try:
        k.connect()
        if type == 'vip':
            k.wait_for_masters()
            # copy /etc/kubernetes to a config map for bootstrapping the rest of the masters
            k.kubeconfig_to_configmap()
            c.install_masters_installer()
            c.clusterize_etcd_server()

        k.cleanup()
        k.kubeconfig_to_configmap()
    except ApiException as e:
        # catch kubernetes exceptions
        print("Exception: %s\n" % e)
        sys.exit(exit_code.get('ERR_KUBE'))

    print_for_prometheus(type, args)


if __name__ == '__main__':
    try:
        # relaunch with variables
        env_ok = os.environ.get('NOD_NETWORK_SPACE')
        if not env_ok:
            # if we install python2-kubernetes we need to restart
            sys.path.insert(0, '/usr/share/yum-cli')
            import yummain
            yummain.user_main(['install', '-y', '-q',
                               'python2-psutil',
                               'python-backports-ssl_match_hostname',
                               'python-ipaddress',
                               'python-jinja2',
                               'python-netifaces',
                               'python2-kubernetes',
                               'cfssl',
                               'helm',
                               ])
            print("*** Relaunching and loading the variables file. ***")
            os.execve('/bin/bash',['bash','-c', '. ' + crt_dir + '/../variables && ' + " ".join(sys.argv)], os.environ)
        else:
            main()
            log.info("*** Finished successfully. ***")
    except Exception, e:
        traceback.print_exc()
