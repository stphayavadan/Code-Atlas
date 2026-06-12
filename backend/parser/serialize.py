"""Serialize the code graph + layout into the JSON the frontend consumes.

The output is a single self-contained document:

  {
    "repo": {...metadata...},
    "entry_points": ["mod:main", ...],
    "nodes": [ {id, label, kind, level, x, y, size, color, ...}, ... ],
    "edges": [ {source, target, kind}, ... ],
    "stats": {...}
  }

Node `size` and `color` are computed here (deterministically) so the frontend
can render immediately without recomputing styling rules. Colors follow a
dark-theme palette keyed by node kind.
"""
from __future__ import annotations

from typing import Dict, List

import networkx as nx

# Dark-cinematic palette: luminous accents on a near-black world.
KIND_COLORS = {
    "package":  "#7c5cff",   # violet  - continents
    "module":   "#22d3ee",   # cyan    - cities
    "class":    "#f59e0b",   # amber   - districts
    "function": "#34d399",   # emerald - streets
    "method":   "#f472b6",   # pink    - buildings
}

KIND_BASE_SIZE = {
    "package": 26.0,
    "module": 14.0,
    "class": 9.0,
    "function": 7.0,
    "method": 5.0,
}


def _node_size(kind: str, attrs: dict) -> float:
    base = KIND_BASE_SIZE.get(kind, 6.0)
    # Modules grow with line count; symbols grow with fan-in + complexity.
    if kind == "module":
        return base + min(18.0, (attrs.get("line_count", 0) / 40.0))
    fan_in = attrs.get("fan_in", 0)
    complexity = attrs.get("complexity", 1)
    return base + min(12.0, fan_in * 1.6 + complexity * 0.4)


def graph_to_dict(
    g: nx.DiGraph,
    layout: Dict[str, Dict[str, float]],
    entry_points: List[str],
    repo_meta: dict,
) -> dict:
    nodes = []
    for n, attrs in g.nodes(data=True):
        kind = attrs.get("kind", "module")
        pos = layout.get(n, {"x": 0.0, "y": 0.0})
        nodes.append({
            "id": n,
            "label": attrs.get("label", n),
            "fullLabel": attrs.get("full_label", attrs.get("label", n)),
            "kind": kind,
            "level": attrs.get("level", 1),
            "x": pos["x"],
            "y": pos["y"],
            "size": round(_node_size(kind, attrs), 2),
            "color": KIND_COLORS.get(kind, "#9ca3af"),
            "package": attrs.get("package"),
            "modulePath": attrs.get("module_path"),
            "relPath": attrs.get("rel_path"),
            "lineno": attrs.get("lineno"),
            "endLineno": attrs.get("end_lineno"),
            "lineCount": attrs.get("line_count"),
            "signature": attrs.get("signature", ""),
            "docstring": attrs.get("docstring", ""),
            "decorators": attrs.get("decorators", []),
            "complexity": attrs.get("complexity", 1),
            "fanIn": attrs.get("fan_in", 0),
            "isEntry": n in entry_points,
            # Source is included for symbols/modules so the UI can show code blocks.
            "source": attrs.get("source", "")[:8000],
        })

    edges = []
    for u, v, d in g.edges(data=True):
        edges.append({
            "source": u,
            "target": v,
            "kind": d.get("kind", "contains"),
        })

    stats = {
        "nodeCount": g.number_of_nodes(),
        "edgeCount": g.number_of_edges(),
        "byKind": _count_by_kind(g),
    }

    return {
        "repo": repo_meta,
        "entryPoints": entry_points,
        "nodes": nodes,
        "edges": edges,
        "stats": stats,
    }


def _count_by_kind(g: nx.DiGraph) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for _, attrs in g.nodes(data=True):
        k = attrs.get("kind", "?")
        counts[k] = counts.get(k, 0) + 1
    return counts
