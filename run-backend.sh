#!/usr/bin/env bash
# Launch the FastAPI backend. Set REPO_PATH to point at any Python repo.
# Port 8077 (8000 is blocked by Windows socket permissions on this host).
cd "$(dirname "$0")/backend" || exit 1
export REPO_PATH="${REPO_PATH:-C:\\tmp\\ccgy_demo}"
export REPO_NAME="${REPO_NAME:-CCGY_Agentic_Framework}"
python -m uvicorn main:app --host 127.0.0.1 --port 8077 --reload
