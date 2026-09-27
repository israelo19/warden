import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from proxy.policy import Policy

HERE = os.path.dirname(os.path.abspath(__file__))
POL = Policy.load(os.path.join(HERE, "..", "policy", "policy.yaml"))


def test_default_deny_unknown_host():
    d = POL.evaluate("evil.example", 443, "GET", "/")
    assert not d.allowed and d.rule_id is None


def test_allow_pypi_simple_get():
    d = POL.evaluate("pypi.org", 443, "GET", "/simple/requests/")
    assert d.allowed and d.rule_id == "pypi-read"


def test_deny_pypi_post_same_host():
    # Same allowlisted host, disallowed method: this is the case host-only
    # blocking (iptables by IP) cannot catch.
    d = POL.evaluate("pypi.org", 443, "POST", "/simple/requests/")
    assert not d.allowed


def test_deny_pypi_off_path():
    d = POL.evaluate("pypi.org", 443, "GET", "/account/login")
    assert not d.allowed


def test_deny_wrong_port():
    d = POL.evaluate("pypi.org", 8443, "GET", "/simple/")
    assert not d.allowed


def test_wildcard_host():
    p = Policy.from_dict({"default": "deny", "rules": [
        {"id": "w", "host": "*.internal.test", "ports": [443], "methods": ["GET"]}]})
    assert p.evaluate("a.internal.test", 443, "GET").allowed
    assert not p.evaluate("internal.test", 443, "GET").allowed  # bare apex excluded
    assert not p.evaluate("ainternal.test", 443, "GET").allowed


def test_case_insensitive_host_and_method():
    d = POL.evaluate("PyPI.org.", 443, "get", "/simple/")
    assert d.allowed


def test_connect_allowed_by_host_port_only():
    # TLS tunnel: no path visible, so host+port on any rule is sufficient.
    assert POL.evaluate_connect("pypi.org", 443).allowed
    assert not POL.evaluate_connect("pypi.org", 8443).allowed
    assert not POL.evaluate_connect("pastebin.com", 443).allowed
