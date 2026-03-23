"""
freedom.py — F = P/D (hypothesis under test, NOT proven law).
P_spatial from BFS (HL-12). Old P=log2(N)*T formula DEAD (R²=0.014).
F = clip(P/D, 0.0, 1.0)
"""
from __future__ import annotations
from collections import deque
from .rooms import ROOMS, ADJACENCY


def bfs_distances(source: str = "Hall_GF") -> dict[str, int]:
    """BFS shortest path from source to all rooms. O(V+E)."""
    visited = {source: 0}
    q = deque([source])
    while q:
        node = q.popleft()
        for nbr in ADJACENCY.get(node, []):
            if nbr not in visited:
                visited[nbr] = visited[node] + 1
                q.append(nbr)
    # Any room not reachable gets max+1
    if visited:
        max_d = max(visited.values())
        for rid in ROOMS:
            if rid not in visited:
                visited[rid] = max_d + 1
    return visited


def compute_P_spatial(room_id: str, distances: dict[str, int]) -> float:
    """
    P_spatial = 1 - (d / max_d)  → [0, 1], Hall_GF = 1.0 reference.
    BFS distance from Hall_GF (main entrance = highest P).
    """
    max_d = max(distances.values()) if distances else 1
    d = distances.get(room_id, max_d)
    return 1.0 / (1.0 + d / max(max_d, 1))


def compute_F(P_spatial: float, D_total: float) -> float:
    """
    F = P / D  (hypothesis under test).
    Clipped to [0, 1]. F > 1 impossible by construction when D >= P.
    """
    if D_total <= 0:
        return 0.0
    return min(1.0, max(0.0, P_spatial / D_total))


# Pre-compute distances at module load (BFS from Hall_GF)
_DISTANCES = bfs_distances("Hall_GF")
_MAX_DIST = max(_DISTANCES.values()) if _DISTANCES else 1

P_SPATIAL: dict[str, float] = {
    rid: compute_P_spatial(rid, _DISTANCES) for rid in ROOMS
}

# Sanity check: Hall_GF should have the highest P
assert P_SPATIAL.get("Hall_GF", 0) == max(P_SPATIAL.values()), \
    "Hall_GF must have highest P_spatial — BFS from entrance"
