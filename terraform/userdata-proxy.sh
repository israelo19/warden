#!/bin/bash
apt-get update && apt-get install -y python3-yaml git
git clone /opt/warden 2>/dev/null || true   # replace with repo URL once published
cd /opt/warden && nohup python3 proxy/egress_proxy.py --policy policy/policy.yaml --port 3128 &
