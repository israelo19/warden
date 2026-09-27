"""Policy loading and matching for Warden.

A policy is deny-by-default. A request is allowed only if some rule matches on
host, port, method, and (optionally) path prefix. Host matching is exact or a
single leading wildcard label (``*.example.com``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import yaml


@dataclass(frozen=True)
class Rule:
    id: str
    host: str
    ports: tuple[int, ...] = (443,)
    methods: tuple[str, ...] = ("GET",)
    paths: tuple[str, ...] = ()  # empty means any path

    def matches_host(self, host: str) -> bool:
        host = host.lower().rstrip(".")
        if self.host.startswith("*."):
            suffix = self.host[1:]  # ".example.com"
            return host.endswith(suffix) and host != suffix[1:]
        return host == self.host

    def matches(self, host: str, port: int, method: str, path: str) -> bool:
        if not self.matches_host(host):
            return False
        if port not in self.ports:
            return False
        if method.upper() not in self.methods:
            return False
        if self.paths and not any(path.startswith(p) for p in self.paths):
            return False
        return True


@dataclass(frozen=True)
class Decision:
    allowed: bool
    rule_id: str | None
    reason: str


@dataclass
class Policy:
    rules: list[Rule] = field(default_factory=list)
    default_allow: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "Policy":
        rules = []
        for r in data.get("rules", []):
            rules.append(
                Rule(
                    id=str(r["id"]),
                    host=str(r["host"]).lower(),
                    ports=tuple(int(p) for p in r.get("ports", [443])),
                    methods=tuple(m.upper() for m in r.get("methods", ["GET"])),
                    paths=tuple(r.get("paths", [])),
                )
            )
        return cls(rules=rules, default_allow=data.get("default", "deny") == "allow")

    @classmethod
    def load(cls, path: str) -> "Policy":
        with open(path) as f:
            return cls.from_dict(yaml.safe_load(f))

    def evaluate(self, host: str, port: int, method: str, path: str = "/") -> Decision:
        for rule in self.rules:
            if rule.matches(host, port, method, path):
                return Decision(True, rule.id, f"matched {rule.id}")
        if self.default_allow:
            return Decision(True, None, "default allow")
        return Decision(False, None, "no matching rule; default deny")

    def evaluate_connect(self, host: str, port: int) -> Decision:
        """HTTPS tunnels: the proxy only sees host:port, never method or path, so a
        CONNECT is allowed if ANY rule permits this host and port. Path/method scoping
        for TLS traffic requires termination at the proxy (see docs/DESIGN.md, gaps)."""
        for rule in self.rules:
            if rule.matches_host(host) and port in rule.ports:
                return Decision(True, rule.id, f"CONNECT host/port matched {rule.id}")
        if self.default_allow:
            return Decision(True, None, "default allow")
        return Decision(False, None, "no rule permits host/port; default deny")

    def hosts(self) -> Iterable[str]:
        return (r.host for r in self.rules)
