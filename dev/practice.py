"""Practice Brief A/B values, written as builder/lib configs, and helpers to read the kit's workflows.

These values come from the practice briefs and the kit builder's hand-written workflows. They live in
dev/ and tests/ only; builder/ never sees them (tests/test_no_brief_values.py checks that). They let
us compare our runtime with the kit's snippets and rebuild the kit's agents with our plumbing.
"""
import json
import pathlib

from builder.lib import embed

ROOT = pathlib.Path(__file__).resolve().parent.parent
KIT = ROOT / "build-the-builder-v3" / "build-the-builder"
CALL_VARIABLES = ("customer_id", "first_name", "last_name", "title", "now")

# --- dates (brief A section 7, rules 6, 22, 30) ---------------------------------------------------
PRACTICE_CAL = {"workdays": [0, 1, 2, 3, 4],
                "holidays": ["2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"]}
PRACTICE_DATES = [
    {"name": "deadline_early", "rule": "business_days_after", "n": 12},
    {"name": "deadline_late", "rule": "business_days_after", "n": 7},
    {"name": "attempt1", "rule": "last_business_day_of_week", "after_today": True},
]
PRACTICE_WINDOW = {"name": "callback", "days": [{"rule": "today"}, {"rule": "next_business_day"}],
                   "from": "10:00", "to": "19:00", "after_now": True, "var": "callback_facts",
                   "label": "A callback can be booked only for these days and times"}

# --- products (brief A rules 17, 18, 25, 30; brief B rules 1-6) -----------------------------------
PRACTICE_SHAPE = dict(list_field="products", id_field="product_id", type_field="type", amount_field="past_due",
                      days_field="days_late", item_fields=["product_id", "type", "card_last4", "past_due",
                                                           "days_late", "minimum_payment", "instalment_amount"])
PRACTICE_TYPES = {
    "credit_card": {"name": "credit card ending {field:card_last4}", "floor_field": "minimum_payment",
                    "floor_label": "minimum payment"},
    "personal_loan": {"name": "personal loan", "floor_field": "instalment_amount", "floor_label": "instalment amount"},
    "car_loan": {"name": "car loan", "floor_field": "instalment_amount", "floor_label": "instalment amount"},
}
A1 = "{date_spoken:attempt1} ({date:attempt1})"
KIT_A_LINE = ("PRODUCT: {name} (product_id {id}). Say it exactly as \"{name}\".\n"
              "PAST-DUE AMOUNT (full amount): {full}. DAYS LATE: {days}.\n"
              "FLOOR ({floor_label}): {floor}. Never propose or accept less than the floor.\n"
              "BAND: {band}. DEADLINE (latest promise date): {deadline_spoken} ({deadline}). PERSUASION ATTEMPTS ALLOWED: {attempts}.\n"
              "ATTEMPT 1 OFFER: {full} on " + A1 + ". If the customer already said the full amount is too much, "
              "attempt 1 is the floor {floor} on " + A1 + " instead.\n{offers}")
KIT_A_BANDS = [
    {"name": "early", "min": 1, "max": 7, "deadline": "deadline_early", "attempts": 1,
     "offers": "NO ATTEMPT 2 (early band). After attempt 1 is refused: stop."},
    {"name": "late", "min": 8, "max": 45, "deadline": "deadline_late", "attempts": 2,
     "offers": "ATTEMPT 2 OFFER (only after attempt 1 is refused): the floor {floor} on the deadline {deadline_spoken} ({deadline}). After it is refused: stop."},
]
B_ATTEMPT1 = (" Attempt 1 offer: the full {full} on " + A1 + " (only if the customer already said the full amount is too much: "
              "the floor {floor} on that date instead; never name both amounts).")
KIT_B_BANDS = [
    dict(KIT_A_BANDS[0], offers=B_ATTEMPT1 + " No attempt 2 (early band): after attempt 1 is refused, stop."),
    dict(KIT_A_BANDS[1], offers=B_ATTEMPT1 + " Attempt 2 offer: the floor {floor} on the deadline {deadline_spoken} ({deadline}). After attempt 2 is refused, stop."),
]
KIT_B_LINE = ("- product_id {id}: {name}. Past-due amount {full}, {days} days late. Floor ({floor_label}) {floor}. "
              "Band {band}, deadline {deadline}, persuasion attempts allowed: {attempts}.{offers}")
KIT_B_HEADER = "LATE PRODUCTS, in this order ({count}):"

# --- verify_identity hooks (brief A rules 11-14) --------------------------------------------------
VERIFY_MSGS = {
    "error": "The check service failed. Nothing was checked. Ask the customer to repeat the same answer and call verify_identity again.",
    "verified": "Both security answers are correct. The customer is verified.",
    "swapped": "Day and month look swapped. This is NOT counted as a wrong answer. Ask the customer to say their date of birth again with the month as a word.",
    "unreadable": "The answer could not be read. Not counted as a wrong answer. Ask for the same answer again.",
    "correct": "Correct. Now ask the second security question: the last four digits of the phone number on file.",
    "failed": "Third wrong answer: the security check has FAILED. Do not state any debt, amount or product. Tell the customer to use the Freya Bank mobile app or visit a branch, thank them and say goodbye, ending with \"Have a good day.\"",
    "wrong": "That answer does not match. Say so and ask the SAME question again. Wrong answers left: {wrong_answers_left}.",
}
VERIFY_POST = dict(
    rules=[{"when": [["all_verified", "true"]], "say": VERIFY_MSGS["verified"], "set": {"bb_identity": "verified"}},
           {"when": [["hint", "equals", "day_month_swapped"]], "say": VERIFY_MSGS["swapped"]},
           {"when": [["ok", "false"], ["verified", "missing"]], "say": VERIFY_MSGS["unreadable"]},
           {"when": [["verified", "true"]], "say": VERIFY_MSGS["correct"]},
           {"when": [["wrong_answers_left", "lte", 0]], "say": VERIFY_MSGS["failed"], "set": {"bb_identity": "failed"}}],
    messages={"default": VERIFY_MSGS["wrong"], "error": VERIFY_MSGS["error"]})
