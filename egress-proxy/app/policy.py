"""Per-agent egress policy checker with domain wildcard and CIDR matching."""

import ipaddress
import re
import socket
from dataclasses import dataclass, field


@dataclass(frozen=True)
class _CompiledRule:
    domain_re: re.Pattern | None
    network: ipaddress.IPv4Network | ipaddress.IPv6Network | None
    ports: list[int]  # empty = all ports allowed


@dataclass
class PolicyChecker:
    """Evaluate whether a (host, port) pair is allowed by an agent's egress rules."""

    rules: list[_CompiledRule] = field(default_factory=list)

    @classmethod
    def from_policy(cls, policy: dict) -> "PolicyChecker":
        compiled: list[_CompiledRule] = []
        for entry in policy.get("allowedEgress", []):
            domain_re = None
            network = None
            ports = [p["port"] for p in entry.get("ports", [])]

            if domain := entry.get("domain"):
                domain_re = _compile_domain(domain)
            if cidr := entry.get("cidr"):
                network = ipaddress.ip_network(cidr, strict=False)

            compiled.append(_CompiledRule(domain_re=domain_re, network=network, ports=ports))
        return cls(rules=compiled)

    def is_allowed(self, host: str, port: int) -> bool:
        for rule in self.rules:
            if not _port_matches(rule.ports, port):
                continue
            if rule.domain_re and rule.domain_re.match(host):
                return True
            if rule.network and _ip_in_network(host, rule.network):
                return True
        return False


def _compile_domain(pattern: str) -> re.Pattern:
    """Compile a domain pattern to regex.

    Supported patterns:
      "*"                  — match all domains
      "example.com"        — exact match
      "*.example.com"      — any subdomain (including example.com itself)
      ".example.com"       — same as *.example.com
    """
    pattern = pattern.lower().strip()
    if pattern == "*":
        return re.compile(r"^.+$", re.IGNORECASE)
    if pattern.startswith("*."):
        base = re.escape(pattern[2:])
        return re.compile(rf"^(.+\.)?{base}$", re.IGNORECASE)
    if pattern.startswith("."):
        base = re.escape(pattern[1:])
        return re.compile(rf"^(.+\.)?{base}$", re.IGNORECASE)
    return re.compile(rf"^{re.escape(pattern)}$", re.IGNORECASE)


def _port_matches(allowed_ports: list[int], port: int) -> bool:
    return not allowed_ports or port in allowed_ports


def _ip_in_network(
    host: str,
    network: ipaddress.IPv4Network | ipaddress.IPv6Network,
) -> bool:
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        # hostname, try DNS resolve
        try:
            addr = ipaddress.ip_address(socket.gethostbyname(host))
        except (socket.gaierror, ValueError):
            return False
    return addr in network
