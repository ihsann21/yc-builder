"""The builder:  python3 builder/build.py <brief.md> [<more briefs>] <tool_api.json> [--cases A]

Runs Claude through the Claude Agent SDK with our skill (builder/skill/SKILL.md). The agent reads the
brief and the tool API file, writes a generator that assembles the workflow from builder/lib parts,
checks and saves it on Freya (builder/save.py) and tests what it can. This script times the run,
writes the trace (start and end time, every model call, what was created, the tests) with secrets
masked, and exports the saved workflow to submission/<slot>.workflow.json.

--cases A|B runs the kit's practice customers as the agent's test (development only; hidden briefs
have no practice customers). Needs FREYA_API_KEY (and FREYA_BANK_TEAM_KEY for --cases) and a Claude
login or ANTHROPIC_API_KEY. BUILD_DEADLINE_S (default 1500) caps the run.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import pathlib
import re
import shutil
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
KIT = ROOT / "build-the-builder-v3" / "build-the-builder"
SKILL = ROOT / "builder" / "skill" / "SKILL.md"
WORK = ROOT / "builder" / "work"
STATE_FILE = WORK / ".freya-agents.json"
SLOTS_FILE = WORK / ".slot-inputs.json"      # slot -> hash of the inputs it was built from
SECRET_VARS = ("FREYA_API_KEY", "FREYA_BANK_TEAM_KEY", "ANTHROPIC_API_KEY")
# Any tool call whose input mentions one of these is refused: the agent never reads keys, and never
# reads practice answers or practice-brief configs (dev/, tests/, the kit builder's out/, the test set).
BLOCKED = re.compile(r"env\.sh|printenv|environ|declare -x|export -p|(^|[\s;&|(])env(\s|$)|"
                     + "|".join(SECRET_VARS)
                     + r"|(^|[\s'\"=]|yc-builder[\\/]+)(dev|tests)[\\/]|build-the-builder[\\/]+out[\\/]"
                     + r"|public-test-set|(^|[\s'\"\\/])(results|traces)[\\/]"
                     # dev/ and tests/ by absolute path too; a space in the repo path may be written as "\ "
                     + "|" + re.escape(str(ROOT)).replace(re.escape(" "), r"(?:\\+ | )")
                     + r"[\\/]+(dev|tests)([\\/\"'\s]|$)")


class Trace:
    """Plain-text trace on stdout and in traces/<slot>-<time>.log; secret values are masked."""

    def __init__(self, slot: str) -> None:
        self.path = ROOT / "traces" / (slot + "-" + time.strftime("%Y%m%d-%H%M%S") + ".log")
        self.path.parent.mkdir(exist_ok=True)
        self.secrets = [os.environ[k] for k in SECRET_VARS if len(os.environ.get(k, "")) >= 8]

    def __call__(self, *parts: object) -> None:
        """Write one line. Never raises: a trace problem must not stop the build."""
        try:
            line = " ".join(str(p) for p in parts)
            for secret in self.secrets:
                line = line.replace(secret, "***")
            line = re.sub(r"fak_[A-Za-z0-9_\-]{6,}", "fak_***", line)
            with self.path.open("a", encoding="utf-8") as out:
                out.write(line + "\n")
            print(line, flush=True)
        except Exception as error:  # noqa: BLE001 - the tracer reports its own failure and goes on
            print("[trace error]", type(error).__name__, file=sys.stderr, flush=True)


TESTS = re.compile(r"builder\.save|run_cases|gen\.py")


def result_text(content: object) -> str:
    """The text of a tool result (a string or a list of content blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return ""


def existing(path: str) -> str:
    """The absolute path of an input file, relative to the working folder or to the repo root."""
    for candidate in (pathlib.Path(path), ROOT / path):
        if candidate.resolve().is_file():
            return str(candidate.resolve())
    raise SystemExit("input file not found: " + path)


GUARDED_FIELDS = ("command", "file_path", "path", "pattern", "glob", "notebook_path")


async def guard(hook_input: dict, tool_use_id: str | None, context: object) -> dict:
    """PreToolUse hook: refuse any tool call whose command or path touches keys, env.sh or practice answers.

    Only commands, paths and search patterns are checked, never the content of a file being written:
    ordinary prose ("environment", "results/") in a generator or notes must not be refused."""
    tool_input = hook_input.get("tool_input", {})
    fields = {k: v for k, v in tool_input.items() if k in GUARDED_FIELDS} if isinstance(tool_input, dict) else tool_input
    found = BLOCKED.search(json.dumps(fields))
    if found:
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                       "permissionDecisionReason": "Off limits for the builder (matched "
                                       + repr(found.group(0).strip()) + "): keys, env.sh, dev/, tests/, "
                                       "practice answers and results."}}
    return {}


