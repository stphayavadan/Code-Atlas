"""AST extraction: turn Python source into structured symbols.

For each file we extract the things that matter for a *map*:
  - imports (so we can draw module->module dependency edges)
  - top-level and nested classes / functions (the "places" on the map)
  - the calls each function makes (so we can draw call edges)
  - line ranges + source slices (so the UI can show the actual code block)
  - docstrings + signatures (raw material for narration)

We use Python's native `ast` module: zero parsing edge cases for Python, and
it ships with the interpreter. Syntax errors in a file degrade gracefully to
a module node with no symbols rather than crashing the whole run.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .ingest import SourceFile


@dataclass
class Symbol:
    """A class, function, or method within a file."""
    id: str                       # globally unique: "<module>::<qualname>"
    name: str                     # short name, e.g. "transcribe_video_in_chunks"
    qualname: str                 # dotted within-module name, e.g. "Foo.method"
    kind: str                     # "class" | "function" | "method"
    module_path: str
    lineno: int
    end_lineno: int
    signature: str                # rendered def/class signature line
    docstring: Optional[str]
    source: str                   # the exact source slice for this symbol
    decorators: List[str] = field(default_factory=list)
    calls: List[str] = field(default_factory=list)   # raw callee names seen in body
    parent_id: Optional[str] = None                  # enclosing class symbol id
    complexity: int = 1                              # crude size/branch heuristic


@dataclass
class ModuleInfo:
    """Everything extracted from one source file."""
    module_path: str
    rel_path: str
    package: str
    line_count: int
    docstring: Optional[str]
    imports: List[str] = field(default_factory=list)        # dotted targets
    import_modules: List[str] = field(default_factory=list)  # normalized module roots
    symbols: List[Symbol] = field(default_factory=list)
    parse_error: Optional[str] = None
    source: str = ""


def _render_signature(node: ast.AST) -> str:
    """Best-effort one-line signature using ast.unparse, trimmed to the header."""
    try:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = ast.unparse(node.args)
            prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            return f"{prefix} {node.name}({args})"
        if isinstance(node, ast.ClassDef):
            bases = ", ".join(ast.unparse(b) for b in node.bases) if node.bases else ""
            return f"class {node.name}({bases})" if bases else f"class {node.name}"
    except Exception:
        pass
    return getattr(node, "name", "<symbol>")


def _decorator_names(node: ast.AST) -> List[str]:
    out: List[str] = []
    for dec in getattr(node, "decorator_list", []) or []:
        try:
            out.append(ast.unparse(dec))
        except Exception:
            out.append("<decorator>")
    return out


class _CallCollector(ast.NodeVisitor):
    """Collect the names of things called within a node's body."""
    def __init__(self) -> None:
        self.calls: List[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        name = self._callee_name(node.func)
        if name:
            self.calls.append(name)
        self.generic_visit(node)

    @staticmethod
    def _callee_name(func: ast.AST) -> Optional[str]:
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            # For "obj.method()" we keep the attribute tail; for "mod.func()" the tail too.
            return func.attr
        return None


def _complexity(node: ast.AST) -> int:
    """A cheap proxy for 'how much is going on here' to size nodes on the map."""
    score = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.For, ast.While, ast.Try,
                              ast.With, ast.AsyncFor, ast.AsyncWith,
                              ast.BoolOp, ast.comprehension)):
            score += 1
    return score


def _slice_source(source_lines: List[str], lineno: int, end_lineno: int) -> str:
    # ast line numbers are 1-based and inclusive.
    return "\n".join(source_lines[lineno - 1:end_lineno])


def parse_source_file(sf: SourceFile) -> ModuleInfo:
    """Parse one SourceFile into a ModuleInfo. Never raises on bad syntax."""
    info = ModuleInfo(
        module_path=sf.module_path,
        rel_path=sf.rel_path,
        package=sf.package,
        line_count=sf.line_count,
        docstring=None,
        source=sf.source,
    )

    try:
        tree = ast.parse(sf.source, filename=sf.rel_path)
    except SyntaxError as e:
        info.parse_error = f"SyntaxError: {e.msg} (line {e.lineno})"
        return info

    info.docstring = ast.get_docstring(tree)
    source_lines = sf.source.splitlines()

    # ---- imports ----
    import_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                info.imports.append(alias.name)
                import_modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod:
                info.imports.append(mod)
                import_modules.add(mod.split(".")[0])
    info.import_modules = sorted(import_modules)

    # ---- classes / functions / methods ----
    def handle(node: ast.AST, parent_qual: str, parent_id: Optional[str]) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            qualname = f"{parent_qual}.{node.name}" if parent_qual else node.name
            sym_id = f"{sf.module_path}::{qualname}"

            # Provisional kind; methods (functions directly inside a class) are
            # corrected in the second pass once all parents are known.
            kind = "class" if isinstance(node, ast.ClassDef) else "function"

            collector = _CallCollector()
            for child in node.body:
                collector.visit(child)

            sym = Symbol(
                id=sym_id,
                name=node.name,
                qualname=qualname,
                kind=kind,
                module_path=sf.module_path,
                lineno=node.lineno,
                end_lineno=getattr(node, "end_lineno", node.lineno),
                signature=_render_signature(node),
                docstring=ast.get_docstring(node) if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else None,
                source=_slice_source(source_lines, node.lineno,
                                     getattr(node, "end_lineno", node.lineno)),
                decorators=_decorator_names(node),
                calls=sorted(set(collector.calls)),
                parent_id=parent_id,
                complexity=_complexity(node),
            )
            info.symbols.append(sym)

            # Recurse into the body for nested defs/classes.
            for child in node.body:
                handle(child, qualname, sym_id)

    for node in tree.body:
        handle(node, "", None)

    # Second pass: fix method vs function classification now that we know parents.
    by_id = {s.id: s for s in info.symbols}
    for s in info.symbols:
        if s.parent_id and by_id.get(s.parent_id) and by_id[s.parent_id].kind == "class":
            if s.kind == "function":
                s.kind = "method"

    return info


def parse_all(files: List[SourceFile]) -> List[ModuleInfo]:
    return [parse_source_file(sf) for sf in files]
