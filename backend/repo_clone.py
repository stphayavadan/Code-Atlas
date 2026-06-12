"""Clone a (possibly private) Git repository using a Personal Access Token.

The PAT is injected into the clone URL only for the duration of the `git clone`
subprocess call; it is never written to disk, logged, or returned. We shallow
clone a single branch to keep it fast.

Supported URL forms:
  https://github.com/owner/repo
  https://github.com/owner/repo.git
  https://gitlab.com/group/repo
  (any https host that accepts  https://<token>@host/...  basic auth)
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, quote


@dataclass
class CloneResult:
    path: str          # local filesystem path of the working tree
    name: str          # repo name (last URL segment, no .git)
    branch: str        # branch that was checked out
    cleanup: object    # call .cleanup() to delete the temp dir


def _repo_name_from_url(url: str) -> str:
    tail = url.rstrip("/").split("/")[-1]
    return tail[:-4] if tail.endswith(".git") else tail


def _auth_url(url: str, pat: str) -> str:
    """Embed the PAT as basic-auth in an https URL.

    GitHub/GitLab/Azure all accept https://<token>@host/path. For GitHub a bare
    token as the username works; we url-encode it to be safe with special chars.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Only https repository URLs are supported.")
    # Strip any existing creds in the host component.
    host = parsed.netloc.split("@")[-1]
    token = quote(pat, safe="")
    path = parsed.path
    return f"https://{token}@{host}{path}"


def clone_repo(url: str, pat: str, branch: Optional[str] = None) -> CloneResult:
    """Shallow-clone `url` (single branch) using `pat`. Raises on failure.

    The token never touches disk: it lives only in the argv of the git process
    and the returned object carries no secret.
    """
    url = url.strip()
    if not url:
        raise ValueError("Repository URL is required.")
    name = _repo_name_from_url(url)
    auth_url = _auth_url(url, pat.strip()) if pat and pat.strip() else url

    tmp = tempfile.TemporaryDirectory(prefix="cba_repo_")
    dest = os.path.join(tmp.name, name)

    cmd = ["git", "clone", "--depth", "1", "--single-branch"]
    if branch and branch.strip():
        cmd += ["--branch", branch.strip()]
    cmd += [auth_url, dest]

    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"  # never hang waiting for credentials

    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=300)
    if proc.returncode != 0:
        tmp.cleanup()
        # Scrub the token out of any error text before surfacing it.
        msg = _scrub(proc.stderr or proc.stdout, pat)
        raise RuntimeError(f"git clone failed: {msg.strip()[:500]}")

    # Resolve the actually-checked-out branch.
    checked_out = branch or _current_branch(dest)
    return CloneResult(path=dest, name=name, branch=checked_out or "default", cleanup=tmp)


def _current_branch(repo_dir: str) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "-C", repo_dir, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=30,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def _scrub(text: str, secret: str) -> str:
    """Remove the PAT (raw or url-encoded) from any text we might surface."""
    if not text:
        return ""
    for needle in {secret, quote(secret, safe="")}:
        if needle:
            text = text.replace(needle, "***")
    # Also blunt any leftover https://...@ basic-auth fragments.
    return re.sub(r"https://[^@/\s]+@", "https://***@", text)