VERIFY_PRE = dict(normalize={"answer": {"by": "field", "cases": {"date_of_birth": {"kind": "date", "order": "DMY"},
                                                                 "phone_last4": {"kind": "digits", "last": 4}}}})

# --- write hooks (brief A rules 6, 34-38, 41, 42) -------------------------------------------------
PROMISE_MSGS = {
    "ok": "The promise IS recorded. Tell the customer it is recorded and say exactly: \"You will receive a text message confirming this promise.\" Then thank them and say goodbye, ending with \"Have a good day.\"",
    "retry": "FAILED: the promise was NOT recorded. Do not say it is recorded. Call create_promise again right now with exactly the same values, once.",
    "give_up": "FAILED twice: the promise could NOT be recorded. Tell the customer honestly that you could not record the promise. Do not try again. Thank them and say goodbye, ending with \"Have a good day.\"",
}
PROMISE_PRE = dict(key_field="product_id", refs=["product_id"], normalize={"amount": {"kind": "amount"}},
                   guard={"date": {"min": "today", "max_var": "bb_deadline__{key}", "calendar": PRACTICE_CAL,
                                   "roll": "forward"}})
PROMISE_POST = dict(key_field="product_id", ok_when=[["ok", "true"], ["promise_id", "present"]], retries=1,
                    fail_mark=["ok", False], messages=PROMISE_MSGS)
DONE_MSGS = {"ok": "Done. Tell the customer, thank them and say goodbye, ending with \"Have a good day.\"",
             "give_up": "This action FAILED and was not carried out. Tell the customer honestly; do not claim it was done."}
SIMPLE_WRITE_POST = dict(ok_when=[["ok", "true"]], fail_mark=["ok", False], messages=DONE_MSGS)

# --- close_call (brief A rules 46 and the closing table; brief B closing) -------------------------
PRACTICE_OUTCOMES = {"promise": [], "paid": [], "transferred": ["restructuring", "human", "support"],
                     "no_promise": ["refused", "hardship", "dispute", "service_error"],
                     "not_verified": ["failed", "declined"],
                     "not_reached": ["callback", "no_callback", "wrong_number", "deceased", "unclear"]}
TRANSFER = {"if": [["count:transfer_to_agent", "gt", 0]], "outcome": "transferred",
            "reason": {"fact": "last:transfer_to_agent.queue", "map": {"general": "human"}}}
PROMISED = {"if": [["count:create_promise", "gt", 0]], "outcome": "promise"}
CALLBACK = {"if": [["count:schedule_callback", "gt", 0]], "outcome": "not_reached", "reason": "callback"}
FAILED = {"if": [["var:bb_identity", "equals", "failed"]], "outcome": "not_verified", "reason": "failed"}
A_RULES = [TRANSFER, PROMISED, CALLBACK, FAILED,
           {"if": [["gave_up:create_promise", "gt", 0]], "outcome": "no_promise", "reason": "service_error"},
           {"if": [["var:bb_identity", "equals", "verified"], ["model:outcome", "in", ["not_verified", "not_reached", "promise", ""]]],
            "outcome": "no_promise", "reason": "refused"},
           {"if": [["var:bb_identity", "not_equals", "verified"], ["model:outcome", "in", ["no_promise", "promise", "paid"]]],
            "outcome": "not_verified", "reason": "declined"},
           {"keep_model": True}]
B_RULES = [TRANSFER, CALLBACK, PROMISED, FAILED,
           {"if": [["all_logged:add_note.reason", "equals", "paid"]], "outcome": "paid"},
           {"if": [["logged:add_note.reason", "gt", 0]], "outcome": "no_promise",
            "reason": {"first_logged": "add_note.reason", "skip": ["paid"]}},
           {"keep_model": True}]
PRACTICE_DEFAULT = {"outcome": "no_promise", "reason": "refused"}


# --- the kit's workflows ---------------------------------------------------------------------------

def run_kit(code: str, **kwargs) -> dict:
    """Run a kit snippet with the full builtins: the kit's code is not bound by our runtime rules."""
    return embed.run(code, strict=False, **kwargs)


def kit_workflow(kit: pathlib.Path, brief: str) -> dict:
    """The kit builder's known-good workflow for practice brief 'a' or 'b'."""
    return json.loads((kit / "out" / ("brief-" + brief + ".workflow.json")).read_text(encoding="utf-8"))


def kit_code(kit: pathlib.Path, brief: str, node: str) -> str:
    """The code of a code node in the kit workflow."""
    node_def = kit_workflow(kit, brief)["nodes"][node]
    return node_def["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]


def kit_tool(kit: pathlib.Path, brief: str, name: str) -> dict:
    """A tool of the kit workflow, from any conversation node or the workflow-level tools."""
    wf = kit_workflow(kit, brief)
    for tool in wf.get("tools", []):
        if tool["function"]["name"] == name:
            return tool
    for node in wf["nodes"].values():
        for tool in node.get("tools", []):
            if tool["function"]["name"] == name:
                return tool
    raise KeyError(name)
