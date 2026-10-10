"""Decision-point test: replay a practice customer's turns over the chat API and print the agent's replies.

    python -m dev.replay <workflow_id> <case_id> "<turn 1>" "<turn 2>" ... [--n 5]

Each replay opens a fresh practice session for the case (its call variables), sends the turns one by one
to the published workflow (POST /api/v2/chat/message), prints every reply and ends the chat. Use it to
measure one decision of the agent in seconds, without a simulation. Dev only: it reads the test set.
Needs FREYA_API_KEY and FREYA_BANK_TEAM_KEY in the environment.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

KIT = pathlib.Path(__file__).resolve().parent.parent / "build-the-builder-v3" / "build-the-builder"
sys.path.insert(0, str(KIT))
sys.path.insert(0, str(KIT / "tools"))
import freya  # noqa: E402
from score import http  # noqa: E402

from builder.lib import embed  # noqa: E402


def initial_state(workflow_id: str, variables: dict) -> dict:
    """The call variables plus what the initial code node writes, run locally: the chat route skips that node."""
    wf = freya.api("GET", "/api/v2/workflow/" + workflow_id, workspaceId=freya.workspace_id())["workflow"]["workflow"]
    node = wf["nodes"][wf["initial_node"]]
    state = dict(variables)
    if node.get("node_type") == "code":
        code = node["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
        embed.run(code, state=state)
    return {k: v if isinstance(v, str) else json.dumps(v) for k, v in state.items()}


def replay(workflow_id: str, case_id: str, turns: list[str]) -> list[str]:
    """The agent's reply to each turn, in order."""
    variables = initial_state(workflow_id, http("/v1/practice/sessions", {"case": case_id})["variables"])
    replies, call_id = [], None
    for turn in turns:
        body = {"workflowId": workflow_id, "message": turn, "customerVariables": variables}
        if call_id:
            body["callId"] = call_id
        try:
            out = freya.api("POST", "/api/v2/chat/message", body)
        except RuntimeError as error:
            replies.append("[error] " + str(error)[:200])
            break
        call_id = out.get("callId") or call_id
        replies.append(str(out.get("response", "")))
    if call_id:
        try:
            freya.api("POST", "/api/v2/chat/end", {"callId": call_id})
        except RuntimeError:
            pass
    return replies


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workflow_id")
    parser.add_argument("case_id")
    parser.add_argument("turns", nargs="+")
    parser.add_argument("--n", type=int, default=1)
    args = parser.parse_args()
    for run in range(args.n):
        print(f"--- run {run + 1}")
        for turn, reply in zip(args.turns, replay(args.workflow_id, args.case_id, args.turns)):
            print("USER: ", turn)
            print("AGENT:", reply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
