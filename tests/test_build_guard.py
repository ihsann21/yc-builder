"""The builder agent's PreToolUse guard: keys, practice answers, dev/ and tests/ stay out of reach."""
import json

import pytest

from builder.build import BLOCKED, ROOT

ROOT_TEXT = str(ROOT)
ESCAPED = ROOT_TEXT.replace(" ", "\\ ")


def seen(command: str) -> str:
    """What the guard searches: the tool input as JSON."""
    return json.dumps({"command": command})


@pytest.mark.parametrize("command", [
    "cat env.sh",
    "printenv",
    "echo $FREYA_API_KEY",
    "cat dev/practice.py",
    "ls tests/",
    f'cat "{ROOT_TEXT}/dev/practice.py"',
    f"cat {ESCAPED}/tests/test_dates.py",
    f'cd "{ROOT_TEXT}/dev" && ls',
    f'cd "{ROOT_TEXT}/tests"',
    "cat build-the-builder-v3/build-the-builder/out/gen_brief_a.py",
    "python3 -c 'open(\"public-test-set.json\")'",
    "cat results/log.jsonl",
])
def test_blocked(command):
    assert BLOCKED.search(seen(command))


@pytest.mark.parametrize("command", [
    "python3 builder/work/brief-a/gen.py 2>/dev/null",
    f'cd "{ROOT_TEXT}" && python3 -m builder.save brief-a builder/work/brief-a/workflow.json a,b',
    f'cat "{ROOT_TEXT}/builder/work/brief-a/inputs/brief-a.md"',
    f"sed -n 1,40p {ESCAPED}/builder/lib/calc.py",
    "grep -n devices builder/lib/tools.py",
])
def test_allowed(command):
    assert not BLOCKED.search(seen(command))


def decide(tool_input: dict) -> str:
    """The guard's decision for one tool call: 'deny' or 'allow'."""
    import asyncio
    from builder.build import guard
    out = asyncio.run(guard({"tool_input": tool_input}, None, None))
    return out.get("hookSpecificOutput", {}).get("permissionDecision", "allow")


def test_guard_checks_commands_and_paths_not_written_content():
    assert decide({"command": "cat env.sh"}) == "deny"
    assert decide({"file_path": f"{ROOT_TEXT}/dev/practice.py"}) == "deny"
    assert decide({"pattern": "x", "path": "tests/"}) == "deny"
    prose = "The customer names the environment of the call; see results/ of the check. Use env vars? no."
    assert decide({"file_path": f"{ROOT_TEXT}/builder/work/s/notes.md", "content": prose}) == "allow"
    assert decide({"file_path": f"{ROOT_TEXT}/builder/work/s/gen.py", "old_string": "a", "new_string": prose}) == "allow"


def test_export_refuses_a_run_that_saved_nothing(tmp_path, monkeypatch):
    from builder import build
    state = tmp_path / ".freya-agents.json"
    state.write_text(json.dumps({"s": {"workflow_id": "w", "agent_id": "a", "version": 3}}))
    monkeypatch.setattr(build, "STATE_FILE", state)
    lines = []

    def trace(*parts):
        lines.append(" ".join(map(str, parts)))
    assert build.export("s", {"workflow_id": "w", "agent_id": "a", "version": 3}, trace) is False
    assert "saved no new version" in lines[-1]
    assert build.export("t", {}, trace) is False and "no workflow was saved" in lines[-1]
