"""Q&A navigation agent: the signature feature.

A developer asks a question in plain language ("where is auth handled?",
"how does the video get transcribed?"). Claude:
  1. picks the single best node on the map to answer it,
  2. calls navigate_to(nodeId, reason) so the frontend flies the camera there,
  3. writes a spoken-style answer grounded in that node and its neighbours.

We give Claude a compact catalog of every node (id + name + one-line hint) so it
can resolve the question to a real place on the map. The answer is grounded in
the chosen node's actual source, fetched after the navigation choice.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .client import call_claude, extract_text, extract_tool_use, MODEL_FAST
from .narrate import _neighbour_summary, _node_context_block

NAVIGATE_TOOL = {
    "name": "navigate_to",
    "description": "Move the map camera to the node that best answers the user's "
                   "question, then explain it. Always call this exactly once.",
    "input_schema": {
        "type": "object",
        "properties": {
            "nodeId": {
                "type": "string",
                "description": "Exact id of the node to fly to. MUST be one from the catalog.",
            },
            "answer": {
                "type": "string",
                "description": "A spoken-style answer to the user's question, grounded in "
                               "this node and how it connects to the rest of the system. "
                               "2 to 5 sentences, no markdown, no code fences.",
            },
            "secondaryNodeIds": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional: other relevant node ids to softly highlight.",
            },
        },
        "required": ["nodeId", "answer"],
    },
}

QA_SYSTEM = """You are the interactive guide of a cinematic codebase map. The user \
can ask anything about this codebase. You see a catalog of every place on the map \
(modules, classes, functions) with short hints. For each question:
- Decide which SINGLE node best answers it — that is where the camera will fly.
- Call navigate_to with that node's exact id and a clear, spoken-style answer.
- Ground your answer in real structure: name the file, what it does, and what it \
connects to. Be warm and concise. If the question is broad, pick the best \
starting point and say why. Never invent code that is not in this codebase."""


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
    """Answer a question and choose a node to navigate to.

    Returns {"nodeId", "answer", "secondaryNodeIds": [...]} — or a graceful
    fallback if the model does not call the tool.
    """
    catalog = _full_catalog(doc)
    valid_ids = {n["id"] for n in doc["nodes"]}
    repo = doc.get("repo", {})

    messages: List[Dict[str, Any]] = []
    for turn in (history or [])[-6:]:
        messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({
        "role": "user",
        "content": (
            f"Codebase: {repo.get('name')} (Python).\n\n"
            f"Map node catalog (use exact ids):\n{catalog}\n\n"
            f"User question: {question}\n\n"
            f"Choose the best node and call navigate_to."
        ),
    })

    resp = call_claude(
        system=QA_SYSTEM,
        messages=messages,
        model=model,
        max_tokens=700,
        temperature=0.3,
        tools=[NAVIGATE_TOOL],
        tool_choice={"type": "tool", "name": "navigate_to"},
    )

    block = extract_tool_use(resp, "navigate_to")
    if not block:
        text = extract_text(resp) or "I couldn't pinpoint that on the map."
        return {"nodeId": None, "answer": text, "secondaryNodeIds": []}

    data = block.get("input", {})
    node_id = data.get("nodeId")
    if node_id not in valid_ids:
        node_id = None  # hallucinated id -> no navigation, keep the answer
    secondary = [s for s in data.get("secondaryNodeIds", []) if s in valid_ids]

    return {
        "nodeId": node_id,
        "answer": data.get("answer", ""),
        "secondaryNodeIds": secondary[:5],
    }
