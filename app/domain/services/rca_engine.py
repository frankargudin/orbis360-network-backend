"""Root Cause Analysis (RCA) Engine.

Algorithm:
1. Build a directed graph from the topology (devices + links)
2. When multiple devices go DOWN, traverse upstream to find common ancestors
3. The node with the most downstream affected devices that is itself DOWN
   is the most probable root cause
4. Weight by: device criticality, position in topology (core > distribution > access)

Strategy: "Upstream Propagation with Weighted Scoring"

Real-world scenarios handled:
- Core switch failure → all downstream APs and switches report DOWN
- Uplink fiber cut → entire floor goes dark
- Single AP failure → only that AP is affected (leaf node, no propagation)
- Cascade detection → distinguish root cause from collateral damage
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class TopologyNode:
    id: UUID
    hostname: str
    device_type: str
    status: str
    is_critical: bool
    parent_id: UUID | None = None
    children: list[UUID] = field(default_factory=list)


@dataclass
class RCAResult:
    root_cause_device_id: UUID
    root_cause_hostname: str
    confidence: float  # 0.0 - 1.0
    affected_device_ids: list[UUID]
    reasoning: str


class RCAEngine:
    """Performs root cause analysis on network topology."""

    # Weights: devices higher in the hierarchy get higher RCA scores
    TYPE_WEIGHTS = {
        "router": 5.0,
        "firewall": 4.5,
        "switch": 3.0,
        "access_point": 1.0,
        "server": 2.0,
        "ups": 4.0,
    }

    def __init__(self):
        self.nodes: dict[UUID, TopologyNode] = {}
        self.adjacency: dict[UUID, list[UUID]] = defaultdict(list)
        self.reverse_adjacency: dict[UUID, list[UUID]] = defaultdict(list)

    def build_topology(self, devices: list[dict], links: list[dict]):
        """Build the internal graph from device and link data."""
        self.nodes.clear()
        self.adjacency.clear()
        self.reverse_adjacency.clear()

        for d in devices:
            node = TopologyNode(
                id=d["id"],
                hostname=d["hostname"],
                device_type=d["device_type"],
                status=d["status"],
                is_critical=d.get("is_critical", False),
                parent_id=d.get("parent_device_id"),
            )
            self.nodes[node.id] = node

        for link in links:
            src = link["source_device_id"]
            tgt = link["target_device_id"]
            if src in self.nodes and tgt in self.nodes:
                self.adjacency[src].append(tgt)
                self.reverse_adjacency[tgt].append(src)
                self.nodes[src].children.append(tgt)

    def find_root_causes(self, down_device_ids: list[UUID]) -> list[RCAResult]:
        """Analyze DOWN devices and return probable root causes, ranked by confidence."""
        if not down_device_ids:
            return []

        down_set = set(down_device_ids)
        candidates: dict[UUID, float] = {}

        for device_id in down_device_ids:
            if device_id not in self.nodes:
                continue

            # Score = (downstream affected count) * type_weight * critical_bonus
            affected = self._count_downstream_affected(device_id, down_set)
            node = self.nodes[device_id]
            type_weight = self.TYPE_WEIGHTS.get(node.device_type, 1.0)
            critical_bonus = 2.0 if node.is_critical else 1.0

            # A device that has no DOWN upstream parents is more likely root cause
            upstream_down = self._has_down_upstream(device_id, down_set)
            upstream_penalty = 0.3 if upstream_down else 1.0

            score = len(affected) * type_weight * critical_bonus * upstream_penalty
            candidates[device_id] = score

        if not candidates:
            return []

        # Sort by score descending
        sorted_candidates = sorted(candidates.items(), key=lambda x: x[1], reverse=True)
        max_score = sorted_candidates[0][1] if sorted_candidates else 1.0

        results = []
        for device_id, score in sorted_candidates[:5]:  # Top 5 candidates
            node = self.nodes[device_id]
            affected = self._count_downstream_affected(device_id, down_set)
            confidence = min(score / max(max_score, 1.0), 1.0)

            has_upstream = self._has_down_upstream(device_id, down_set)
            reasoning = self._build_reasoning(node, affected, has_upstream)

            results.append(
                RCAResult(
                    root_cause_device_id=device_id,
                    root_cause_hostname=node.hostname,
                    confidence=round(confidence, 2),
                    affected_device_ids=list(affected),
                    reasoning=reasoning,
                )
            )

        return results

    def _count_downstream_affected(self, device_id: UUID, down_set: set[UUID]) -> set[UUID]:
        """BFS to find all downstream devices that are also DOWN."""
        visited = set()
        queue = [device_id]
        affected = set()

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            for child in self.adjacency.get(current, []):
                if child in down_set:
                    affected.add(child)
                queue.append(child)

        return affected

    def _has_down_upstream(self, device_id: UUID, down_set: set[UUID]) -> bool:
        """Check if any upstream (parent) device is also DOWN."""
        for parent_id in self.reverse_adjacency.get(device_id, []):
            if parent_id in down_set and parent_id != device_id:
                return True
        # Also check explicit parent_device_id
        node = self.nodes.get(device_id)
        if node and node.parent_id and node.parent_id in down_set:
            return True
        return False

    def _build_reasoning(self, node: TopologyNode, affected: set[UUID], has_upstream: bool) -> str:
        parts = [f"{node.hostname} ({node.device_type}) is DOWN"]
        if affected:
            parts.append(f"with {len(affected)} downstream device(s) also affected")
        if node.is_critical:
            parts.append("and is marked as CRITICAL infrastructure")
        if not has_upstream:
            parts.append("— no upstream device is down, making this the most probable origin")
        else:
            parts.append("— note: an upstream device is also down, which may be the true root cause")
        return "; ".join(parts)
