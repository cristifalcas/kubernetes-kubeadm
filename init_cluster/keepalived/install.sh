#!/bin/bash
set -xe

cd "$( dirname "${BASH_SOURCE[0]}" )"
mode="${1:-create}"
. ../../variables
sed "s#KEEPALIVED_IMAGE#$KEEPALIVED_IMAGE#" -i keepalived.yaml

/bin/mkdir -p /etc/keepalived/ /etc/kubernetes/manifests/
/bin/cp keepalived.yaml     /etc/kubernetes/manifests/keepalived.yaml
/bin/cp keepalived.conf    /etc/keepalived/keepalived.conf
