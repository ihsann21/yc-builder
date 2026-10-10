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
