"""Tour sequencing: Claude designs the teaching order for the map.

Given the repo's structure (not its full source), Claude chooses an ordered
list of stops — entry point first, then core abstractions, then supporting
cast — and a one-line reason for each stop. This is the "guided tour" spine;
the per-stop narration is filled in lazily by narrate.py as the camera arrives.

We use the SMART model here because ordering requires reasoning about the whole
system at once, but the payload is tiny (just the node catalog), so it is cheap.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from .client import call_claude, MODEL_SMART

TOUR_TOOL = {
    "name": "propose_tour",
    "description": "Propose the ordered sequence of stops for a guided code tour.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "A short, inviting title for this tour (max 8 words).",
            },
            "stops": {
                "type": "array",
                "description": "Ordered tour stops, 6 to 12 of them. Start at the entry "
                               "point, move to core abstractions, then supporting modules. "
                               "Each id MUST be one of the provided node ids.",
                "items": {
                    "type": "object",
                    "properties": {
                        "nodeId": {"type": "string", "description": "Exact node id to visit."},
                        "reason": {"type": "string",
                                   "description": "One short sentence: why this stop, why now."},
                    },
                    "required": ["nodeId", "reason"],
                },
            },
        },
        "required": ["title", "stops"],
    },
}

TOUR_SYSTEM = """You are an expert software educator designing a guided tour of a \
codebase for a newcomer. You are given a catalog of the codebase's modules, \
classes and key functions, plus how they connect. Design the best LEARNING \
ORDER: begin at the natural entry point, reveal the core abstractions the system \
is built on, then the supporting pieces. Prefer modules and important classes/\
functions as stops; skip trivial helpers. Choose 6 to 12 stops. Call the \
propose_tour tool with your plan. Every nodeId must be exactly one from the \
catalog."""


def _build_catalog(doc: dict) -> str:
    """Compact, model-readable catalog of tour-worthy nodes."""
    by_id = {n["id"]: n for n in doc["nodes"]}
    # Count call/import fan-in to surface importance.
    lines: List[str] = []

    # Modules first (with their notable symbols inline), then standalone importance.
    modules = [n for n in doc["nodes"] if n["kind"] == "module"]
    modules.sort(key=lambda n: (n.get("package", ""), n.get("label", "")))

    entry_set = set(doc.get("entryPoints", []))

    for m in modules:
        tag = " [ENTRY]" if m["id"] in entry_set else ""
        doc_hint = (m.get("docstring") or "").strip().replace("\n", " ")[:120]
        lines.append(f'- {m["id"]}{tag} | module | {m.get("relPath","")} '
                     f'| {m.get("lineCount",0)} lines'
                     + (f' | "{doc_hint}"' if doc_hint else ""))
        # Child classes/functions of this module.
        children = [n for n in doc["nodes"]
                    if n.get("modulePath") == m.get("modulePath")
                    and n["kind"] in ("class", "function")]
        children.sort(key=lambda n: n.get("lineno", 0))
        for c in children:
            cd = (c.get("docstring") or "").strip().replace("\n", " ")[:80]
            lines.append(f'    - {c["id"]} | {c["kind"]} | {c.get("signature","")}'
                         f' | fanIn={c.get("fanIn",0)}'
                         + (f' | "{cd}"' if cd else ""))
    return "\n".join(lines)


def design_tour(doc: dict, model: str = MODEL_SMART) -> Dict[str, Any]:
    """Return {'title': str, 'stops': [{'nodeId','reason'}, ...]} for a valid tour."""
    catalog = _build_catalog(doc)
    repo = doc.get("repo", {})
    valid_ids = {n["id"] for n in doc["nodes"]}

    user = (
        f"Codebase: {repo.get('name')} (Python, {repo.get('fileCount')} files, "
        f"{repo.get('totalLines')} lines).\n\n"
        f"Node catalog (use these exact ids):\n{catalog}\n\n"
        f"Design the guided tour now via the propose_tour tool."
    )

    resp = call_claude(
        system=TOUR_SYSTEM,
        messages=[{"role": "user", "content": user}],
        model=model,
        max_tokens=1500,
        tools=[TOUR_TOOL],
        tool_choice={"type": "tool", "name": "propose_tour"},
    )

    from .client import extract_tool_use
    block = extract_tool_use(resp, "propose_tour")
    if not block:
        # Fallback: entry points + highest-fanIn nodes.
        return _fallback_tour(doc)

    plan = block.get("input", {})
    # Validate + drop any hallucinated ids, preserving order.
    clean_stops = []
    seen = set()
    for stop in plan.get("stops", []):
        nid = stop.get("nodeId")
        if nid in valid_ids and nid not in seen:
            clean_stops.append({"nodeId": nid, "reason": stop.get("reason", "")})
            seen.add(nid)
    if not clean_stops:
        return _fallback_tour(doc)

    return {"title": plan.get("title", f"A tour of {repo.get('name')}"),
            "stops": clean_stops}


def _fallback_tour(doc: dict) -> Dict[str, Any]:
    """Deterministic backup if the model call fails: entries + top fan-in nodes."""
    stops = []
    seen = set()
    for ep in doc.get("entryPoints", []):
        stops.append({"nodeId": ep, "reason": "A natural entry point into the system."})
        seen.add(ep)
    ranked = sorted(
        (n for n in doc["nodes"] if n["kind"] in ("module", "class", "function")),
        key=lambda n: n.get("fanIn", 0), reverse=True,
    )
    for n in ranked:
        if n["id"] not in seen and len(stops) < 10:
            stops.append({"nodeId": n["id"], "reason": "A heavily used part of the system."})
            seen.add(n["id"])
    return {"title": f"A tour of {doc.get('repo', {}).get('name', 'this codebase')}",
            "stops": stops}
