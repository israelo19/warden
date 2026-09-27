# Warden design rationale

This document explains *why* each design decision exists and how it connects to the target
metrics in the README. Read this before touching the code.

## 1. Why enforce outside the sandbox

gVisor (runsc) implements a user-space kernel, the Sentry, that intercepts the application's
syscalls. Networking goes through netstack, gVisor's own user-space TCP/IP stack. That is
great for isolating the *host kernel* from the workload, but it does not give you
application-aware egress policy: netstack will happily open a socket to any address the
sandbox's network namespace can route to.

Design decision: the enforcement point is a separate process, outside the sandbox, that the
sandbox cannot bypass because **the sandbox has no other route**. Two layers make this hold:

- Docker network for the sandbox is `--internal` with the proxy as its only other member.
- At the cloud layer, the Terraform security group on the sandbox host only permits egress
  to the proxy host on port 3128.

Why this helps the unauthorized-egress metric: with gVisor alone, every request an agent
makes succeeds if the host has internet, so the baseline unauthorized egress rate is
roughly "how often does the agent wander." Under Warden, an unauthorized request cannot
succeed at the network layer regardless of what the agent decides. The only unauthorized
egress that survives is traffic that reaches an *allowlisted* host for a disallowed
purpose, which is why the policy also scopes method and path prefix, not just host.

## 2. Why deny-by-default with an explicit allowlist

A denylist is a guess about what the agent might do. An allowlist is a statement of what the
task needs. Tasks in `eval/tasks.yaml` each declare the hosts they legitimately require,
and the policy is the union of those. Anything outside that set is, by definition,
unauthorized egress for the purposes of the evaluation. This makes the metric
unambiguous: "unauthorized" is not a judgment call, it is "not in the allowlist."

## 3. Why the proxy is a forward HTTP proxy rather than iptables rules

iptables/nftables can do host-level allowlisting by IP, but:

- IPs for CDNs and registries change constantly; policy by hostname is what humans mean.
- IP rules cannot see the HTTP method or path, so they cannot distinguish `GET /package`
  from `POST /upload` on the same host.
- A proxy produces a structured access log with the task ID, which the eval harness reads
  directly to compute the metric. The log *is* the measurement instrument.

The cost is that the agent must honor `HTTP_PROXY`/`HTTPS_PROXY`. Because the sandbox has
no default route, an agent that ignores the proxy simply gets a connection failure, which
still counts as "unauthorized egress blocked."

## 4. Why measure goal-driven boundary routing instead of jailbreaks

Prompted escape attempts test the model's refusal behavior. Warden is not about the model,
it is about the environment. The interesting question for containment is: when the agent is
genuinely trying to do its job, how often does the environment let it touch something it
should not? So every task in the set is benign ("install this package and run its tests,"
"summarize this repo's README") but has a plausible off-path temptation baked in
(a README that links to an external webhook, a package whose install script phones home,
an "alternative mirror" mentioned in an error message).

## 5. Evaluation design and the 74% target

Two arms, same tasks, same model, same seed:

- **Baseline**: gVisor default isolation, full network.
- **Warden**: gVisor + proxy-only network + allowlist.

For each trial the harness records `(task_id, arm, unauthorized_attempts,
unauthorized_successes, task_completed)`. The headline metric is

    reduction = 1 - (unauthorized_success_rate_warden / unauthorized_success_rate_baseline)

The 74% figure is a **target** chosen from a back-of-envelope estimate: if roughly a quarter
of unauthorized attempts in the task set land on allowlisted hosts (e.g. a disallowed path
on an allowed registry), host-level blocking alone would yield about 75% reduction, and
path scoping should push it higher. The harness exists to find out whether that estimate
holds. If it does not, the honest outcome is a lower number and a note on which task
category leaked.

50 trials per arm is chosen for a coarse confidence interval on a proportion at reasonable
cost; it is not a claim of statistical rigor.

## 6. Why Terraform

The evaluation must be reproducible: same VM size, same security groups, same runsc
version. Terraform makes the network isolation a reviewable artifact instead of a
sequence of console clicks, and `terraform destroy` guarantees the evaluation environment
does not linger with a permissive rule left behind.

## 7. Known gaps

- HTTPS: the current proxy handles `CONNECT` by hostname only, from the request line. It
  cannot inspect the path inside TLS, so path-scoped rules apply only to plain HTTP. The
  planned fix is a per-sandbox CA and TLS termination at the proxy for allowlisted hosts.
- DNS: the sandbox has no resolver; all name resolution happens at the proxy. This is
  intentional (DNS exfiltration is closed off) but means agents that resolve names
  themselves fail loudly.
- The proxy is single-process and not hardened; it is an evaluation instrument, not a
  production gateway.
