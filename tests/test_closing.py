import copy
import itertools

import pytest

from builder.lib import closing, embed
from builder.lib.runtime import closing as rt
from dev.practice import A_RULES, B_RULES, PRACTICE_DEFAULT, PRACTICE_OUTCOMES, kit_tool, run_kit

# A made-up outcome table: names deliberately unlike any brief.
OUTCOMES = {"won": [], "handed_over": ["desk", "manager"], "lost": ["said_no", "broken", "argued"], "nobody": ["later", "gone"]}
RULES = [
    {"if": [["count:handover", "gt", 0]], "outcome": "handed_over", "reason": {"fact": "last:handover.team", "map": {"boss": "manager"}}},
    {"if": [["count:book", "gt", 0]], "outcome": "won"},
    {"if": [["gave_up:book", "gt", 0]], "outcome": "lost", "reason": "broken"},
    {"if": [["all_logged:memo.why", "equals", "said_no"]], "outcome": "lost", "reason": "said_no"},
    {"if": [["logged:memo.why", "gt", 0]], "outcome": "lost", "reason": {"first_logged": "memo.why", "skip": ["said_no"]}},
    {"if": [["var:who", "equals", "stranger"]], "outcome": "nobody", "reason": {"model": True}},
    {"keep_model": True},
]
DEFAULT = {"outcome": "lost", "reason": "said_no"}


def close(state: dict, outcome: str = "", reason: str = "", rules=RULES) -> dict:
    body = {"id": "c1", "result": outcome, "why": reason}
    code = closing.close_hook(outcome_field="result", reason_field="why", outcomes=OUTCOMES, rules=rules, default=DEFAULT)
    embed.run(code, state=state, request={"body": body})
    return body


@pytest.mark.parametrize("state,model,expected", [
    ({"bb_count__handover": 1, "bb_last__handover__team": "boss", "bb_count__book": 1}, ("won", ""), ("handed_over", "manager")),
    ({"bb_count__handover": 1, "bb_last__handover__team": "desk"}, ("", ""), ("handed_over", "desk")),
    ({"bb_count__handover": 1, "bb_last__handover__team": "nonsense"}, ("lost", "argued"), ("lost", "argued")),
    ({"handover_success_count": "1", "handover_args.team": "desk"}, ("", ""), ("handed_over", "desk")),   # engine keys when no hook ran
    ({"bb_count__book": 2}, ("lost", "said_no"), ("won", None)),
    ({"bb_failed_out__book": "a1"}, ("won", ""), ("lost", "broken")),
    ({"bb_products": "a1,a2", "bb_log__memo__why": "a1:said_no,a2:said_no"}, ("", ""), ("lost", "said_no")),
    ({"bb_products": "a1,a2", "bb_log__memo__why": "a2:argued,a1:said_no"}, ("", ""), ("lost", "argued")),
    ({"bb_products": "a1,a2", "bb_log__memo__why": "a1:said_no"}, ("won", ""), ("won", None)),   # not every product noted
    ({"bb_log__memo__why": "a1:said_no,a1:argued"}, ("", ""), ("lost", "said_no")),                # first entry per key wins
    ({"who": "stranger"}, ("nobody", "gone"), ("nobody", "gone")),
    ({"who": "stranger"}, ("nobody", "said_no"), ("lost", "said_no")),       # reason not allowed: falls through to default
    ({}, ("nobody", "later"), ("nobody", "later")),
    ({}, ("won", "later"), ("won", None)),                                     # reason dropped for an outcome without reasons
    ({}, ("invented", ""), ("lost", "said_no")),
    ({}, ("", ""), ("lost", "said_no")),
])
def test_rules(state, model, expected):
    body = close(dict(state), *model)
    assert (body["result"], body.get("why")) == expected
    assert body["id"] == "c1"


def test_a_holding_rule_with_an_unresolved_reason_falls_back_instead_of_vanishing():
    rule = {"if": [["count:handover", "gt", 0]], "outcome": "handed_over",
            "reason": {"fact": "last:handover.team"}, "fallback": "desk"}
    rules = [rule, {"keep_model": True}]
    assert close({"bb_count__handover": 1}, "handed_over", "manager", rules) == {"id": "c1", "result": "handed_over", "why": "manager"}
    body = close({"bb_count__handover": 1}, "lost", "said_no", rules)       # model reason does not fit: rule fallback
    assert (body["result"], body["why"]) == ("handed_over", "desk")
    with pytest.raises(ValueError):
        closing.close_hook(outcome_field="result", reason_field="why", outcomes=OUTCOMES, default=DEFAULT,
                           rules=[dict(rule, fallback="said_no")])


