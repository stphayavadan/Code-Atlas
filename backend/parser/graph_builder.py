"""Graph construction: modules + symbols -> a navigable code graph.

Node taxonomy (the "places" on the map), each tagged with a `level` so the
frontend can do semantic zoom (Google-Maps style):

  level 0  package   top-level folder            -> "continents"
  level 1  module    a .py file                  -> "cities"
  level 2  class     a class definition          -> "districts"
  level 2  function  a top-level function        -> "streets"
  level 3  method    a function inside a class    -> "buildings"

Edge kinds:
  contains   structural nesting (package->module->class->method)
  imports    module A imports module B (intra-repo only)
  calls      symbol A calls symbol B (resolved within the repo where possible)
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

import networkx as nx

from .ast_parser import ModuleInfo, Symbol

LEVEL = {"package": 0, "module": 1, "class": 2, "function": 2, "method": 3}


def _node(graph: nx.DiGraph, node_id: str, **attrs) -> None:
    graph.add_node(node_id, **attrs)


def build_graph(modules: List[ModuleInfo]) -> nx.DiGraph:
    """Build the full code graph from parsed modules."""
    g = nx.DiGraph()

    module_paths = {m.module_path for m in modules}
    # Map a short callee name -> the symbol ids that define it (for call resolution).
    name_to_symbols: Dict[str, List[str]] = defaultdict(list)
    # Map top-level package -> set of module paths (for import resolution).
    package_modules: Dict[str, List[str]] = defaultdict(list)

    # ---- pass 1: create package + module + symbol nodes ----
    packages_seen: set[str] = set()
    for m in modules:
        pkg = m.package
        pkg_id = f"pkg:{pkg}"
        if pkg not in packages_seen:
            _node(g, pkg_id, label=pkg, kind="package", level=LEVEL["package"],
                  module_path=None, package=pkg)
            packages_seen.add(pkg)

        mod_id = f"mod:{m.module_path}"
        _node(g, mod_id,
              label=m.module_path.split(".")[-1],
              full_label=m.module_path,
              kind="module",
              level=LEVEL["module"],
              package=pkg,
              module_path=m.module_path,
              rel_path=m.rel_path,
              line_count=m.line_count,
              docstring=m.docstring or "",
              imports=m.imports,
              parse_error=m.parse_error or "",
              n_symbols=len(m.symbols),
              source=m.source)
        g.add_edge(pkg_id, mod_id, kind="contains")
        package_modules[pkg].append(m.module_path)

        for s in m.symbols:
            _node(g, s.id,
                  label=s.name,
                  full_label=s.qualname,
                  kind=s.kind,
                  level=LEVEL.get(s.kind, 2),
                  package=pkg,
                  module_path=m.module_path,
                  rel_path=m.rel_path,
                  lineno=s.lineno,
                  end_lineno=s.end_lineno,
                  signature=s.signature,
                  docstring=s.docstring or "",
                  decorators=s.decorators,
                  complexity=s.complexity,
                  source=s.source)
            name_to_symbols[s.name].append(s.id)

    # ---- pass 2: containment edges for symbols ----
    for m in modules:
        mod_id = f"mod:{m.module_path}"
        for s in m.symbols:
            parent = s.parent_id if s.parent_id and g.has_node(s.parent_id) else mod_id
            g.add_edge(parent, s.id, kind="contains")

    # ---- pass 3: import edges (intra-repo only) ----
    for m in modules:
        src = f"mod:{m.module_path}"
        for imp in m.imports:
            target_mod = _resolve_import(imp, module_paths)
            if target_mod and target_mod != m.module_path:
                dst = f"mod:{target_mod}"
                if g.has_node(dst):
                    g.add_edge(src, dst, kind="imports")

    # ---- pass 4: call edges (resolved within repo, best-effort) ----
    for m in modules:
        for s in m.symbols:
            for callee in s.calls:
                candidates = name_to_symbols.get(callee, [])
                target = _pick_call_target(candidates, s, m)
                if target and target != s.id:
                    g.add_edge(s.id, target, kind="calls")

    _annotate_metrics(g)
    return g


def _resolve_import(imp: str, module_paths: set[str]) -> Optional[str]:
    """Resolve an import string to an in-repo module path, if it is one.

    Handles "services.MP4_Transcript_Service", "services", and "utilities.utils".
    Returns None for third-party / stdlib imports.
    """
    if imp in module_paths:
        return imp
    # "from services import X" -> imp == "services"; map to package, no single module.
    # Try progressively shorter prefixes matching a known module.
    parts = imp.split(".")
    for i in range(len(parts), 0, -1):
        candidate = ".".join(parts[:i])
        if candidate in module_paths:
            return candidate
    return None


def _pick_call_target(candidates: List[str], caller: Symbol,
                      module: ModuleInfo) -> Optional[str]:
    """Choose the most likely definition for a called name.

    Preference order: same module > imported module > any single match.
    Ambiguous names with many definitions across the repo are dropped to avoid
    a hairball of spurious edges.
    """
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    same_module = [c for c in candidates if c.startswith(f"{module.module_path}::")]
    if len(same_module) == 1:
        return same_module[0]
    if same_module:
        return same_module[0]
    # Too ambiguous across modules -> skip rather than guess wrong.
    return None


def _annotate_metrics(g: nx.DiGraph) -> None:
    """Add degree-based importance so the frontend can size key nodes."""
    for n in g.nodes:
        in_calls = sum(1 for _, _, d in g.in_edges(n, data=True) if d.get("kind") == "calls")
        in_imports = sum(1 for _, _, d in g.in_edges(n, data=True) if d.get("kind") == "imports")
        g.nodes[n]["fan_in"] = in_calls + in_imports
        g.nodes[n]["degree"] = g.degree(n)


def detect_entry_points(g: nx.DiGraph, modules: List[ModuleInfo]) -> List[str]:
    """Heuristically rank likely entry points (where a tour should start).

    Signals: presence of `if __name__ == "__main__"`, a `main` function,
    common entry filenames (main/app/cli/__main__/run), and low import fan-in
    (entry points are imported by few but import many).
    """
    scores: Dict[str, float] = {}
    entry_names = {"main", "app", "cli", "__main__", "run", "server", "manage"}

    for m in modules:
        mod_id = f"mod:{m.module_path}"
        if not g.has_node(mod_id):
            continue
        score = 0.0
        short = m.module_path.split(".")[-1].lower()
        if short in entry_names:
            score += 5.0
        if 'if __name__' in m.source and "__main__" in m.source:
            score += 6.0
        if any(s.name == "main" for s in m.symbols):
            score += 3.0
        # Entry points import a lot, get imported little.
        out_imports = sum(1 for _, _, d in g.out_edges(mod_id, data=True)
                          if d.get("kind") == "imports")
        in_imports = sum(1 for _, _, d in g.in_edges(mod_id, data=True)
                         if d.get("kind") == "imports")
        score += 0.5 * out_imports - 0.7 * in_imports
        scores[mod_id] = score

    ranked = sorted(scores, key=lambda k: scores[k], reverse=True)
    return ranked[:5]
