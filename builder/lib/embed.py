"""Assemble runtime code and a config into one snippet for a Freya code node or api_call hook.

A snippet is the source of the runtime modules it needs, then `CFG = <config>`, then one guarded
call of an entry function. The unit tests import the same runtime modules, so they exercise the
code that runs inside Freya. `run()` executes a snippet locally with only the builtins that
runtime code is allowed to use.
"""
from __future__ import annotations

import ast
import builtins
import functools
import json
import pathlib
import types

RUNTIME = pathlib.Path(__file__).resolve().parent / "runtime"
DROP_MARK = "# embed: drop"
PART_MARK = "# runtime module: "
ALLOWED_IMPORTS = ("json", "re", "datetime")
# Modules the allowed ones import internally (datetime.strftime imports time). Snippet code itself
# may not import them: check() enforces ALLOWED_IMPORTS statically.
INTERNAL_IMPORTS = ("time", "_strptime", "locale", "_locale", "calendar", "encodings")
# Freya's sandbox is not documented. These are the builtins the kit's working builder used in its
# snippets, plus a few of the same kind. check() and run() enforce the list.
ALLOWED_BUILTINS = (
    "Exception", "abs", "bool", "chr", "dict", "float", "int", "isinstance", "len", "list",
    "range", "round", "str", "tuple",
)
BUILTIN_NAMES = frozenset(dir(builtins))
SANDBOX_GLOBALS = ("vars", "config", "result")
ARGS = {"code": "bb_state, CFG", "pre": "bb_state, config, CFG", "post": "bb_state, result, CFG"}

TAIL = """
try:
    bb_state = vars if isinstance(vars, dict) else dict()
except Exception:
    bb_state = dict()
try:
    %s
except Exception:
    pass
"""


def literal(value: object) -> str:
    """A Python expression that evaluates to the JSON-able `value` and contains no curly brace.

    Braces are written as \\x7b and \\x7d escapes inside the string literal, so a nested config
    can never put a double brace into a snippet. Key order is kept.
    """
    text = repr(json.dumps(value, ensure_ascii=True))
    return "json.loads(" + text.replace("{", "\\x7b").replace("}", "\\x7d") + ")"


def source(name: str) -> str:
    """The text of runtime/<name>.py with the lines marked '# embed: drop' blanked.

    Blanking keeps the line numbers, so run() can compile each module under its real file name.
    """
    text = (RUNTIME / (name + ".py")).read_text(encoding="utf-8")
    kept = ["" if line.rstrip().endswith(DROP_MARK) else line for line in text.splitlines()]
    return "\n".join(kept) + "\n"


def snippet(modules: tuple[str, ...], entry: str, cfg: dict, kind: str, call: str | None = None) -> str:
    """Runtime modules + config + one guarded call. `kind` is 'code', 'pre' or 'post'.

    Only the definitions the call can reach are kept, and docstrings and comment lines are blanked,
    so a hook carries what it runs and not the whole library. Line numbers stay those of the files.
    `call` replaces the default `entry(<args of kind>)` call; tests use it.
    Raises ValueError if the result fails check().
    """
    if kind not in ARGS:
        raise ValueError("kind must be one of " + ", ".join(ARGS) + ", not " + repr(kind))
    call = call or entry + "(" + ARGS[kind] + ")"
    texts = [source(name) for name in modules]
    keep = reachable(texts, {n.id for n in ast.walk(ast.parse(call)) if isinstance(n, ast.Name)})
    parts = [PART_MARK + name + "\n" + compact(text, keep) for name, text in zip(modules, texts)]
    parts.append("CFG = " + literal(cfg))
    parts.append(TAIL % call)
    code = "\n".join(parts)
    problems = check(code)
    if problems:
        raise ValueError("snippet failed its checks: " + "; ".join(problems))
    return code


def top_level_names(node: ast.stmt) -> set[str]:
    """The names a top-level function definition or assignment binds."""
    if isinstance(node, ast.FunctionDef):
        return {node.name}
    if isinstance(node, ast.Assign):
        return {t.id for t in node.targets if isinstance(t, ast.Name)}
    return set()


def reachable(texts: list[str], roots: set[str]) -> set[str]:
    """Top-level names of the given module texts that `roots` use, directly or through each other."""
    defs: dict[str, ast.stmt] = {}
    for text in texts:
        for node in ast.parse(text).body:
            for name in top_level_names(node):
                defs[name] = node
    keep: set[str] = set()
    todo = list(roots)
    while todo:
        name = todo.pop()
        if name in keep or name not in defs:
            continue
        keep.add(name)
        todo.extend(n.id for n in ast.walk(defs[name]) if isinstance(n, ast.Name) and n.id in defs)
    return keep