def test_runtime_helpers_directly():
    state = {"bb_products": "a1,a2", "bb_log__memo__why": "a2:x,a1:y,a2:z"}
    assert rt.log_entries(state, "memo.why") == [["a2", "x"], ["a1", "y"]]
    assert rt.first_logged(state, "memo.why", ["y"], {}) == "x"
    assert rt.all_logged(state, "memo.why", {}) == ""
    assert rt.valid_choice("won", "anything", OUTCOMES) == ["won", ""]
    assert rt.valid_choice("lost", "nope", OUTCOMES) is None
    assert rt.fact_value({}, "unknown:x", {}, {}) is None


def test_close_writes_its_choice_and_survives_bad_input():
    state = {"bb_count__book": 1}
    close(state, "lost", "argued")
    assert state["bb_close"] == "won" and state["bb_close_model"] == "lost/argued"
    code = closing.close_hook(outcome_field="result", reason_field="why", outcomes=OUTCOMES, rules=RULES, default=DEFAULT)
    assert embed.run(code, state={}, request=None) == {}
    assert embed.run(code, state={}, request={"body": "x"}) == {}


@pytest.mark.parametrize("bad", [
    dict(outcomes={}),
    dict(rules=[{"if": [["count:book", "gt", 0]], "outcome": "unknown"}]),
    dict(rules=[{"if": [["count:book", "gt", 0]], "outcome": "lost", "reason": "not_listed"}]),
    dict(rules=[{"if": [["sideways:book", "gt", 0]], "outcome": "won"}]),
    dict(rules=[{"if": [["count:book", "between", 0]], "outcome": "won"}]),
    dict(rules=[{"outcome": "won"}]),
    dict(rules=[{"if": [["count:book", "gt", 0]], "outcome": "lost", "reason": {"guess": True}}]),
    dict(default={"outcome": "lost", "reason": "nope"}),
    dict(default={"outcome": "won", "reason": "said_no"}),
])
def test_rejects_bad_config(bad):
    cfg = dict(outcome_field="result", reason_field="why", outcomes=OUTCOMES, rules=RULES, default=DEFAULT)
    cfg.update(bad)
    with pytest.raises(ValueError):
        closing.close_hook(**cfg)


# --- the kit's working builder wrote the closing logic by hand for each brief; ours must agree ----

MODELS =[("", "")] + [(o, r) for o, rs in PRACTICE_OUTCOMES.items() for r in (rs or [""])]
NOTES = [[], [("p1", "refused")], [("p1", "paid"), ("p2", "paid"), ("p3", "paid")], [("p1", "paid"), ("p2", "dispute")],
         [("p2", "hardship"), ("p1", "paid")], [("p1", "paid"), ("p2", "paid")]]


def states(transfer, promises, callback, identity, failed_out, notes, order):
    """The same call, as the kit's variables and as ours."""
    kit, ours = {}, {}
    if transfer:
        kit.update({"transfer_to_agent_success_count": 1, "transfer_to_agent_args.queue": transfer})
        ours.update({"bb_count__transfer_to_agent": 1, "bb_last__transfer_to_agent__queue": transfer})
    kit["promises_recorded"], ours["bb_count__create_promise"] = promises, promises
    if callback:
        kit["schedule_callback_success_count"], ours["bb_count__schedule_callback"] = 1, 1
    if identity != "none":
        kit["verify_identity_response.data.all_verified"] = "true" if identity == "verified" else "false"
        kit["verify_identity_response.data.wrong_answers_left"] = {"verified": 3, "failed": 0, "pending": 2}[identity]
        if identity in ("verified", "failed"):
            ours["bb_identity"] = identity
    if failed_out:
        kit["cp_failures"], ours["bb_failed_out__create_promise"] = 2, "p1"
    if notes:
        kit["notes_log"] = ours["bb_log__add_note__reason"] = ",".join(p + ":" + r for p, r in notes)
    kit["product_order"] = ours["bb_products"] = order
    return kit, ours


