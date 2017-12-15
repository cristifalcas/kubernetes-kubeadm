#!/bin/bash

sed s/cpu=.*,memory=.*Gi/cpu=0,memory=0Gi/ /etc/systemd/system/kubelet.service.d/20-extra-args.conf -i
systemctl daemon-reload
systemctl restart kubelet
