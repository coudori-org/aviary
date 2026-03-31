"""Unit tests for egress-proxy PolicyChecker."""

import importlib.util
from pathlib import Path

# Load from egress-proxy directly (avoids name collision with api's `app` package)
_spec = importlib.util.spec_from_file_location(
    "egress_policy",
    Path(__file__).resolve().parents[3] / "egress-proxy" / "app" / "policy.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
PolicyChecker = _mod.PolicyChecker


def test_empty_policy_denies_all():
    checker = PolicyChecker.from_policy({})
    assert not checker.is_allowed("example.com", 443)
    assert not checker.is_allowed("10.0.0.1", 80)


def test_exact_domain_match():
    checker = PolicyChecker.from_policy({
        "allowedEgress": [{"name": "GH", "domain": "api.github.com"}],
    })
    assert checker.is_allowed("api.github.com", 443)
    assert checker.is_allowed("api.github.com", 80)
    assert not checker.is_allowed("github.com", 443)
    assert not checker.is_allowed("evil-api.github.com", 443)


def test_wildcard_domain_match():
    checker = PolicyChecker.from_policy({
        "allowedEgress": [{"name": "GH", "domain": "*.github.com"}],
    })
    assert checker.is_allowed("api.github.com", 443)
    assert checker.is_allowed("raw.github.com", 443)
    # *.github.com also matches github.com itself
    assert checker.is_allowed("github.com", 443)
    assert not checker.is_allowed("evil.com", 443)


def test_dot_prefix_domain_match():
    """'.example.com' should behave like '*.example.com'."""
    checker = PolicyChecker.from_policy({
        "allowedEgress": [{"name": "Ex", "domain": ".example.com"}],
    })
    assert checker.is_allowed("sub.example.com", 443)
    assert checker.is_allowed("example.com", 443)
    assert not checker.is_allowed("notexample.com", 443)


def test_domain_case_insensitive():
    checker = PolicyChecker.from_policy({
        "allowedEgress": [{"name": "GH", "domain": "API.GitHub.COM"}],
    })
    assert checker.is_allowed("api.github.com", 443)
    assert checker.is_allowed("API.GITHUB.COM", 443)


def test_cidr_match():
    checker = PolicyChecker.from_policy({
        "allowedEgress": [{"name": "Internal", "cidr": "10.0.0.0/8"}],
    })
    assert checker.is_allowed("10.0.0.1", 80)
    assert checker.is_allowed("10.255.255.255", 443)
    assert not checker.is_allowed("11.0.0.1", 80)


def test_port_filtering():
    checker = PolicyChecker.from_policy({
        "allowedEgress": [
            {"name": "HTTPS only", "domain": "api.github.com", "ports": [{"port": 443}]},
        ],
    })
    assert checker.is_allowed("api.github.com", 443)
    assert not checker.is_allowed("api.github.com", 80)


def test_no_ports_means_all_ports():
    checker = PolicyChecker.from_policy({
        "allowedEgress": [{"name": "All ports", "domain": "example.com"}],
    })
    assert checker.is_allowed("example.com", 80)
    assert checker.is_allowed("example.com", 443)
    assert checker.is_allowed("example.com", 8080)


def test_mixed_cidr_and_domain():
    checker = PolicyChecker.from_policy({
        "allowedEgress": [
            {"name": "Internal", "cidr": "10.0.0.0/8"},
            {"name": "GitHub", "domain": "*.github.com", "ports": [{"port": 443}]},
        ],
    })
    assert checker.is_allowed("10.0.0.1", 80)
    assert checker.is_allowed("api.github.com", 443)
    assert not checker.is_allowed("api.github.com", 80)
    assert not checker.is_allowed("evil.com", 443)


def test_multiple_rules_any_match():
    checker = PolicyChecker.from_policy({
        "allowedEgress": [
            {"name": "Rule A", "domain": "a.example.com", "ports": [{"port": 443}]},
            {"name": "Rule B", "domain": "b.example.com", "ports": [{"port": 80}]},
        ],
    })
    assert checker.is_allowed("a.example.com", 443)
    assert checker.is_allowed("b.example.com", 80)
    assert not checker.is_allowed("a.example.com", 80)
    assert not checker.is_allowed("b.example.com", 443)


def test_wildcard_star_allows_all_domains():
    """domain: '*' allows all external traffic."""
    checker = PolicyChecker.from_policy({
        "allowedEgress": [{"name": "Allow All", "domain": "*"}],
    })
    assert checker.is_allowed("anything.example.com", 443)
    assert checker.is_allowed("api.github.com", 80)
    assert checker.is_allowed("evil.hacker.org", 8080)


def test_wildcard_star_with_port_restriction():
    """domain: '*' with port restriction only allows specified ports."""
    checker = PolicyChecker.from_policy({
        "allowedEgress": [{"name": "HTTPS Only", "domain": "*", "ports": [{"port": 443}]}],
    })
    assert checker.is_allowed("anything.com", 443)
    assert not checker.is_allowed("anything.com", 80)
