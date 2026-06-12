"""File ingestion: walk a repository and collect parseable Python source files.

Scope is intentionally Python-only (see project plan). We skip the usual noise
(virtualenvs, caches, VCS, build artifacts) so the resulting map reflects the
*authored* code, not its dependencies.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

# Directories we never want to walk into. Keeps the map focused on real code.
SKIP_DIRS = {
    ".git", ".hg", ".svn",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "venv", ".venv", "env", ".env", "virtualenv",
    "node_modules", "dist", "build", ".eggs", "site-packages",
    ".idea", ".vscode", ".streamlit",
}


@dataclass
class SourceFile:
    """A single Python file discovered in the repository."""
    abs_path: str          # absolute path on disk
    rel_path: str          # path relative to repo root, using forward slashes
    module_path: str       # dotted module path, e.g. "services.MP4_Transcript_Service"
    package: str           # top-level package/dir, or "(root)" for repo-root files
    source: str            # full file contents
    line_count: int


def _to_module_path(rel_path: str) -> str:
    """Convert a relative file path to a dotted module path.

    "services/MP4_Transcript_Service.py" -> "services.MP4_Transcript_Service"
    "main.py"                             -> "main"
    "pkg/__init__.py"                     -> "pkg"
    """
    no_ext = rel_path[:-3] if rel_path.endswith(".py") else rel_path
    parts = [p for p in no_ext.split("/") if p]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else "(root)"


def _package_of(rel_path: str) -> str:
    """Return the top-level directory a file lives in, or '(root)'."""
    parts = rel_path.split("/")
    return parts[0] if len(parts) > 1 else "(root)"


def ingest_repository(root: str) -> List[SourceFile]:
    """Walk `root` and return every authored Python source file.

    Raises FileNotFoundError if the root does not exist.
    """
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        raise FileNotFoundError(f"Repository path is not a directory: {root}")

    files: List[SourceFile] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skip dirs in-place so os.walk does not descend into them.
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        for name in filenames:
            if not name.endswith(".py"):
                continue
            abs_path = os.path.join(dirpath, name)
            rel_path = os.path.relpath(abs_path, root).replace(os.sep, "/")
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    source = f.read()
            except (UnicodeDecodeError, OSError):
                # Skip unreadable/binary-ish files rather than failing the whole run.
                continue

            files.append(SourceFile(
                abs_path=abs_path,
                rel_path=rel_path,
                module_path=_to_module_path(rel_path),
                package=_package_of(rel_path),
                source=source,
                line_count=source.count("\n") + 1,
            ))

    files.sort(key=lambda f: f.rel_path)
    return files
