"""Check, validate and save a workflow:  python3 -m builder.save <slot> <workflow.json> <call,variables>

1. builder.lib.workflow.check: problems stop the save (warnings are printed).
2. A dry run on Freya (POST ?dryRun=true).
3. freya.save_workflow: create the first time, then update in place and publish; a workflow id that
   no longer exists on Freya is created again, and a new workflow is saved twice (see `save`).
4. Read the saved workflow back and compare nodes and tools with what was sent (the platform
   drops misplaced fields silently).
Prints the workflow and agent ids as the last line (JSON). Exit code 0 only when saved.
"""
from __future__ import annotations

import json
import pathlib
import sys

from builder.build import STATE_FILE, VENDOR
from builder.lib import workflow

sys.path.insert(0, str(VENDOR))
import freya  # noqa: E402  (the kit's client, copied to builder/vendor; standard library only)


def shape(wf: dict) -> dict:
    """Node -> tool names, plus the workflow-level tools: what a save must keep."""
    out = {key: sorted(t["function"]["name"] for t in node.get("tools", []) + node.get("pre_actions", []))
           for key, node in wf.get("nodes", {}).items()}
    out["(workflow tools)"] = sorted(t["function"]["name"] for t in wf.get("tools", []))
    return out


def save(slot: str, wf: dict) -> dict:
    """freya.save_workflow, plus two gaps it leaves: a slot whose workflow no longer exists on Freya (404)
    is created again, and a new workflow is saved once more, so that its agent gets the event's model
    (the update path sets it; a chat turn does not start without it)."""
    try:
        saved = freya.save_workflow(slot, wf, state_file=str(STATE_FILE))
    except RuntimeError as error:
        state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
        if slot not in state or " -> 404:" not in str(error):
            raise
        print("stale workflow id for", slot, "(not found on Freya): creating a new workflow")
        state.pop(slot)
        STATE_FILE.write_text(json.dumps(state, indent=1))
        saved = freya.save_workflow(slot, wf, state_file=str(STATE_FILE))
    if "version" not in saved:
        saved = freya.save_workflow(slot, wf, state_file=str(STATE_FILE))
    return saved


def main() -> int:
    slot, path, variables = sys.argv[1], pathlib.Path(sys.argv[2]), tuple(sys.argv[3].split(","))
    wf = json.loads(path.read_text(encoding="utf-8"))
    problems = workflow.check(wf, variables)
    for line in problems:
        print("check:", line)
    if [p for p in problems if not p.startswith("warning")]:
        print("NOT SAVED: fix the problems above")
        return 1
    try:
        freya.validate_workflow(slot + " (dry run)", wf)
        print("dry run: ok")
    except RuntimeError as error:
        print("dry run FAILED:", str(error)[:1500])
        return 1
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    saved = save(slot, wf)
    back = freya.api("GET", "/api/v2/workflow/" + saved["workflow_id"], workspaceId=freya.workspace_id())["workflow"]["workflow"]
    sent, kept = shape(wf), shape(back)
    for key in sent:
        if sent[key] != kept.get(key):
            print("READ-BACK DIFFERS at", key, "sent", sent[key], "stored", kept.get(key))
    print(json.dumps({"slot": slot, **saved}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