def task_prompt(briefs: list[str], api: str, slot: str, cases: str, minutes: int) -> str:
    """The first user message of the agent."""
    test = (f"Practice customers exist for this brief: test with `python3 {KIT / 'tools' / 'run_cases.py'} "
            f"<agent_id> --brief {cases}` (run it from {KIT}).") if cases else \
        "There are no practice customers for this brief: test with the local checks the skill describes."
    return (f"Build the phone agent for the brief file(s) {', '.join(briefs)} with the tool API file {api}.\n"
            f"Slot: {slot}. Work folder: {WORK / slot}. You have {minutes} minutes in total: save a first "
            f"complete version early, then improve it.\n{test}\nFollow the skill in your system prompt.")


async def run_agent(briefs: list[str], api: str, slot: str, cases: str, deadline: int, trace: Trace) -> None:
    """Run the agent; print every model call and tool use to the trace."""
    from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, HookMatcher, ResultMessage,
                                  ToolResultBlock, ToolUseBlock, UserMessage, query)
    model = os.environ.get("BUILDER_MODEL", "claude-opus-5-5")
    options = ClaudeAgentOptions(
        cwd=str(ROOT), model=model, setting_sources=[],
        system_prompt={"type": "preset", "preset": "claude_code", "append": SKILL.read_text(encoding="utf-8")},
        allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"], permission_mode="dontAsk", max_turns=150,
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[guard])]},
        env={"BASH_DEFAULT_TIMEOUT_MS": "900000", "BASH_MAX_TIMEOUT_MS": "1200000",
             "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1", "PYTHONPATH": str(ROOT)},
    )
    prompt = task_prompt(briefs, api, slot, cases, deadline // 60)
    watched = {}   # tool_use_id -> command, for the checks and tests whose output belongs in the trace
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            trace("[model call]", (getattr(message, "model", "") or model) + ":", call_purpose(message.content))
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    trace("  [tool]", block.name, str(block.input)[:200].replace("\n", " "))
                    command = str(block.input.get("command", "")) if isinstance(block.input, dict) else ""
                    if TESTS.search(command):
                        watched[block.id] = command
        elif isinstance(message, UserMessage) and isinstance(message.content, list):
            for block in message.content:
                if isinstance(block, ToolResultBlock) and block.tool_use_id in watched:
                    for line in result_text(block.content).strip().splitlines()[-25:]:
                        trace("  [test output]", line[:240])
        elif isinstance(message, ResultMessage):
            trace(f"[agent done] turns={message.num_turns} cost=${message.total_cost_usd or 0:.2f} "
                  f"duration={message.duration_ms / 1000:.0f}s result={message.subtype}"
                  + (" ERROR " + str(getattr(message, "errors", "") or "")[:200] if message.is_error else ""))
            for name, use in (getattr(message, "model_usage", None) or {}).items():
                trace("[model usage]", name, json.dumps(use)[:200])


def call_purpose(content: list) -> str:
    """One line on what a model call did: its text, else the tools it called and why."""
    texts = [b.text.strip() for b in content if hasattr(b, "text") and str(getattr(b, "text", "")).strip()]
    if texts:
        return " ".join(texts).replace("\n", " ")[:300]
    tools = []
    for block in content:
        if hasattr(block, "name") and isinstance(getattr(block, "input", None), dict):
            why = block.input.get("description") or block.input.get("file_path") or block.input.get("pattern") or ""
            tools.append(block.name + (" (" + str(why)[:120] + ")" if why else ""))
    return ("tool call: " + "; ".join(tools)) if tools else "(no text)"


def saved_entry(slot: str) -> dict:
    """The slot's entry in the state file ({workflow_id, agent_id, version}), or {}."""
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8")).get(slot, {})
    except (OSError, ValueError):
        return {}


def export(slot: str, before: dict, trace: Trace) -> bool:
    """Export the slot's saved workflow to submission/<slot>.workflow.json and trace what it holds.

    Only a workflow this run saved is exported: if the state entry did not change, the run saved
    nothing and the file of an earlier run must not pass for this run's agent."""
    saved = saved_entry(slot)
    if not saved:
        trace("[export] FAILED: no workflow was saved for slot", slot)
        return False
    if saved == before:
        trace("[export] FAILED: this run saved no new version (still", saved.get("workflow_id"),
              "version", str(saved.get("version")) + "); nothing exported")
        return False
    sys.path.insert(0, str(KIT))
    import freya
    out = ROOT / "submission" / (slot + ".workflow.json")
    out.parent.mkdir(exist_ok=True)
    freya.export_workflow(saved["workflow_id"], str(out))
    wf = json.loads(out.read_text(encoding="utf-8"))["workflow"]
    tools = sum(len(n.get("tools", [])) for n in wf.get("nodes", {}).values()) + len(wf.get("tools", []))
    trace(f"[created] workflow_id={saved['workflow_id']} agent_id={saved['agent_id']} "
          f"version={saved.get('version', 1)} nodes={len(wf.get('nodes', {}))} tools={tools}")
    trace("[export] wrote", out.relative_to(ROOT))
    return True


def slot_for(briefs: list[str], api: str, slots_file: pathlib.Path = SLOTS_FILE) -> str:
    """The slot: the last brief's file name, made safe. A name already used for other inputs (two hidden
    briefs both called brief.md) gets a short hash of the inputs, so one build never overwrites the other."""
    digest = hashlib.sha256(b"".join(pathlib.Path(f).read_bytes() for f in briefs + [api])).hexdigest()[:6]
    slot = re.sub(r"[^A-Za-z0-9_-]", "_", pathlib.Path(briefs[-1]).stem) or "brief"
    try:
        known = json.loads(slots_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        known = {}
    if known.get(slot, digest) != digest:
        slot = slot + "-" + digest
    known[slot] = digest
    slots_file.parent.mkdir(parents=True, exist_ok=True)
    slots_file.write_text(json.dumps(known, indent=1), encoding="utf-8")
    return slot


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a Freya phone agent from a brief.")
    parser.add_argument("files", nargs="+", help="brief file(s), then the tool API file")
    parser.add_argument("--cases", choices=["A", "B"], default="", help="practice customers to test with (dev only)")
    args = parser.parse_args()
    if len(args.files) < 2:
        parser.error("give at least one brief and the tool API file")
    for stream in (sys.stdout, sys.stderr):    # agent text holds characters a Windows console cannot show
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    briefs = [existing(f) for f in args.files[:-1]]
    api = existing(args.files[-1])
    slot = slot_for(briefs, api)
    deadline = int(os.environ.get("BUILD_DEADLINE_S", "1500"))
    trace = Trace(slot)
    start = time.time()
    trace("[start]", time.strftime("%Y-%m-%d %H:%M:%S"), "briefs:", briefs, "tool API:", api, "slot:", slot)
    # every run starts with no work folders at all, as on a fresh clone: this slot's old one and every other
    # slot's (an agent copied another brief's generator) go where the agent cannot read; the state file stays
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for folder in sorted(WORK.iterdir()) if WORK.exists() else []:
        if folder.is_dir():
            archive = ROOT / "dev" / "out" / "work-archive" / (folder.name + "-" + stamp)
            archive.parent.mkdir(parents=True, exist_ok=True)
            folder.rename(archive)
            trace("[work] work folder moved to", archive.relative_to(ROOT))
    (WORK / slot).mkdir(parents=True, exist_ok=True)
    # the agent works on copies in its work folder, so an input kept anywhere (even under dev/) stays readable
    inputs = WORK / slot / "inputs"
    inputs.mkdir()
    for source in briefs + [api]:
        shutil.copyfile(source, inputs / pathlib.Path(source).name)
    briefs = [str(inputs / pathlib.Path(b).name) for b in briefs]
    api = str(inputs / pathlib.Path(api).name)
    trace("[inputs] copied to", inputs.relative_to(ROOT))
    before = saved_entry(slot)
    try:
        asyncio.run(asyncio.wait_for(run_agent(briefs, api, slot, args.cases, deadline, trace), timeout=deadline))
    except asyncio.TimeoutError:
        trace(f"[deadline] stopped the agent after {deadline} s; exporting what was saved")
    except Exception as error:  # the agent failed: still export whatever it saved
        trace("[agent error]", type(error).__name__, str(error)[:300])
    ok = False
    try:
        ok = export(slot, before, trace)
    except Exception as error:  # noqa: BLE001 - the trace must still get its end line
        trace("[export] FAILED:", type(error).__name__, str(error)[:300])
    finally:
        trace("[end]", time.strftime("%Y-%m-%d %H:%M:%S"), f"build time {time.time() - start:.0f} s")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
