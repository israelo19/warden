#!/bin/bash
# Install docker + gVisor (runsc) and point the sandbox at the proxy.
apt-get update && apt-get install -y docker.io curl
curl -fsSL https://gvisor.dev/archive.key | gpg --dearmor -o /usr/share/keyrings/gvisor.gpg
echo "deb [signed-by=/usr/share/keyrings/gvisor.gpg] https://storage.googleapis.com/gvisor/releases release main" > /etc/apt/sources.list.d/gvisor.list
apt-get update && apt-get install -y runsc
runsc install && systemctl restart docker
echo "WARDEN_PROXY=http://${proxy_ip}:3128" >> /etc/environment
