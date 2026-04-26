"""React Flow graph → topological execution plan."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass
class PlanNode:
    id: str
    type: str
    data: dict


def build_topological_plan(definition: dict) -> list[PlanNode]:
    nodes = {n["id"]: n for n in definition.get("nodes", [])}
    edges = definition.get("edges", [])
    in_deg: dict[str, int] = defaultdict(int)
    adj: dict[str, list[str]] = defaultdict(list)

    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s not in nodes or t not in nodes:
            raise ValueError(f"Edge references unknown node: {s} -> {t}")
        adj[s].append(t)
        in_deg[t] += 1

    queue: deque[str] = deque(nid for nid in nodes if in_deg[nid] == 0)
    plan: list[PlanNode] = []
    while queue:
        nid = queue.popleft()
        raw = nodes[nid]
        plan.append(PlanNode(id=nid, type=raw.get("type") or "", data=raw.get("data") or {}))
        for nxt in adj[nid]:
            in_deg[nxt] -= 1
            if in_deg[nxt] == 0:
                queue.append(nxt)

    if len(plan) != len(nodes):
        raise ValueError("Workflow graph has a cycle")
    return plan


def upstream_of(node_id: str, edges: list[dict]) -> list[str]:
    return [e["source"] for e in edges if e.get("target") == node_id]


def downstream_of(node_id: str, edges: list[dict]) -> list[str]:
    return [e["target"] for e in edges if e.get("source") == node_id]
