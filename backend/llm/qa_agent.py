"""Q&A navigation agent: the signature feature.

A developer asks a question in plain language ("where is auth handled?",
"how does the video get transcribed?"). The model:
  1. picks the single best node on the map to answer it,
  2. selects the best nodeId so the frontend flies the camera there,
  3. writes a spoken-style answer grounded in that node and its neighbours.

We give the model a compact set of candidate nodes so it can resolve the
question to a real place on the map. The answer is grounded in the chosen node's
actual source and its context.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .client import call_model, extract_text, MODEL_FAST
from .kb import FoundryCodeKnowledgeBase, format_candidates
from .narrate import _neighbour_summary, _node_context_block

QA_SYSTEM = """You are the interactive guide of a cinematic codebase map. The user \
can ask anything about this codebase. You see a selection of candidate nodes \
(modules, classes, functions) with short hints and source excerpts. Choose the \
single node that best answers the user's question, then return a JSON object \
with nodeId, answer, and optional secondaryNodeIds. Use only the provided \
candidates and do not invent nodes or files."""


def _full_catalog(doc: dict) -> str:
    lines: List[str] = []
    entry_set = set(doc.get("entryPoints", []))
    nodes = sorted(doc["nodes"], key=lambda n: (n.get("level", 9),
                                                 n.get("package", ""),
                                                 n.get("label", "")))
    for n in nodes:
        if n["kind"] == "package":
            continue
        tag = " [ENTRY]" if n["id"] in entry_set else ""
        hint = (n.get("docstring") or n.get("signature") or "").strip().replace("\n", " ")[:90]
        loc = f' @ {n.get("relPath","")}' if n.get("relPath") else ""
        lines.append(f'{n["id"]}{tag} | {n["kind"]}{loc}'
                     + (f' | {hint}' if hint else ""))
    return "\n".join(lines)


def answer_question(
    question: str,
    doc: dict,
    history: Optional[List[Dict[str, str]]] = None,
    model: str = MODEL_FAST,
) -> Dict[str, Any]:
    """Answer a question and choose a node to navigate to."""
    valid_ids = {n["id"] for n in doc["nodes"]}
    repo = doc.get("repo", {})
    kb = FoundryCodeKnowledgeBase(doc)
    candidates = kb.search(question, top_k=6)

    messages: List[Dict[str, Any]] = []
    for turn in (history or [])[-6:]:
        messages.append({"role": turn["role"], "content": turn["content"]})

    prompt = (
        f"Codebase: {repo.get('name')} (Python).\n\n"
        f"Candidate nodes:\n{format_candidates(candidates)}\n\n"
        f"User question: {question}\n\n"
        f"Choose the single best node from the candidates, and answer in a spoken-style "
        f"way. Return only valid JSON with keys: nodeId, answer, secondaryNodeIds. "
        f"secondaryNodeIds may list up to 3 other relevant candidate node ids."
    )

    resp = call_model(
        system=QA_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        model=model,
        max_tokens=700,
        temperature=0.3,
    )

    text = extract_text(resp)
    try:
        data = json.loads(text)
    except Exception:
        # Fallback if model output isn't valid JSON.
        top = candidates[0] if candidates else None
        answer = (
            f"I think the best place is {top.get('fullLabel') if top else 'the codebase'}. "
            f"It is in {top.get('relPath')}" if top else ""
        )
        return {"nodeId": top["id"] if top else None, "answer": answer, "secondaryNodeIds": []}

    node_id = data.get("nodeId")
    if node_id not in valid_ids:
        node_id = None
    secondary = [s for s in data.get("secondaryNodeIds", []) if s in valid_ids]

    return {
        "nodeId": node_id,
        "answer": data.get("answer", ""),
        "secondaryNodeIds": secondary[:5],
    }
