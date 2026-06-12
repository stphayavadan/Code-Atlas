"""FastAPI backend for the Visual Codebase Tour.

Flow:
  1. Frontend home page POSTs a repo URL + PAT (+ optional branch) to /api/build.
  2. A background BuildJob clones, parses, designs the dive, and PRE-GENERATES
     the overview plus an explanation for EVERY node (in parallel).
  3. Frontend polls /api/build/status until ready (showing progress).
  4. The dive then serves graph/tour/overview/narration entirely from memory —
     no mid-dive model calls, so motion never stalls.

All Azure Foundry credentials and the repo PAT live server-side. The PAT is
used only for the clone subprocess and is never persisted or echoed back.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

from build_job import JOB
from llm.qa_agent import answer_question

app = FastAPI(title="Visual Codebase Tour", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Optional demo repo to auto-build on startup (skip by unsetting REPO_PATH).
DEFAULT_REPO = os.getenv("REPO_PATH", "")
DEFAULT_REPO_NAME = os.getenv("REPO_NAME", "")


@app.on_event("startup")
def _startup() -> None:
    if DEFAULT_REPO and os.path.isdir(DEFAULT_REPO):
        print(f"[startup] Auto-building local demo repo: {DEFAULT_REPO}")
        JOB.start_local(DEFAULT_REPO, DEFAULT_REPO_NAME or None)
    else:
        print("[startup] Idle. POST /api/build with a repo URL + PAT to begin.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _require_ready() -> None:
    if JOB.status != "ready" or JOB.doc is None:
        raise HTTPException(
            status_code=409,
            detail=f"Repository not ready (status: {JOB.status}). "
                   f"POST /api/build then poll /api/build/status.",
        )


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class BuildRequest(BaseModel):
    url: str
    pat: Optional[str] = ""
    branch: Optional[str] = None


class QARequest(BaseModel):
    question: str
    history: Optional[List[Dict[str, str]]] = None


# ---------------------------------------------------------------------------
# Build lifecycle
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "status": JOB.status, "ready": JOB.status == "ready"}


@app.post("/api/build")
def build(req: BuildRequest) -> dict:
    if not req.url.strip():
        raise HTTPException(status_code=400, detail="Repository URL is required.")
    if JOB.status in ("cloning", "parsing", "tour", "narrating"):
        raise HTTPException(status_code=409, detail="A build is already in progress.")
    JOB.start(req.url, req.pat or "", req.branch)
    return JOB.snapshot()


@app.get("/api/build/status")
def build_status() -> dict:
    return JOB.snapshot()


# ---------------------------------------------------------------------------
# Experience data (all served from the pre-generated in-memory cache)
# ---------------------------------------------------------------------------
@app.get("/api/graph")
def get_graph() -> dict:
    _require_ready()
    return JOB.doc


@app.get("/api/overview")
def get_overview() -> dict:
    _require_ready()
    return {"text": JOB.overview or ""}


@app.get("/api/tour")
def get_tour() -> dict:
    _require_ready()
    return JOB.tour or {"title": "", "stops": []}


@app.get("/api/narrate/{node_id:path}")
def get_narration(node_id: str) -> dict:
    _require_ready()
    if node_id not in JOB.by_id:
        raise HTTPException(status_code=404, detail=f"Unknown node: {node_id}")
    # Pre-generated; falls back gracefully if a node somehow missed generation.
    text = JOB.narration.get(node_id) or JOB.by_id[node_id].get("signature", "")
    return {"nodeId": node_id, "text": text}


@app.post("/api/ask")
def ask(req: QARequest) -> dict:
    _require_ready()
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Empty question.")
    result = answer_question(req.question, JOB.doc, history=req.history)
    # The chosen node's explanation is already pre-generated, so the dive to it
    # is instant; nothing further to do here.
    return result
