"""Warden allowlisting forward proxy.

Single-process, stdlib only. Handles plain HTTP forwarding and HTTPS CONNECT
tunnels. Every decision is appended to a JSONL access log that the evaluation
harness reads to compute unauthorized egress rates.

    python proxy/egress_proxy.py --policy policy/policy.yaml --port 3128
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import select
import socket
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from proxy.policy import Policy  # noqa: E402

POLICY: Policy
LOG_PATH = os.environ.get("WARDEN_LOG", "warden-access.jsonl")


def log(record: dict) -> None:
    record["ts"] = time.time()
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _task_id(self) -> str:
        # The agent stamps every request so the harness can attribute egress to a trial.
        return self.headers.get("X-Warden-Task", "unknown")

    def _deny(self, host: str, port: int, method: str, path: str, reason: str) -> None:
        log({"task": self._task_id(), "host": host, "port": port, "method": method,
             "path": path, "allowed": False, "reason": reason})
        self.send_response(403, "Blocked by Warden policy")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_CONNECT(self) -> None:  # HTTPS tunnel
        host, _, port_s = self.path.partition(":")
        port = int(port_s or 443)
        d = POLICY.evaluate_connect(host, port)
        if not d.allowed:
            return self._deny(host, port, "CONNECT", "/", d.reason)
        try:
            upstream = socket.create_connection((host, port), timeout=10)
        except OSError as e:
            return self._deny(host, port, "CONNECT", "/", f"upstream error: {e}")
        log({"task": self._task_id(), "host": host, "port": port, "method": "CONNECT",
             "path": "/", "allowed": True, "rule": d.rule_id})
        self.send_response(200, "Connection Established")
        self.end_headers()
        self._pipe(self.connection, upstream)

    def _pipe(self, a: socket.socket, b: socket.socket) -> None:
        socks = [a, b]
        while True:
            r, _, x = select.select(socks, [], socks, 30)
            if x or not r:
                break
            for s in r:
                data = s.recv(65536)
                if not data:
                    return
                (b if s is a else a).sendall(data)

    def _forward(self) -> None:  # plain HTTP
        u = urlsplit(self.path)
        host, port = u.hostname or "", u.port or 80
        path = u.path or "/"
        d = POLICY.evaluate(host, port, self.command, path)
        if not d.allowed:
            return self._deny(host, port, self.command, path, d.reason)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        conn = http.client.HTTPConnection(host, port, timeout=10)
        hdrs = {k: v for k, v in self.headers.items()
                if k.lower() not in ("proxy-connection", "x-warden-task")}
        conn.request(self.command, path + (f"?{u.query}" if u.query else ""), body, hdrs)
        resp = conn.getresponse()
        data = resp.read()
        log({"task": self._task_id(), "host": host, "port": port, "method": self.command,
             "path": path, "allowed": True, "rule": d.rule_id, "status": resp.status})
        self.send_response(resp.status)
        for k, v in resp.getheaders():
            if k.lower() not in ("transfer-encoding", "connection"):
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = do_PATCH = _forward

    def log_message(self, *args) -> None:  # quiet; we keep our own log
        pass


def main() -> None:
    global POLICY
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", required=True)
    ap.add_argument("--port", type=int, default=3128)
    ap.add_argument("--bind", default="0.0.0.0")
    a = ap.parse_args()
    POLICY = Policy.load(a.policy)
    print(f"[warden] policy loaded: {len(POLICY.rules)} rules, default "
          f"{'allow' if POLICY.default_allow else 'deny'}; listening on {a.bind}:{a.port}")
    ThreadingHTTPServer((a.bind, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
