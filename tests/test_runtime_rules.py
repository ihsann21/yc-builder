"""The rules in builder/lib/runtime/__init__.py, checked on every runtime module."""
import ast

import pytest

from builder.lib import embed

MODULES = sorted(p.stem for p in embed.RUNTIME.glob("*.py") if p.stem != "__init__")
TOP_LEVEL = (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.Assign)


def test_all_runtime_modules_are_listed():
    assert MODULES == ["closing", "common", "dates", "hooks", "products", "wrap"]


@pytest.mark.parametrize("name", MODULES)
def test_module_passes_the_snippet_check(name):
    assert embed.check(embed.source(name)) == []


@pytest.mark.parametrize("name", MODULES)
def test_raw_module_has_no_double_braces_and_drops_only_sibling_imports(name):
    text = (embed.RUNTIME / (name + ".py")).read_text(encoding="utf-8")
    assert "{{" not in text and "}}" not in text
    dropped = "\n".join(line for line in text.splitlines() if line.rstrip().endswith(embed.DROP_MARK))
    for node in ast.parse(dropped).body:
        assert isinstance(node, ast.ImportFrom) and node.module.startswith("builder.lib.runtime."), ast.dump(node)


@pytest.mark.parametrize("name", MODULES)
def test_top_level_holds_only_imports_constants_and_functions(name):
    tree = ast.parse(embed.source(name))
    body = tree.body[1:] if isinstance(tree.body[0], ast.Expr) else tree.body   # module docstring
    for node in body:
        assert isinstance(node, TOP_LEVEL), (name, type(node).__name__, node.lineno)


def test_no_top_level_name_is_defined_twice_across_modules():
    seen = {}
    for name in MODULES:
        for node in ast.parse(embed.source(name)).body:
            targets = [node.name] if isinstance(node, ast.FunctionDef) else \
                      [t.id for t in node.targets if isinstance(t, ast.Name)] if isinstance(node, ast.Assign) else []
            for target in targets:
                assert target not in seen, (target, seen.get(target), name)
                seen[target] = name


@pytest.mark.parametrize("modules", [("common", "dates"), ("common", "products"), ("common", "dates", "hooks"),
                                     ("common", "hooks"), ("common", "closing")])
def test_each_snippet_combination_assembles(modules):
    code = embed.snippet(modules, "noop", {}, "code", call="pass")
    assert embed.run(code, state={}) == {}
