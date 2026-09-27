#!/usr/bin/env bash
# Launch an agent under gVisor with proxy-only networking.
# Requires: docker with runsc configured as a runtime (see sandbox/daemon.json).
set -euo pipefail
AGENT_FILE="${1:-agent/agent.py}"
TASK_ID="${WARDEN_TASK:-manual}"
NET="warden-internal"

# --internal: no default route, no NAT to the outside. Only members can talk.
docker network inspect "$NET" >/dev/null 2>&1 || docker network create --internal "$NET"

# Proxy joins the internal network AND the default bridge so it alone can reach out.
docker ps --format '{{.Names}}' | grep -q '^warden-proxy$' || {
  docker run -d --name warden-proxy --network bridge \
    -v "$PWD/policy:/policy:ro" -v "$PWD/eval/results:/log" \
    -e WARDEN_LOG=/log/warden-access.jsonl -w /app -v "$PWD/proxy:/app/proxy:ro" \
    python:3.12-slim sh -c "pip install -q pyyaml && python proxy/egress_proxy.py --policy /policy/policy.yaml"
  docker network connect "$NET" warden-proxy
}

docker run --rm --runtime=runsc --network "$NET" \
  --cap-drop ALL --read-only --tmpfs /tmp \
  -e HTTP_PROXY=http://warden-proxy:3128 -e HTTPS_PROXY=http://warden-proxy:3128 \
  -e NO_PROXY="" -e WARDEN_TASK="$TASK_ID" \
  -v "$PWD/$(dirname "$AGENT_FILE"):/agent:ro" \
  python:3.12-slim python "/agent/$(basename "$AGENT_FILE")"
