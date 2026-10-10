"""Practice Brief A rebuilt with builder/lib: the kit builder's prompts, our plumbing.

The prompts, on_enter lines, extraction and tool descriptions are read from the kit builder's
known-good workflow (out/brief-a.workflow.json), so the only difference from it is the plumbing:
date and product code, hooks and the close hook come from builder/lib. Offline: nothing here calls
Freya. dev/ may hold practice-brief values (builder/ may not).

    python -m dev.practice_a [--out dev/out/practice-a.workflow.json]
"""
from __future__ import annotations

import argparse
import json
import pathlib

from builder.lib import calc, closing, hooks, tools
from builder.lib import workflow as wf
from dev.practice import (A_RULES, CALL_VARIABLES, KIT, KIT_A_BANDS, KIT_A_LINE, PRACTICE_CAL, PRACTICE_DATES,
                          PRACTICE_DEFAULT, PRACTICE_OUTCOMES, PRACTICE_SHAPE, PRACTICE_TYPES, PRACTICE_WINDOW,
                          PROMISE_POST, PROMISE_PRE, SIMPLE_WRITE_POST, VERIFY_POST, VERIFY_PRE, kit_workflow)

BAKE = {"customer_id": "{{customer_id}}"}


def kit_parts() -> tuple[dict, dict]:
    """(kit workflow, kit tools by name)."""
    kit = kit_workflow(KIT, "a")
    found = {t["function"]["name"]: t for t in kit.get("tools", [])}
    for node in kit["nodes"].values():
        found.update({t["function"]["name"]: t for t in node.get("tools", [])})
    return kit, found


def kit_notes(tool: dict, op: tools.Operation) -> dict[str, str]:
    """The kit's leaf descriptions, as notes for the fields the OpenAPI file leaves undescribed."""
    leaves = tool["function"]["parameters"]["properties"]["body"]["properties"]
    return {f.name: leaves[f.name]["description"] for f in op.request
            if f.name in leaves and leaves[f.name].get("description") and not f.description}


def build() -> dict:
    """The practice Brief A workflow, assembled from builder/lib parts."""
    ops, warnings = tools.operations(tools.load_api(KIT / "tools" / "openapi.json"))
    if warnings:
        raise ValueError("tool API warnings: " + "; ".join(warnings))
    kit, kit_tools = kit_parts()

    def tool(name: str, pre: str = "", post: str = "", **extra) -> dict:
        return tools.api_tool(ops[name], description=kit_tools[name]["function"]["description"], bake=BAKE,
                              notes=kit_notes(kit_tools[name], ops[name]), pre=pre, post=post, **extra)

    verify = tool("verify_identity", hooks.pre_hook("verify_identity", **VERIFY_PRE),
                  hooks.post_hook("verify_identity", **VERIFY_POST))
    callback = tool("schedule_callback",
                    hooks.pre_hook("schedule_callback", normalize={"date": {"kind": "date", "future": True},
                                                                   "time": {"kind": "time"}}),
                    hooks.post_hook("schedule_callback", **SIMPLE_WRITE_POST))
    transfer = tool("transfer_to_agent", hooks.pre_hook("transfer_to_agent"),
                    hooks.post_hook("transfer_to_agent", **SIMPLE_WRITE_POST))
    promise = tool("create_promise", hooks.pre_hook("create_promise", **PROMISE_PRE),
                   hooks.post_hook("create_promise", **PROMISE_POST))
    close = tool("close_call", closing.close_hook(outcome_field="outcome", reason_field="reason",
                                                  outcomes=PRACTICE_OUTCOMES, rules=A_RULES, default=PRACTICE_DEFAULT),
                 lifecycle="end_of_call")
    end = tools.end_call_tool(description=kit_tools["end_call"]["function"]["description"],
                              trigger_phrase="Have a good day.",
                              polite_replies=["goodbye", "bye", "have a good day", "you too", "thank you", "thanks", "take care"])
    lookup = tools.api_tool(ops["get_account"], description="Get the late product.", bake=BAKE, retries=2)

    dates = calc.dates_code(calendar=PRACTICE_CAL, dates=PRACTICE_DATES, windows=[PRACTICE_WINDOW],
                            weekday_mode="following_week", calendar_days=40)
    facts = calc.products_code(sources=calc.product_sources("load_account", "get_account", "products", "products"),
                               types=PRACTICE_TYPES, bands=KIT_A_BANDS, line=KIT_A_LINE,
                               known_dates=tuple(d["name"] for d in PRACTICE_DATES), **PRACTICE_SHAPE)
    k = kit["nodes"]
    verified = wf.any_of(wf.when_true("verify_identity_response.data.all_verified"), wf.when_equals("bb_identity", "verified"))
    nodes = {
        "setup": wf.code_node("setup", dates, "greet"),
        "greet": wf.conversation_node(
            "greet", task=k["greet"]["task_message"], tools=[callback, end], on_enter=k["greet"]["on_enter"],
            transitions=[wf.transition("identity", "The person clearly confirmed they are the customer",
                                       wf.when_equals("person", "customer"))],
            extraction=k["greet"]["extraction_schema"], max_turns=60),
        "identity": wf.conversation_node(
            "identity", task=k["identity"]["task_message"], tools=[verify, transfer, end], on_enter=k["identity"]["on_enter"],
            transitions=[wf.transition("load_account", "Both security answers verified", verified)], max_turns=60),
        "load_account": wf.api_request_node("load_account", lookup, "account_facts", mapping=[("data.products", "products")]),
        "account_facts": wf.code_node("account_facts", facts, "negotiate"),
        "negotiate": wf.conversation_node(
            "negotiate", task=k["negotiate"]["task_message"], tools=[promise, transfer, end],
            on_enter=k["negotiate"]["on_enter"], transitions=[], max_turns=80),
    }
    return wf.workflow(initial="setup", nodes=nodes, system_prompt=kit["system_prompt"], tools=[close],
                       test_variables=kit["test_variables"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", default=str(pathlib.Path(__file__).resolve().parent / "out" / "practice-a.workflow.json"))
    out = pathlib.Path(parser.parse_args().out)
    built = build()
    problems = wf.check(built, CALL_VARIABLES)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(built, indent=1), encoding="utf-8")
    print("wrote", out, "-", len(json.dumps(built)), "bytes,", len(built["nodes"]), "nodes")
    print("check:", problems or "no problems")


if __name__ == "__main__":
    main()
