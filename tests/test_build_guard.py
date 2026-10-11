"""The builder agent's PreToolUse guard: keys, practice answers, dev/ and tests/ stay out of reach."""
import json
import pathlib

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


def test_slot_is_the_brief_name_unless_that_name_was_built_from_other_inputs(tmp_path):
    from builder.build import slot_for
    slots = tmp_path / "work" / ".slot-inputs.json"
    api = tmp_path / "api.json"
    api.write_text("{}")
    (tmp_path / "clean").mkdir()
    (tmp_path / "raw").mkdir()
    clean, raw = tmp_path / "clean" / "brief (final).md", tmp_path / "raw" / "brief (final).md"
    clean.write_text("clean spec")
    raw.write_text("raw material")
    first = slot_for([str(clean)], str(api), slots)
    assert first == "brief__final_"
    assert slot_for([str(clean)], str(api), slots) == first              # same inputs: same slot, updated in place
    second = slot_for([str(raw)], str(api), slots)
    assert second.startswith("brief__final_-") and second != first       # same name, other inputs: own slot
    assert slot_for([str(raw)], str(api), slots) == second


def test_every_model_call_gets_a_purpose_line():
    from types import SimpleNamespace as NS
    from builder.build import call_purpose
    assert call_purpose([NS(text="Saving now.\nThen testing.")]) == "Saving now. Then testing."
    assert call_purpose([NS(name="Bash", input={"command": "x", "description": "Run generator"}),
                         NS(name="Read", input={"file_path": "/a/b.md"})]) == "tool call: Bash (Run generator); Read (/a/b.md)"
    assert call_purpose([]) == "(no text)"


def decide_tool(tool: str, tool_input: dict) -> str:
    import asyncio
    from builder.build import guard
    out = asyncio.run(guard({"tool_name": tool, "tool_input": tool_input}, None, None))
    return out.get("hookSpecificOutput", {}).get("permissionDecision", "allow")


@pytest.mark.parametrize("tool,tool_input", [
    ("Read", {"file_path": f"{ROOT_TEXT}/builder/work/brief-x/inputs/brief-x.md"}),
    ("Read", {"file_path": "builder/lib/calc.py"}),
    ("Read", {"file_path": f"{ROOT_TEXT}/builder/vendor/docs/api.md"}),
    ("Read", {"file_path": "builder/vendor/docs/workflow-format.md"}),
    ("Grep", {"pattern": "def products_code", "path": "builder/lib"}),
    ("Glob", {"pattern": "*.py", "path": f"{ROOT_TEXT}/builder/lib/runtime"}),
    ("Bash", {"command": f'cd "{ROOT_TEXT}" && python3 builder/work/brief-x/gen.py'}),
    ("Bash", {"command": "grep -rn shifts builder/lib"}),
])
def test_the_builder_can_still_do_its_work(tool, tool_input):
    assert decide_tool(tool, tool_input) == "allow"


@pytest.mark.parametrize("tool,tool_input", [
    ("Read", {"file_path": f"{ROOT_TEXT}/submission/brief-a.workflow.json"}),
    ("Read", {"file_path": f"{ROOT_TEXT}/PROGRESS.md"}),
    ("Read", {"file_path": f"{ROOT_TEXT}/brief-d.md"}),
    ("Read", {"file_path": f"{ROOT_TEXT}/build-the-builder-v3/build-the-builder/briefs/brief-a.md"}),
    ("Read", {"file_path": f"{ROOT_TEXT}/build-the-builder-v3/build-the-builder/examples/base-agent.json"}),
    ("Grep", {"pattern": "holiday"}),
    ("Grep", {"pattern": "holiday", "path": "."}),
    ("Glob", {"pattern": "**/*.workflow.json"}),
    ("Bash", {"command": "cat brief-d.md"}),
    ("Bash", {"command": f'cat "{ROOT_TEXT}/brief-d.md"'}),
    ("Bash", {"command": "cat PROGRESS.md"}),
    ("Bash", {"command": "cat submission/brief-a.workflow.json"}),
    ("Bash", {"command": "cd build-the-builder-v3/build-the-builder && cat out/gen_brief_a.py"}),
    ("Bash", {"command": "ls build-the-builder-v3/build-the-builder/briefs/"}),
    ("Bash", {"command": "grep -rn Reyes ."}),
    ("Bash", {"command": f'rg holiday "{ROOT_TEXT}"'}),
])
def test_the_builder_cannot_reach_other_briefs_or_practice_data(tool, tool_input):
    assert decide_tool(tool, tool_input) == "deny"