@pytest.mark.parametrize("brief,rules", [("a", A_RULES), ("b", B_RULES)])
def test_same_outcome_as_the_kit_close_hook(kit, brief, rules):
    kit_pre = kit_tool(kit, brief, "close_call")["pre_process_code"]
    ours = closing.close_hook(outcome_field="outcome", reason_field="reason", outcomes=PRACTICE_OUTCOMES,
                              rules=rules, default=PRACTICE_DEFAULT)
    grid = itertools.product([None, "restructuring", "general", "support"], [0, 1], [False, True],
                             ["none", "pending", "verified", "failed"], [False, True],
                             NOTES if brief == "b" else [[]], ["p1,p2,p3", ""] if brief == "b" else [""], MODELS)
    compared = 0
    for transfer, promises, callback, identity, failed_out, notes, order, model in grid:
        kit_state, our_state = states(transfer, promises, callback, identity, failed_out, notes, order)
        body = {"customer_id": "c", "outcome": model[0], "reason": model[1]}
        k, o = {"body": copy.deepcopy(body)}, {"body": copy.deepcopy(body)}
        run_kit(kit_pre, state=kit_state, request=k)
        embed.run(ours, state=our_state, request=o)
        kit_out = (k["body"].get("outcome"), k["body"].get("reason") or None)
        our_out = (o["body"].get("outcome"), o["body"].get("reason"))
        if kit_out[0] in PRACTICE_OUTCOMES and (not PRACTICE_OUTCOMES[kit_out[0]] or kit_out[1] in PRACTICE_OUTCOMES[kit_out[0]]):
            assert our_out == kit_out, (transfer, promises, callback, identity, failed_out, notes, order, model)
            compared += 1
        else:   # the kit sent an outcome the bank does not know; ours falls back to the default
            assert our_out == (PRACTICE_DEFAULT["outcome"], PRACTICE_DEFAULT["reason"])
    assert compared > 1000


@pytest.mark.parametrize("model,expected", [
    (("lost / argued", ""), ("lost", "argued")),            # outcome and reason written into one field
    (("Lost", "Argued"), ("lost", "argued")),               # case
    (("lost + argued", "argued"), ("lost", "argued")),
    (("handed_over: desk", ""), ("handed_over", "desk")),
    (("", "argued"), ("lost", "argued")),                   # a reason that belongs to one outcome only
    (("nonsense", "gone"), ("nobody", "gone")),
    (("won.", ""), ("won", None)),
])
def test_model_choice_is_read_leniently(model, expected):
    body = close({}, *model, rules=[{"keep_model": True}])
    assert (body["result"], body.get("why")) == expected


def test_a_reason_shared_by_two_outcomes_does_not_pick_one():
    outcomes = {"a": ["x"], "b": ["x"], "c": []}
    assert rt.read_model("", "x", outcomes) == {"outcome": "", "reason": "x"}
    assert rt.read_model("a/x", "", outcomes) == {"outcome": "a", "reason": "x"}


@pytest.mark.parametrize("op", ["present", "missing", "true", "false"])
def test_number_facts_refuse_presence_operators(op):
    from builder.lib import closing as cl
    with pytest.raises(ValueError, match="is a number"):
        cl.close_hook(outcome_field="result", reason_field="why", outcomes={"lost": ["gone"], "won": []},
                      rules=[{"if": [["gave_up:book", op]], "outcome": "lost", "reason": "gone"}],
                      default={"outcome": "won"})


def test_a_gave_up_count_of_zero_does_not_fire():
    body = close({}, "", "", rules=[{"if": [["gave_up:book", "gte", 1]], "outcome": "nobody", "reason": "gone"}])
    assert body["result"] != "nobody"


def test_gave_up_counts_a_last_write_that_ended_in_an_engine_error():
    rules = [{"if": [["gave_up:book", "gte", 1]], "outcome": "nobody", "reason": "gone"}]
    assert close({"book_response.status": "error", "book_failure_count": 1}, "", "", rules=rules)["result"] == "nobody"
    assert close({"book_response.status": "success", "book_failure_count": 1}, "", "", rules=rules)["result"] != "nobody"
