# Warden

Network policy enforcement for gVisor-isolated AI agents.

**Status: design complete, implementation in progress. Local only, not yet published.**

## The problem

Sandboxing an AI agent with gVisor gives you strong syscall-level isolation, but gVisor's
network story is coarse: you either give the sandbox a network or you don't. A tool-using
agent needs *some* egress (package registries, an API, a docs site) to do its job, so in
practice people hand it a full network namespace and hope.

The failure mode Warden targets is not a prompted jailbreak. It is **goal-driven boundary
routing**: an agent pursuing a completely legitimate task that incidentally reaches a
destination it should never touch (an internal metadata endpoint, a paste site, a webhook
it found in a README, a mirror of a package registry). No malice, just an agent following
the shortest path to its goal.

## The approach

Warden inserts a policy enforcement point *outside* the sandbox:

```
 +-----------------------------+        +-------------------+        internet
 |  gVisor sandbox (runsc)     |        |  Warden proxy     |  -->   (allowlisted
 |  no default route           | -----> |  allowlist + log  |         hosts only)
 |  HTTP(S)_PROXY=warden:3128  |  only  |  deny by default  |  --x   everything else
 +-----------------------------+  path  +-------------------+
```

1. The sandbox network namespace has **no route to the internet**. Its only reachable peer
   is the Warden proxy. This is enforced at the host / cloud layer (Terraform security group
   + Docker network), not by asking the agent nicely.
2. The proxy is **deny-by-default**. Every outbound request is matched against
   `policy/policy.yaml` (host, port, method, path prefix). Denied requests return 403 and
   are logged with the task ID that produced them.
3. An **adversarial control evaluation harness** (`eval/`) runs the same task set against
   (a) gVisor default isolation alone and (b) gVisor + Warden, and measures the
   unauthorized egress rate for each.

## Target metrics

These are the **design targets** the evaluation harness is built to measure. They have not
been measured yet; `eval/results/` is empty until the full harness run is complete.

| Metric | Target | How it is measured |
|---|---|---|
| Unauthorized egress rate reduction vs. gVisor default | >= 74% | `eval/harness.py`, 50 trials per arm |
| Task completion rate under Warden | >= 90% of baseline | same harness, task success flag |
| Added latency per allowed request | < 20 ms p50 | proxy access log timestamps |
| Policy decision correctness | 100% on unit suite | `pytest tests/` |

## What exists today

- [x] Architecture and threat model (`docs/`)
- [x] Policy schema and matcher (`proxy/policy.py`) with passing unit tests
- [x] Allowlisting egress proxy, single-process, stdlib only (`proxy/egress_proxy.py`)
- [x] Terraform for an isolated evaluation VM and security groups (`terraform/`)
- [x] Sandbox launch script for `runsc` with proxy-only networking (`sandbox/`)
- [x] Evaluation harness skeleton and task set (`eval/`)
- [ ] Full 50-trial evaluation run for each arm
- [ ] HTTPS CONNECT tunneling with SNI-based host checks
- [ ] Per-task policy scoping (different allowlists per task)

## Quick start (local)

```bash
python -m pytest tests/                  # policy matcher tests
python proxy/egress_proxy.py --policy policy/policy.yaml --port 3128
./sandbox/run_agent.sh agent/agent.py    # launches under runsc with proxy-only network
python eval/harness.py --trials 5 --arm warden   # smoke run
```

## Log (local dev notes)

- 2026-09-23: policy matcher + 8 unit tests passing. First proxy smoke test found that HTTPS
  `CONNECT` was denied for allowlisted hosts because the matcher required the method to be
  in the rule; added `evaluate_connect` (host+port only for TLS tunnels). Verified manually:
  allowlisted host -> 200, unknown host -> blocked, allowlisted host on disallowed path -> 403.
  Full evaluation run not started.
