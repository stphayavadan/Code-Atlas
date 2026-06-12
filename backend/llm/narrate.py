"""Narration: Azure Foundry turns graph nodes into plain-language explanations.

Two surfaces:
  - narrate_node(node, context)  : one rich explanation for a single place on
                                    the map (shown when a user clicks / the tour
                                    stops there).
  - narrate_overview(doc)        : the opening "establishing shot" narration for
                                    the whole repo.

We never dump the entire codebase at the model. Each call carries only the
relevant slice: the node's own source plus a compact description of its
neighbours (what it imports / calls / is called by). This keeps calls fast,
cheap, and on-topic — and is what makes the experience feel like a guide who
knows *this* spot, not a generic summarizer.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .client import call_model, extract_text, MODEL_FAST

NODE_SYSTEM = """You are the narrator of an interactive, cinematic "guided tour" \
of a software codebase — think a museum audio guide, but for code. You are \
standing at one specific place on the map and explaining it to a developer who \
has never seen this codebase before.

Voice & style:
- Warm, confident, concise. Spoken aloud, so write for the ear: short sentences, \
no bullet symbols, no markdown, no code fences.
- Lead with the PURPOSE ("This is where..."), then HOW it works at a high level, \
then how it connects to the rest of the system.
- Explain intent and design, not a line-by-line readthrough. Mention the one \
interesting or non-obvious thing if there is one.
- 2 to 4 sentences. Never exceed 90 words. Do not invent behaviour you cannot \
see in the provided code."""

OVERVIEW_SYSTEM = """You are the opening narrator of a cinematic guided tour of a \
codebase. The camera is pulled all the way back, showing the whole map. Give a \
warm, vivid 3-to-4-sentence establishing shot: what this project IS, its major \
regions (packages), and where a newcomer's eye should go first. Spoken aloud — \
no markdown, no lists, no code. Never exceed 100 words."""


def _neighbour_summary(node_id: str, doc: dict) -> Dict[str, List[str]]:
    """Compact description of a node's graph neighbourhood for context."""
    by_id = {n["id"]: n for n in doc["nodes"]}
    imports, calls, called_by, contains = [], [], [], []
    for e in doc["edges"]:
        if e["source"] == node_id:
            tgt = by_id.get(e["target"], {})
            label = tgt.get("fullLabel") or tgt.get("label", e["target"])
            if e["kind"] == "imports":
                imports.append(label)
            elif e["kind"] == "calls":
                calls.append(label)
            elif e["kind"] == "contains":
                contains.append(label)
        elif e["target"] == node_id and e["kind"] == "calls":
            src = by_id.get(e["source"], {})
            called_by.append(src.get("fullLabel") or src.get("label", e["source"]))
    return {
        "imports": imports[:12],
        "calls": calls[:12],
        "calledBy": called_by[:12],
        "contains": contains[:20],
    }


def _node_context_block(node: dict, neigh: Dict[str, List[str]], repo_name: str) -> str:
    lines = [
        f"Repository: {repo_name}",
        f"Kind: {node['kind']}",
        f"Name: {node.get('fullLabel') or node.get('label')}",
    ]
    if node.get("relPath"):
        lines.append(f"File: {node['relPath']}")
    if node.get("signature"):
        lines.append(f"Signature: {node['signature']}")
    if node.get("docstring"):
        lines.append(f"Docstring: {node['docstring'][:400]}")
    if node.get("decorators"):
        lines.append(f"Decorators: {', '.join(node['decorators'])}")
    if neigh["contains"]:
        lines.append(f"Contains: {', '.join(neigh['contains'])}")
    if neigh["imports"]:
        lines.append(f"Imports (in-repo): {', '.join(neigh['imports'])}")
    if neigh["calls"]:
        lines.append(f"Calls: {', '.join(neigh['calls'])}")
    if neigh["calledBy"]:
        lines.append(f"Called by: {', '.join(neigh['calledBy'])}")

    src = node.get("source", "")
    if src:
        # Cap source so the prompt stays lean; head of the block is the most telling.
        lines.append("\nSource:\n" + src[:3500])
    return "\n".join(lines)


def narrate_node(node: dict, doc: dict, model: str = MODEL_FAST) -> str:
    """Generate the spoken explanation for one node."""
    repo_name = doc.get("repo", {}).get("name", "this project")
    neigh = _neighbour_summary(node["id"], doc)
    context = _node_context_block(node, neigh, repo_name)

    resp = call_model(
        system=NODE_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"Narrate this stop on the tour.\n\n{context}",
        }],
        model=model,
        max_tokens=320,
        temperature=0.4,
    )
    return extract_text(resp)


def narrate_overview(doc: dict, model: str = MODEL_FAST) -> str:
    """Generate the opening establishing-shot narration for the whole repo."""
    repo = doc.get("repo", {})
    packages: Dict[str, int] = {}
    modules_by_pkg: Dict[str, List[str]] = {}
    for n in doc["nodes"]:
        if n["kind"] == "module":
            pkg = n.get("package", "(root)")
            packages[pkg] = packages.get(pkg, 0) + 1
            modules_by_pkg.setdefault(pkg, []).append(n["label"])

    entry_labels = []
    by_id = {n["id"]: n for n in doc["nodes"]}
    for ep in doc.get("entryPoints", [])[:3]:
        if ep in by_id:
            entry_labels.append(by_id[ep].get("fullLabel") or by_id[ep]["label"])

    region_lines = []
    for pkg, mods in modules_by_pkg.items():
        region_lines.append(f"  {pkg}: {', '.join(mods[:8])}")

    context = (
        f"Project: {repo.get('name')}\n"
        f"Language: Python\n"
        f"Files: {repo.get('fileCount')}, total lines: {repo.get('totalLines')}\n"
        f"Likely entry points: {', '.join(entry_labels) or 'unknown'}\n"
        f"Regions (packages) and their modules:\n" + "\n".join(region_lines)
    )

    resp = call_model(
        system=OVERVIEW_SYSTEM,
        messages=[{"role": "user", "content": f"Open the tour.\n\n{context}"}],
        model=model,
        max_tokens=320,
        temperature=0.5,
    )
    return extract_text(resp)
