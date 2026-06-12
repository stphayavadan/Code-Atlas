"""End-to-end structural pipeline: repo path -> graph.json document.

This is the deterministic, LLM-free half of the system. It is fast, cached,
and the foundation the narration / tour / Q&A layers build on.
"""
from __future__ import annotations

import os
from typing import Optional

import networkx as nx

from parser.ingest import ingest_repository
from parser.ast_parser import parse_all
from parser.graph_builder import build_graph, detect_entry_points
from parser.serialize import graph_to_dict
from layout.layout import compute_layout


def build_repo_document(repo_path: str, repo_name: Optional[str] = None) -> dict:
    """Parse a repository and return the full serializable graph document."""
    repo_path = os.path.abspath(repo_path)
    name = repo_name or os.path.basename(repo_path.rstrip("/\\"))

    files = ingest_repository(repo_path)
    modules = parse_all(files)
    g: nx.DiGraph = build_graph(modules)
    layout = compute_layout(g)
    entry_points = detect_entry_points(g, modules)

    total_lines = sum(m.line_count for m in modules)
    repo_meta = {
        "name": name,
        "path": repo_path,
        "fileCount": len(files),
        "totalLines": total_lines,
        "language": "python",
        "parseErrors": [
            {"module": m.module_path, "error": m.parse_error}
            for m in modules if m.parse_error
        ],
    }

    return graph_to_dict(g, layout, entry_points, repo_meta)
