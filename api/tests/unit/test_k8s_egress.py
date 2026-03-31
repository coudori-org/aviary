"""Unit tests for NetworkPolicy egress rule builder."""

import sys
from pathlib import Path

# Ensure app package is importable when running standalone
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.services.k8s_service import _build_egress_rules


def test_default_egress_rules_no_custom():
    """Default policy: only DNS + platform services."""
    rules = _build_egress_rules({})
    assert len(rules) == 2
    # DNS rule
    assert rules[0]["ports"] == [{"port": 53, "protocol": "UDP"}]
    # Platform services rule
    assert rules[1]["ports"] == [{"port": 8080, "protocol": "TCP"}]


def test_egress_rules_with_cidr_and_ports():
    """CIDR-based entry becomes a direct NetworkPolicy rule."""
    policy = {
        "allowedEgress": [
            {"name": "GitHub", "cidr": "140.82.112.0/20", "ports": [{"port": 443, "protocol": "TCP"}]},
        ],
    }
    rules = _build_egress_rules(policy)
    assert len(rules) == 3
    custom = rules[2]
    assert custom["to"] == [{"ipBlock": {"cidr": "140.82.112.0/20"}}]
    assert custom["ports"] == [{"port": 443, "protocol": "TCP"}]


def test_egress_rules_cidr_without_ports():
    """CIDR rule without ports allows all ports."""
    policy = {
        "allowedEgress": [
            {"name": "Internal", "cidr": "10.0.0.0/8"},
        ],
    }
    rules = _build_egress_rules(policy)
    assert len(rules) == 3
    custom = rules[2]
    assert custom["to"] == [{"ipBlock": {"cidr": "10.0.0.0/8"}}]
    assert "ports" not in custom


def test_domain_entries_not_in_network_policy():
    """Domain-based entries are enforced by egress-proxy only, not NetworkPolicy."""
    policy = {
        "allowedEgress": [
            {"name": "GitHub", "domain": "*.github.com"},
            {"name": "NPM", "domain": "registry.npmjs.org"},
        ],
    }
    rules = _build_egress_rules(policy)
    # Only default 2 rules — domain entries should NOT appear
    assert len(rules) == 2


def test_mixed_cidr_and_domain():
    """Only CIDR entries become NetworkPolicy rules; domain entries are skipped."""
    policy = {
        "allowedEgress": [
            {"name": "S3", "cidr": "52.216.0.0/15", "ports": [{"port": 443}]},
            {"name": "GitHub", "domain": "*.github.com"},
            {"name": "Internal", "cidr": "10.0.0.0/8"},
        ],
    }
    rules = _build_egress_rules(policy)
    assert len(rules) == 4  # 2 default + 2 CIDR (domain skipped)
