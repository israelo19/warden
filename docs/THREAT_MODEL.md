# Threat model

**Asset**: the boundary between an AI agent's working environment and everything outside it.

**Adversary**: not the model. The adversary is the *task environment*: web pages, READMEs,
package install scripts, and error messages the agent reads, any of which may steer it
toward an off-path destination. The agent is assumed cooperative but fallible.

**In scope**
- Outbound HTTP(S) from the sandbox to non-allowlisted hosts
- Outbound HTTP(S) to allowlisted hosts for non-allowlisted methods/paths
- DNS-based exfiltration
- Agent ignoring proxy environment variables

**Out of scope (for now)**
- gVisor sandbox escapes (host kernel compromise)
- Side channels (timing, resource exhaustion)
- Malicious model weights
- Inbound connections (the sandbox accepts none)

**Trust boundaries**
1. Agent process <-> gVisor Sentry (syscall boundary, gVisor's job)
2. Sandbox netns <-> Warden proxy (the only link; enforced by Docker internal network + SG)
3. Warden proxy <-> internet (allowlist enforced here)