def test_a_clone_under_a_folder_named_like_a_blocked_one_still_works():
    import re
    from builder.build import GENERIC, unrooted
    root = "/tmp/out/results/environments/yc-builder"
    text = json.dumps({"file_path": root + "/builder/work/brief-a/gen.py"})
    assert GENERIC.search(text) and not GENERIC.search(unrooted(text, re.escape(root)))


@pytest.mark.parametrize("name", ["out", "results", "environment-rules", "brief-x", "dev"])
def test_a_brief_named_like_a_blocked_folder_gets_a_safe_slot(tmp_path, name):
    from builder.build import BLOCKED, ROOT, slot_for
    brief, api = tmp_path / (name + ".md"), tmp_path / "api.json"
    brief.write_text("x"), api.write_text("{}")
    slot = slot_for([str(brief)], str(api), tmp_path / "slots.json")
    from builder.build import blocked_name
    copy = (name + ".md") if not blocked_name(name + ".md") else "input-1.md"
    folder = ROOT / "builder" / "work" / slot / "inputs" / copy
    assert not BLOCKED.search(json.dumps({"file_path": str(folder)})), slot


def test_vendored_freya_client_and_docs_match_the_kit(kit):
    """builder/vendor is the kit's freya.py and docs/, copied unchanged: the builder runs without the kit."""
    vendor = ROOT / "builder" / "vendor"
    assert (vendor / "freya.py").read_bytes() == (kit / "freya.py").read_bytes()
    kit_docs = sorted(p.name for p in (kit / "docs").glob("*.md"))
    assert kit_docs and sorted(p.name for p in (vendor / "docs").glob("*.md")) == kit_docs
    for name in kit_docs:
        assert (vendor / "docs" / name).read_bytes() == (kit / "docs" / name).read_bytes(), name


def test_save_and_export_use_the_vendored_client():
    from builder import build, save
    assert build.VENDOR == ROOT / "builder" / "vendor"
    assert pathlib.Path(save.freya.__file__).resolve() == (build.VENDOR / "freya.py").resolve()


def test_case_folder_files_slot_and_prompt(tmp_path):
    """The final's form: a case folder of bank documents and the team's mock URL."""
    from builder.build import case_files, slot_for, task_prompt
    case = tmp_path / "FreyaBank-Case"
    (case / "docs").mkdir(parents=True)
    (case / "BRIEF.md").write_text("brief", encoding="utf-8")
    (case / "docs" / "contract.md").write_text("contract", encoding="utf-8")
    (case / ".DS_Store").write_text("x", encoding="utf-8")
    (case / "__MACOSX").mkdir()
    (case / "__MACOSX" / "junk").write_text("x", encoding="utf-8")
    files = case_files(case)
    assert [pathlib.Path(f).name for f in files] == ["BRIEF.md", "contract.md"]
    slots = tmp_path / "slots.json"
    slot = slot_for(files, "https://mock.example.workers.dev", slots_file=slots, name=case.name)
    assert slot == "FreyaBank-Case"
    assert slot_for(files, "https://other.example.workers.dev", slots_file=slots, name=case.name).startswith(
        "FreyaBank-Case-")
    prompt = task_prompt(files, "https://mock.example.workers.dev", slot, "", 25, str(case),
                         "https://mock.example.workers.dev")
    assert "BRIEF.md" in prompt and "https://mock.example.workers.dev" in prompt and "case folder" in prompt
