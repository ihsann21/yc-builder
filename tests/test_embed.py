import json

import pytest

from builder.lib import embed


def test_literal_round_trips_and_has_no_braces():
    value = {"a": {"b": [1, 2.5, "x}}y", "{{z}}"]}, "q": "it's \"quoted\" \\ back", "n": None, "t": True}
    expr = embed.literal(value)
    assert "{" not in expr and "}" not in expr
    assert eval(expr, {"json": json}) == value


def test_literal_keeps_key_order():
    expr = embed.literal({"z": 1, "a": 2})
    assert list(eval(expr, {"json": json}).keys()) == ["z", "a"]


def test_source_drops_marked_lines():
    text = embed.source("common")
    assert "# embed: drop" not in text
    assert "def lookup(" in text


def test_snippet_checks_and_runs_code_entry():
    code = embed.snippet(("common",), "lookup", {"k": "v"}, "code", call="bb_state['out'] = lookup(CFG, 'k')")
    state = embed.run(code, state={})
    assert state["out"] == "v"


def test_check_flags_braces_imports_underscores_and_fstrings():
    assert any("double brace" in p for p in embed.check("x = 1  # {{y}}\n"))
    assert any("import" in p for p in embed.check("import os\n"))
    assert any("underscore" in p for p in embed.check("_x = 1\n"))
    assert any("f-string" in p for p in embed.check("x = 1\ny = f'a'\n"))
    assert any("compile" in p for p in embed.check("def (:\n"))
    assert embed.check("import json\nx = json.loads('[1]')\n") == []


def test_run_uses_restricted_builtins():
    code = "import json\nbb = vars\nbb['n'] = len([1, 2])\n"
    assert embed.run(code, state={})["n"] == 2
    with pytest.raises(NameError):
        embed.run("x = enumerate([1])\n", state={})
    with pytest.raises(ImportError):
        embed.run("import os\n", state={})


def test_snippet_never_raises_when_entry_fails():
    code = embed.snippet(("common",), "lookup", {}, "code", call="bb_state['a'] = 1 / 0")
    assert embed.run(code, state={}) == {}


def test_snippet_rejects_unknown_kind():
    with pytest.raises(ValueError):
        embed.snippet(("common",), "lookup", {}, "nope")
