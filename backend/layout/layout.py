"""Map layout: assign 2D coordinates so the graph reads like a map.

Strategy (the thing that turns a hairball into a "map"):
  1. Place each PACKAGE region at a point on a circle (continents spread out).
  2. Within each package, lay out its modules in a small local cluster around
     the package center using a force-directed layout on the intra-package
     import graph.
  3. Place each module's child symbols (classes/functions/methods) in a tight
     radial "satellite" ring around their module, nested for methods.

Coordinates are computed once and cached. They are stable (seeded) so the map
does not jump around between runs. The frontend treats these as world-space
positions and does semantic-zoom level-of-detail on top.
"""
from __future__ import annotations

import math
from typing import Dict, List, Tuple

import networkx as nx

# World-space scale knobs (arbitrary units; the frontend camera handles zoom).
PACKAGE_RING_RADIUS = 4000.0     # how far package centers sit from origin
MODULE_SPREAD = 900.0            # radius of the module cluster within a package
SYMBOL_RING_BASE = 130.0         # base radius for a module's symbol ring
SYMBOL_RING_STEP = 60.0          # extra radius per ring of crowding
METHOD_RING = 55.0               # radius of a method ring around its class


def _packages(g: nx.DiGraph) -> List[str]:
    return sorted(n for n, d in g.nodes(data=True) if d.get("kind") == "package")


def _children(g: nx.DiGraph, node: str, kind: str | None = None) -> List[str]:
    out = []
    for _, child, d in g.out_edges(node, data=True):
        if d.get("kind") != "contains":
            continue
        if kind is None or g.nodes[child].get("kind") == kind:
            out.append(child)
    return out


def _module_cluster_positions(g: nx.DiGraph, modules: List[str],
                              center: Tuple[float, float]) -> Dict[str, Tuple[float, float]]:
    """Force-directed layout of modules within one package, recentered."""
    if not modules:
        return {}
    if len(modules) == 1:
        return {modules[0]: center}

    sub = nx.Graph()
    sub.add_nodes_from(modules)
    # Connect modules that import each other (intra-package structure).
    mod_set = set(modules)
    for u in modules:
        for _, v, d in g.out_edges(u, data=True):
            if d.get("kind") == "imports" and v in mod_set:
                sub.add_edge(u, v)

    # Deterministic spring layout (seeded) so the map is stable.
    pos = nx.spring_layout(sub, seed=42, k=0.9, iterations=120)
    # Normalize to MODULE_SPREAD and recenter on the package center.
    cx, cy = center
    out: Dict[str, Tuple[float, float]] = {}
    for n, (x, y) in pos.items():
        out[n] = (cx + x * MODULE_SPREAD, cy + y * MODULE_SPREAD)
    return out


def _symbol_positions(g: nx.DiGraph, module: str,
                      module_pos: Tuple[float, float]) -> Dict[str, Tuple[float, float]]:
    """Radial placement of a module's symbols, with methods orbiting classes."""
    out: Dict[str, Tuple[float, float]] = {}
    mx, my = module_pos

    top_symbols = _children(g, module)  # classes + top-level functions
    # Stable ordering by line number for a natural reading flow.
    top_symbols.sort(key=lambda s: g.nodes[s].get("lineno", 0))

    n = len(top_symbols)
    if n == 0:
        return out

    for i, sym in enumerate(top_symbols):
        angle = (2 * math.pi * i) / n
        ring = SYMBOL_RING_BASE + SYMBOL_RING_STEP * (n // 12)
        sx = mx + ring * math.cos(angle)
        sy = my + ring * math.sin(angle)
        out[sym] = (sx, sy)

        # Methods orbit their class node.
        if g.nodes[sym].get("kind") == "class":
            methods = _children(g, sym)
            methods.sort(key=lambda s: g.nodes[s].get("lineno", 0))
            m = len(methods)
            for j, meth in enumerate(methods):
                ma = (2 * math.pi * j) / max(m, 1)
                out[meth] = (sx + METHOD_RING * math.cos(ma),
                             sy + METHOD_RING * math.sin(ma))
    return out


def compute_layout(g: nx.DiGraph) -> Dict[str, Dict[str, float]]:
    """Return {node_id: {"x": float, "y": float}} for every node in the graph."""
    positions: Dict[str, Tuple[float, float]] = {}

    packages = _packages(g)
    n_pkg = len(packages)

    for pi, pkg in enumerate(packages):
        # Package center on a ring; single package sits at origin.
        if n_pkg == 1:
            center = (0.0, 0.0)
        else:
            angle = (2 * math.pi * pi) / n_pkg
            center = (PACKAGE_RING_RADIUS * math.cos(angle),
                      PACKAGE_RING_RADIUS * math.sin(angle))
        positions[pkg] = center

        modules = _children(g, pkg, kind="module")
        modules.sort()
        mod_pos = _module_cluster_positions(g, modules, center)
        for mod, p in mod_pos.items():
            positions[mod] = p
            positions.update(_symbol_positions(g, mod, p))

    # Any stragglers (shouldn't happen) get parked near origin deterministically.
    for i, n in enumerate(g.nodes):
        if n not in positions:
            positions[n] = (50.0 * (i % 10), 50.0 * (i // 10))

    return {n: {"x": float(x), "y": float(y)} for n, (x, y) in positions.items()}
