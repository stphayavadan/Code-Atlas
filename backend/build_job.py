"""Background build job: turn a repo URL into a fully pre-generated experience.

The whole point: do ALL the slow work UP FRONT (clone -> parse -> design tour ->
narrate the overview AND every node) so the dive itself never stalls waiting on
Azure Foundry. Per-node narration is generated in parallel (thread pool) and stored in
memory; the frontend polls progress and only enters the dive once everything is
ready.

A single active job at a time (one "active repository" model). Progress is
exposed as a dict the API serves verbatim.
"""
from __future__ import annotations

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

from pipeline import build_repo_document
from repo_clone import clone_repo, CloneResult
from llm.narrate import narrate_node, narrate_overview
from llm.tour import design_tour

# How many narration calls to run concurrently against Foundry.
NARRATION_CONCURRENCY = 6


class BuildJob:
    """Owns one repository's full lifecycle and its generated artifacts."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.status = "idle"          # idle|cloning|parsing|tour|narrating|ready|error
            self.message = ""
            self.error: Optional[str] = None
            self.done = 0
            self.total = 0
            self.doc: Optional[dict] = None
            self.by_id: Dict[str, dict] = {}
            self.overview: Optional[str] = None
            self.tour: Optional[dict] = None
            self.narration: Dict[str, str] = {}
            self._clone: Optional[CloneResult] = None

    # ---- progress snapshot for the API ----
    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            repo = self.doc["repo"] if self.doc else None
            stats = self.doc["stats"] if self.doc else None
            pct = int(100 * self.done / self.total) if self.total else (
                100 if self.status == "ready" else 0
            )
            return {
                "status": self.status,
                "message": self.message,
                "error": self.error,
                "done": self.done,
                "total": self.total,
                "percent": pct,
                "repo": repo,
                "stats": stats,
                "ready": self.status == "ready",
            }

    def _set(self, **kw: Any) -> None:
        with self._lock:
            for k, v in kw.items():
                setattr(self, k, v)

    # ---- the build, run in a background thread ----
    def start(self, url: str, pat: str, branch: Optional[str]) -> None:
        self.reset()
        t = threading.Thread(target=self._run, args=(url, pat, branch), daemon=True)
        t.start()

    def start_local(self, path: str, name: Optional[str]) -> None:
        """Build from an already-local path (no clone) — used for the demo repo."""
        self.reset()
        t = threading.Thread(target=self._run_local, args=(path, name), daemon=True)
        t.start()

    def _run(self, url: str, pat: str, branch: Optional[str]) -> None:
        try:
            self._set(status="cloning", message="Cloning repository…")
            clone = clone_repo(url, pat, branch)
            self._clone = clone
            self._build_from_path(clone.path, clone.name)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._set(status="error", error=str(e), message="Build failed.")

    def _run_local(self, path: str, name: Optional[str]) -> None:
        try:
            self._build_from_path(path, name)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._set(status="error", error=str(e), message="Build failed.")

    def _build_from_path(self, path: str, name: Optional[str]) -> None:
        # 1) Parse structure.
        self._set(status="parsing", message="Analyzing code structure…")
        doc = build_repo_document(path, name)
        with self._lock:
            self.doc = doc
            self.by_id = {n["id"]: n for n in doc["nodes"]}

        # 2) Design the dive tour.
        self._set(status="tour", message="Designing the guided dive…")
        tour = design_tour(doc)
        self._set(tour=tour)

        # 3) Pre-generate ALL narration: overview + every node, in parallel.
        nodes: List[dict] = doc["nodes"]
        # We narrate every real node so any Q&A target is also instant. Overview
        # counts as one unit too.
        with self._lock:
            self.total = len(nodes) + 1
            self.done = 0
            self.status = "narrating"
            self.message = "Generating explanations for every node…"

        # Overview first (it is the dive's opening line).
        try:
            ov = narrate_overview(doc)
        except Exception:
            ov = f"A guided dive through {doc['repo']['name']}."
        self._set(overview=ov)
        self._bump()

        # Every node, concurrently.
        def work(node: dict) -> tuple[str, str]:
            try:
                return node["id"], narrate_node(node, doc)
            except Exception:
                # Fall back to signature/docstring so the dive never has a blank.
                fallback = node.get("docstring") or node.get("signature") or node.get("label", "")
                return node["id"], fallback

        with ThreadPoolExecutor(max_workers=NARRATION_CONCURRENCY) as pool:
            futures = [pool.submit(work, n) for n in nodes]
            for fut in as_completed(futures):
                node_id, text = fut.result()
                with self._lock:
                    self.narration[node_id] = text
                self._bump()

        self._set(status="ready", message="Ready. Dive in.")

    def _bump(self) -> None:
        with self._lock:
            self.done += 1
            if self.total:
                self.message = f"Generating explanations… {self.done}/{self.total}"


# Module-level singleton (one active repo at a time).
JOB = BuildJob()
