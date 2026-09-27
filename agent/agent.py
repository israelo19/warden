"""Minimal tool-using agent used by the evaluation harness.

It reads a task from WARDEN_TASK_SPEC (JSON), performs the HTTP fetches the task
asks for, and honors HTTP(S)_PROXY. It stamps every request with X-Warden-Task so
the proxy log can be joined back to the trial. The 'temptations' in a task are
off-path URLs the task materials mention; a well-contained run never reaches them.
"""
import json
import os
import urllib.request

TASK = json.loads(os.environ.get("WARDEN_TASK_SPEC", "{}"))
TASK_ID = os.environ.get("WARDEN_TASK", "manual")


def fetch(url: str) -> tuple[int, int]:
    req = urllib.request.Request(url, headers={"X-Warden-Task": TASK_ID,
                                               "User-Agent": "warden-agent/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, len(r.read())
    except Exception as e:  # blocked, unreachable, or upstream error
        return getattr(e, "code", 0), 0


if __name__ == "__main__":
    for url in TASK.get("required_urls", []):
        print("required", url, fetch(url))
    # Placeholder for the LLM-driven step: the real agent decides on its own whether
    # to follow links found in fetched content. Kept deterministic here for the smoke run.
    for url in TASK.get("temptations", []):
        if os.environ.get("WARDEN_SIMULATE_WANDER") == "1":
            print("wandered", url, fetch(url))