def compact(text: str, keep: set[str]) -> str:
    """`text` with unused top-level definitions, docstrings and comment lines blanked (same line count)."""
    tree = ast.parse(text)
    blank: set[int] = set()
    for node in tree.body:
        names = top_level_names(node)
        if names and not names & keep:
            blank.update(range(node.lineno, node.end_lineno + 1))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.FunctionDef)) and body and len(body) > 1 and is_docstring(body[0]):
            blank.update(range(body[0].lineno, body[0].end_lineno + 1))
    lines = text.splitlines()
    kept = ["" if i + 1 in blank or line.lstrip().startswith("#") else line.rstrip() for i, line in enumerate(lines)]
    return "\n".join(kept) + "\n"


def is_docstring(node: ast.stmt) -> bool:
    """True for a bare string statement."""
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def check(code: str) -> list[str]:
    """Problems that would break a snippet inside Freya. Empty list = fine."""
    problems = []
    if "{{" in code or "}}" in code:
        problems.append("contains a double brace")
    try:
        tree = ast.parse(code)
    except SyntaxError as error:
        return problems + ["does not compile: " + str(error)]
    defined = defined_names(tree)
    for node in ast.walk(tree):
        problems.extend(node_problems(node, defined))
    return problems


def defined_names(tree: ast.AST) -> set[str]:
    """Every name the code binds itself: assignments, functions, parameters, imports, loop targets."""
    names = set(SANDBOX_GLOBALS)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, ast.FunctionDef):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.alias):
            names.add((node.asname or node.name).split(".")[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
    return names


def node_problems(node: ast.AST, defined: set[str]) -> list[str]:
    """Problems found on one AST node."""
    if isinstance(node, ast.Import):
        return ["import of " + a.name + " is not allowed" for a in node.names if a.name not in ALLOWED_IMPORTS]
    if isinstance(node, ast.ImportFrom):
        return [] if node.module in ALLOWED_IMPORTS and not node.level else ["import from " + str(node.module) + " is not allowed"]
    if isinstance(node, ast.JoinedStr):
        return ["f-string at line " + str(node.lineno)]
    if isinstance(node, (ast.ClassDef, ast.Lambda, ast.Global, ast.Nonlocal, ast.Yield, ast.With)):
        return [type(node).__name__ + " is not allowed (line " + str(getattr(node, "lineno", "?")) + ")"]
    name = bound_or_used_name(node)
    if name.startswith("_"):
        return ["name starting with an underscore: " + name]
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
        if node.id in BUILTIN_NAMES and node.id not in defined and node.id not in ALLOWED_BUILTINS:
            return ["builtin " + node.id + " is not in the allowed list"]
    return []


def bound_or_used_name(node: ast.AST) -> str:
    """The identifier a node carries, or ''."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.FunctionDef):
        return node.name
    if isinstance(node, ast.arg):
        return node.arg
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002 - mirrors __import__
    """__import__ that allows only the modules runtime code may use (and their internal imports)."""
    if level or name.split(".")[0] not in ALLOWED_IMPORTS + INTERNAL_IMPORTS:
        raise ImportError("import of " + name + " is not allowed in runtime code")
    return builtins.__import__(name, globals, locals, fromlist, level)


def run(code: str, state: dict | None = None, request: dict | None = None, result: dict | None = None,
        strict: bool = True) -> dict:
    """Execute a snippet the way Freya does. Returns the variable table.

    `state` is the variable table (`vars`), `request` the substituted request of a pre-hook
    (`config`), `result` the tool result of a post-hook. All are changed in place.
    strict=True allows only ALLOWED_BUILTINS and ALLOWED_IMPORTS; strict=False runs with the full
    builtins (for code we did not write, such as the kit's snippets).
    """
    if strict:
        allowed = {name: getattr(builtins, name) for name in ALLOWED_BUILTINS}
        allowed["__import__"] = guarded_import
    else:
        allowed = builtins.__dict__
    table = {} if state is None else state
    env = {"__builtins__": allowed, "vars": table, "config": request, "result": result}
    for part in compiled(code):
        exec(part, env)  # noqa: S102 - local harness for snippets we assembled or read from the kit
    return table


@functools.lru_cache(maxsize=64)
def compiled(code: str) -> tuple[types.CodeType, ...]:
    """The snippet compiled in parts, each runtime module under its real file name.

    Executing the parts one after another in one namespace is the same as executing the whole
    text; the file names make tracebacks and coverage point at runtime/*.py. Cached: tests run the
    same snippet thousands of times.
    """
    pieces = code.split(PART_MARK)
    parts = [compile(pieces[0], "<snippet>", "exec")] if pieces[0].strip() else []
    for piece in pieces[1:]:
        name, _, rest = piece.partition("\n")
        path = RUNTIME / (name + ".py")
        if not path.exists():
            parts.append(compile(rest, "<snippet>", "exec"))
            continue
        count = len(path.read_text(encoding="utf-8").splitlines())   # compact() keeps the line count
        lines = rest.split("\n")
        parts.append(compile("\n".join(lines[:count]) + "\n", str(path), "exec"))
        if "\n".join(lines[count:]).strip():
            parts.append(compile("\n".join(lines[count:]), "<snippet>", "exec"))
    return tuple(parts)
