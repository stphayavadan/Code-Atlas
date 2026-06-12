"""Azure Foundry IQ-based code knowledge retrieval.

This module uses Azure Foundry chat to rank and select the most relevant code
nodes for a user question. The knowledge base is built from the parsed repo
graph and the model performs the retrieval step, so the whole stack uses
Azure Foundry rather than a local search heuristic.
"""
from __future__ import annotations

import json
from typing import Dict, Iterable, List

from .client import call_model, extract_text, MODEL_FAST

KB_SYSTEM = """You are a code retrieval engine for a parsed Python repository.
You receive a compact catalog of repo nodes and a user question. Your job is
to return the most relevant node ids, ordered by relevance. Do not invent
nodes, ids, or files. Use only the catalog provided."""


def _compact_node_entry(node: dict) -> str:
    hint = (node.get("docstring") or node.get("signature") or "").strip().replace("\n", " ")
    return (
        f"ID: {node['id']}\n"
        f"Kind: {node.get('kind','')}\n"
        f"File: {node.get('relPath','')}\n"
        f"Label: {node.get('label','')}\n"
        f"Hint: {hint[:220]}\n"
        "---"
    )


class FoundryCodeKnowledgeBase:
    def __init__(self, doc: dict, model: str = MODEL_FAST):
        self.nodes = [n for n in doc.get("nodes", []) if n.get("kind") != "package"]
        self.node_by_id = {n["id"]: n for n in self.nodes}
        self.model = model

    def _catalog(self) -> str:
        return "\n".join(_compact_node_entry(n) for n in self.nodes)

    def search(self, query: str, top_k: int = 6) -> List[dict]:
        if not self.nodes:
            return []

        prompt = (
            f"Repository nodes:\n{self._catalog()}\n\n"
            f"User query: {query}\n\n"
            "Return only a valid JSON object with keys:\n"
            "- ids: an ordered array of node ids from the catalog\n"
            "- reason: a single short sentence explaining the top choice.\n"
            "If fewer than {top_k} nodes are relevant, return only the relevant ids."
        )

        response = call_model(
            system=KB_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            model=self.model,
            max_tokens=512,
            temperature=0.0,
        )

        text = extract_text(response)
        try:
            payload = json.loads(text)
            ids = [str(i) for i in payload.get("ids", [])]
        except Exception:
            return self._fallback(query, top_k)

        results = [self.node_by_id[node_id] for node_id in ids if node_id in self.node_by_id]
        if len(results) < top_k:
            remaining = [n for n in self.nodes if n["id"] not in {r["id"] for r in results}]
            results.extend(remaining[: top_k - len(results)])
        return results[:top_k]

    def _fallback(self, query: str, top_k: int) -> List[dict]:
        return sorted(self.nodes, key=self._default_sort)[:top_k]

    @staticmethod
    def _default_sort(node: dict) -> float:
        return float(node.get("fanIn", 0)) + (1.0 if node.get("isEntry") else 0.0)


def format_candidates(nodes: Iterable[dict]) -> str:
    lines: List[str] = []
    for node in nodes:
        lines.append(f"ID: {node['id']}")
        lines.append(
            f"Kind: {node.get('kind','')} | File: {node.get('relPath','')} | "
            f"Signature: {node.get('signature','')}"
        )
        if node.get("docstring"):
            lines.append(f"Docstring: {node['docstring'][:220].replace('\n', ' ')}")
        source = node.get("source", "")
        if source:
            lines.append("Source excerpt:")
            lines.append(source.strip()[:750])
        lines.append("---")
    return "\n".join(lines)
