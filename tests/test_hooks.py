import json
import copy
import datetime as dt

import pytest

from builder.lib import embed, hooks
from builder.lib.runtime import hooks as rt
from dev.practice import PROMISE_POST, PROMISE_PRE, VERIFY_POST, VERIFY_PRE, kit_tool, run_kit

CAL = {"workdays": [0, 1, 2, 3, 4], "holidays": ["2030-01-07"]}


# --- value normalisation -------------------------------------------------------------------------

@pytest.mark.parametrize("text,order,expected", [
    ("1988-03-14", "DMY", "1988-03-14"),
    ("1988-03-14T00:00", "DMY", "1988-03-14"),
    ("14/03/1988", "DMY", "1988-03-14"),
    ("14.3.1988", "DMY", "1988-03-14"),
    ("03/14/1988", "MDY", "1988-03-14"),
    ("1988/03/14", "DMY", "1988-03-14"),
    ("14 March 1988", "DMY", "1988-03-14"),
    ("March 14th, 1988", "DMY", "1988-03-14"),
    ("the 14th of march 1988", "DMY", "1988-03-14"),
    ("the fourteenth of March, nineteen eighty-eight", "DMY", "1988-03-14"),
    ("twenty-second of October one nine eight eight", "DMY", "1988-10-22"),
    ("1st Jan two thousand and five", "DMY", "2005-01-01"),
    ("31 February 1988", "DMY", None),      # not a real date: never guess
    ("14/03/88", "DMY", None),              # two-digit year: never guess
    ("14 March", "DMY", None),              # no year
    ("March 1988", "DMY", None),
    ("hello", "DMY", None),
    ("19 March 20 05", "DMY", None),       # 1920 or 2005: two readings
    ("14 March 3 1988", "DMY", None),      # a stray number
])
def test_parse_date_text(text, order, expected):
    assert rt.parse_date_text(text, order) == expected


def test_parse_date_text_infers_a_future_year_only_when_asked():
    today = dt.date(2030, 11, 20)
    assert rt.parse_date_text("2 December", "DMY", today, True) == "2030-12-02"
    assert rt.parse_date_text("3 January", "DMY", today, True) == "2031-01-03"
    assert rt.parse_date_text("3 January", "DMY", today, False) is None


@pytest.mark.parametrize("text,last,expected", [
    ("4821", 4, "4821"), ("my number ends 0044821", 4, "4821"), ("four eight two one", 4, "4821"),
    ("48", 4, None), ("12 34 56", 0, "123456"), ("no digits", 0, None),
    ("4821 and I got this number in 2019", 4, None), ("I have no one", 0, None), ("four hundred twenty", 0, None),
    ("+90 532 123 4821", 4, "4821"),
])
def test_digits(text, last, expected):
    assert rt.normalize_digits(text, last) == expected


@pytest.mark.parametrize("text,expected", [
    ("15:30", "15:30"), ("3pm", "15:00"), ("3:30 pm", "15:30"), ("10", "10:00"), ("9.05", "09:05"),
    ("12am", "00:00"), ("12 pm", "12:00"), ("15h", "15:00"), ("noon", "12:00"), ("25:00", None), ("later", None),
    ("5", None), ("9h", "09:00"),
])
def test_parse_time(text, expected):
    assert rt.parse_time(text) == expected


@pytest.mark.parametrize("value,expected", [
    (455.2, 455.2), ("455.20", 455.2), ("1,250.50", 1250.5), ("455,20", 455.2), ("1,250", 1250.0),
    ("$ 99", 99.0), (12.345, 12.35), ("four hundred", None), (True, None),
    ("1.250,50", 1250.5), ("1.250.000", 1250000.0), ("between 100 and 200", None), ("455.2 EUR 20", None),
    ("1e5", None), (float("inf"), None),
])
def test_parse_amount(value, expected):
    assert rt.parse_amount(value) == expected


def test_repair_ref():
    state = {"bb_products": "p1,p2", "bb_type__p1": "store_card", "bb_type__p2": "loan",
             "bb_name__p1": "store card ending 9911", "bb_name__p2": "loan"}
    assert rt.repair_ref("p2", state) == "p2"
    assert rt.repair_ref("P2", state) == "p2"
    assert rt.repair_ref("2", state) == "p2"
    assert rt.repair_ref("loan", state) == "p2"
    assert rt.repair_ref("store card", state) == "p1"
    assert rt.repair_ref("store card ending 9911", state) == "p1"
    assert rt.repair_ref("nonsense", state) == "nonsense"
    assert rt.repair_ref("nonsense", {"bb_products": "only"}) == "only"
    assert rt.repair_ref("x", {}) == "x"


@pytest.mark.parametrize("value,low,high,roll,expected,note", [
    ("2030-01-09", "2030-01-02", "2030-01-10", "forward", "2030-01-09", ""),
    ("2030-01-01", "2030-01-02", "2030-01-10", "forward", "2030-01-02", "before the earliest allowed date"),
    ("2030-01-20", "2030-01-02", "2030-01-10", "forward", "2030-01-10", "after the latest allowed date"),
    ("2030-01-05", "2030-01-02", "2030-01-10", "forward", "2030-01-08", "not a business day"),
    ("2030-01-05", "2030-01-02", "2030-01-10", "backward", "2030-01-04", "not a business day"),
    ("2030-01-12", "2030-01-02", "2030-01-12", "forward", "2030-01-11", "not a business day"),  # cannot pass the limit
    ("soon", "2030-01-02", "2030-01-10", "forward", "soon", ""),
])
def test_guard_date(value, low, high, roll, expected, note):
    day = lambda s: dt.date.fromisoformat(s)
    assert rt.guard_date(value, day(low), day(high), CAL, roll) == (expected, note)


# --- pre hook ------------------------------------------------------------------------------------

def pre(state: dict, body: dict, **cfg) -> tuple[dict, dict]:
    request = {"url": "u", "method": "POST", "headers": {}, "body": copy.deepcopy(body)}
    state = embed.run(hooks.pre_hook("book", **cfg), state=state, request=request)
    return state, request["body"]


def test_pre_hook_normalises_by_question():
    cfg = dict(normalize={"answer": {"by": "question", "cases": {"birthday": {"kind": "date", "order": "DMY"},
                                                                 "pin": {"kind": "digits", "last": 4}}}})
    assert pre({}, {"question": "birthday", "answer": "14 March 1988"}, **cfg)[1]["answer"] == "1988-03-14"
    assert pre({}, {"question": "pin", "answer": "it is 0099 4821"}, **cfg)[1]["answer"] == "4821"
    assert pre({}, {"question": "other", "answer": " x "}, **cfg)[1]["answer"] == " x "


def test_pre_hook_repairs_guards_and_captures():
    state = {"now": "2030-01-02T10:00", "bb_products": "a1,a2", "bb_deadline__a2": "2030-01-10"}
    state, body = pre(state, {"account": "2", "when": "2030-01-12", "sum": "1,000.5", "who": "c9"},
                      key_field="account", refs=["account"], normalize={"sum": {"kind": "amount"}},
                      guard={"when": {"max_var": "bb_deadline__{key}", "min": "today", "calendar": CAL, "roll": "forward"}})
    assert body == {"account": "a2", "when": "2030-01-10", "sum": 1000.5, "who": "c9"}
    assert state["bb_key__book"] == "a2" and state["bb_arg__book__when"] == "2030-01-10"
    assert state["bb_adjusted__book"] == "when changed from 2030-01-12 to 2030-01-10 (after the latest allowed date)"


def test_pre_hook_survives_odd_values_and_still_records_the_request():
    state = {"now": "2030-01-02T10:00", "bb_products": "a1,a2", "bb_deadline__a1": "2030-01-10",
             "bb_arg__book__stale": "old"}
    guard = {"when": {"min": "today", "max_var": "bb_deadline__{key}", "calendar": CAL}}
    for odd in (None, 7, ["2030-01-12"], {"d": 1}):
        state, body = pre(state, {"account": "²", "when": odd}, key_field="account", refs=["account"], guard=guard)
        assert body["when"] == odd and state["bb_key__book"] == "²"
        assert state["bb_arg__book__when"] == odd and "bb_arg__book__stale" not in state


def test_a_format_only_change_leaves_no_note():
    state = {"now": "2030-01-02T10:00", "bb_products": "a1", "bb_deadline__a1": "2030-01-10"}
    state, body = pre(state, {"account": "a1", "when": "2030-01-09T00:00"}, key_field="account",
                      guard={"when": {"min": "today", "max_var": "bb_deadline__{key}", "calendar": CAL}})
    assert body["when"] == "2030-01-09" and state["bb_adjusted__book"] == ""


def test_pre_hook_without_a_body_or_with_bad_state_does_nothing():
    state, body = pre({"now": "garbage"}, {"when": "2030-01-12"},
                      guard={"when": {"min": "today", "calendar": CAL}})
    assert body == {"when": "2030-01-12"}
    assert embed.run(hooks.pre_hook("book"), state={}, request=None) == {}


# --- post hook -----------------------------------------------------------------------------------

def post(state: dict, data, status: str = "success", **cfg) -> tuple[dict, dict]:
    result = {"status": status, "data": copy.deepcopy(data), "message": "m", "status_code": 200, "header": {"A": "b"}}
    state = embed.run(hooks.post_hook("book", **cfg), state=state, result=result)
    return state, result


WRITE = dict(key_field="account", ok_when=[["done", "true"], ["ref", "present"]], retries=1, fail_mark=["done", False],
             log_fields=["why"], messages={"ok": "Booked {key}.", "retry": "Failed for {key}, try once more.",
                                           "give_up": "Failed {tries} times for {key}. Say so."})


def test_post_hook_tracks_a_successful_write():
    state = {"bb_key__book": "a1", "bb_arg__book__account": "a1", "bb_arg__book__why": "x"}
    state, result = post(state, {"done": "true", "ref": "r1"}, **WRITE)
    assert "header" not in result and result["data"]["what_to_do_next"] == "Booked a1."
    assert state["bb_count__book"] == 1 and state["bb_done__book"] == "a1"
    assert state["bb_last__book__why"] == "x" and state["bb_log__book__why"] == "a1:x"


def test_post_hook_retries_then_gives_up_per_key():
    state = {"bb_key__book": "a1"}
    state, result = post(state, {"done": False}, **WRITE)
    assert result["data"] == {"done": False, "what_to_do_next": "Failed for a1, try once more."}
    assert state["bb_fail__book__a1"] == 1 and state["bb_count__book"] == 0
    state, result = post(state, {"done": "false"}, status="error", **WRITE)
    assert result["data"]["what_to_do_next"] == "Failed 2 times for a1. Say so."
    assert state["bb_failed_out__book"] == "a1"
    state["bb_key__book"] = "a2"
    state, result = post(state, None, status="error", **WRITE)          # service error, no data at all
    assert result["what_to_do_next"] == "Failed for a2, try once more."


def test_logged_values_with_separators_stay_one_entry():
    state = {"bb_key__book": "a1", "bb_arg__book__why": "no, thanks: later"}
    state, _ = post(state, {"done": True, "ref": "r"}, **WRITE)
    assert state["bb_log__book__why"] == "a1:no  thanks  later"


def test_post_hook_reports_a_changed_date():
    state = {"bb_key__book": "a1", "bb_adjusted__book": "when changed from A to B (x)"}
    state, result = post(state, {"done": True, "ref": "r"}, **WRITE)
    assert result["data"]["what_to_do_next"] == "Booked a1. Note: when changed from A to B (x). Tell the customer the value that was recorded."
    assert state["bb_adjusted__book"] == ""


CHECK = dict(rules=[{"when": [["all_ok", "true"]], "say": "All good.", "set": {"bb_identity": "verified"}},
                    {"when": [["left", "lte", 0]], "say": "Locked.", "set": {"bb_identity": "failed"}}],
             messages={"default": "Wrong, {left} left.", "error": "Service down."})


@pytest.mark.parametrize("data,status,message,identity", [
    ({"all_ok": "True"}, "success", "All good.", "verified"),
    ({"all_ok": False, "left": "0"}, "success", "Locked.", "failed"),
    ({"all_ok": False, "left": 2}, "success", "Wrong, 2 left.", None),
    ("<html>", "error", "Service down.", None),
])
def test_post_hook_rules(data, status, message, identity):
    state, result = post({}, data, status=status, **CHECK)
    where = result["data"] if isinstance(result["data"], dict) else result
    assert where["what_to_do_next"] == message
    assert state.get("bb_identity") == identity


@pytest.mark.parametrize("bad", [
    dict(normalize={"x": {"kind": "telepathy"}}),
    dict(normalize={"x": {"by": "q", "cases": {"a": {"kind": "digits", "last": -1}}}}),
    dict(guard={"x": {"roll": "sideways", "calendar": CAL}}),
    dict(guard={"x": {"calendar": {"workdays": [9], "holidays": []}}}),
    dict(refs="x"),
])
def test_pre_hook_rejects_bad_config(bad):
    with pytest.raises(ValueError):
        hooks.pre_hook("book", **bad)


@pytest.mark.parametrize("bad", [
    dict(rules=[{"when": [["x", "is_bigger"]], "say": "s"}]),
    dict(rules=[{"say": "no when"}]),
    dict(retries=-1, ok_when=[["x", "true"]]),
    dict(messages={"oops": "unknown key"}),
    dict(messages={"ok": "{{double}}"}),
    dict(fail_mark=["ok"]),
    dict(retries=1),                                          # retries without ok_when
])
def test_post_hook_rejects_bad_config(bad):
    with pytest.raises(ValueError):
        hooks.post_hook("book", **bad)


# --- the kit's working builder wrote these hooks by hand; ours must behave the same -------------


@pytest.mark.parametrize("data", [
    {"ok": True, "verified": True, "all_verified": True, "wrong_answers_left": 3},
    {"ok": "true", "verified": "true", "all_verified": "false", "wrong_answers_left": 3},
    {"ok": True, "verified": False, "all_verified": False, "wrong_answers_left": 2, "hint": "day_month_swapped"},
    {"ok": False, "error": "unreadable date"},
    {"ok": True, "verified": False, "all_verified": False, "wrong_answers_left": 0},
    {"ok": True, "verified": False, "all_verified": False, "wrong_answers_left": "1"},
    "Internal Server Error",
])
def test_verify_post_matches_the_kit(kit, data):
    kit_post = kit_tool(kit, "a", "verify_identity")["post_process_code"]
    k = {"status": "success", "data": copy.deepcopy(data), "header": {"x": "y"}}
    run_kit(kit_post, state={}, result=k)
    state, ours = post({}, data, **VERIFY_POST)
    assert ours["data"] == k["data"] and ("what_to_do_next" in ours) == ("what_to_do_next" in k)
    if not isinstance(data, dict):
        assert ours["what_to_do_next"] == k["what_to_do_next"]


@pytest.mark.parametrize("field,answer", [
    ("date_of_birth", "14 March 1988"), ("date_of_birth", "March 14th, 1988"), ("date_of_birth", "14/03/1988"),
    ("date_of_birth", "14-3-1988"), ("date_of_birth", "1988-03-14"), ("date_of_birth", "the 3rd of may 1990"),
    ("phone_last4", "4821"), ("phone_last4", "07700 900 4821"), ("phone_last4", "48"),
])
def test_verify_pre_matches_the_kit(kit, field, answer):
    kit_pre = kit_tool(kit, "a", "verify_identity")["pre_process_code"]
    k = {"body": {"field": field, "answer": answer}}
    run_kit(kit_pre, state={}, request=k)
    state, body = pre({}, {"field": field, "answer": answer}, **VERIFY_PRE)
    assert body == k["body"]


def test_promise_post_matches_the_kit(kit):
    kit_post = kit_tool(kit, "a", "create_promise")["post_process_code"]
    kit_state, our_state = {}, {"bb_key__book": "p1"}
    for data in ({"ok": False, "error": "boom"}, {"ok": True, "promise_id": "pr_1"}, {"ok": False}, {"ok": "false"}):
        k = {"status": "success", "data": copy.deepcopy(data), "header": {}}
        run_kit(kit_post, state=kit_state, result=k)
        our_state, ours = post(our_state, data, **PROMISE_POST)
        assert ours["data"] == k["data"]
    assert our_state["bb_count__book"] == kit_state["promises_recorded"] == 1
    assert our_state["bb_fail__book__p1"] == kit_state["cp_failures"] == 3


@pytest.mark.parametrize("date", ["2026-10-13", "2026-10-14", "2026-10-17", "2026-10-23", "2026-10-26",
                                  "2026-10-24", "2026-11-30", "2026-10-25"])
def test_promise_pre_matches_the_kit(kit, date):
    kit_pre = kit_tool(kit, "a", "create_promise")["pre_process_code"]
    kit_state = {"product_id": "p1", "deadline_p": "2026-10-23", "today_iso": "2026-10-14"}
    k = {"body": {"product_id": "p1", "amount": 50, "date": date}}
    run_kit(kit_pre, state=kit_state, request=k)
    our_state = {"now": "2026-10-14T11:00", "bb_products": "p1", "bb_single_product": "p1", "bb_deadline__p1": "2026-10-23"}
    state, body = pre(our_state, {"product_id": "p1", "amount": 50, "date": date}, **PROMISE_PRE)
    assert body == k["body"]


@pytest.mark.parametrize("time", ["3pm", "15:30", "15.30", "10", "3:30 pm", "19:00", "noon-ish"])
def test_callback_pre_matches_the_kit(kit, time):
    kit_pre = kit_tool(kit, "a", "schedule_callback")["pre_process_code"]
    k = {"body": {"date": "2026-10-15T00:00", "time": time}}
    run_kit(kit_pre, state={}, request=k)
    state, body = pre({}, {"date": "2026-10-15T00:00", "time": time},
                      normalize={"date": {"kind": "date"}, "time": {"kind": "time"}})
    assert body == k["body"]


def test_open_placeholder_lists_products_no_listed_tool_has_written():
    msgs = {"ok": "Still open: {open:book:mark}.", "retry": "r", "give_up": "Open: {open:book:mark}."}
    cfg = dict(WRITE, messages=msgs)
    state = {"bb_products": "a1,a2,a3", "bb_done__mark": "a3", "bb_key__book": "a1"}
    state, result = post(state, {"done": "true", "ref": "r"}, **cfg)
    assert result["data"]["what_to_do_next"] == "Still open: a2."
    state["bb_key__book"] = "a2"
    state, _ = post(state, {"done": False}, **cfg)
    state, result = post(state, {"done": False}, **cfg)                 # a2 failed out: it still needs a note
    assert result["data"]["what_to_do_next"] == "Open: a2."
    state["bb_done__mark"] = "a3,a2"
    state["bb_key__book"] = "a3"
    state, result = post(state, {"done": "true", "ref": "r"}, **cfg)
    assert result["data"]["what_to_do_next"] == "Still open: none."


def test_hook_fields_are_checked_against_the_tool_api(kit_api):
    from builder.lib import closing, tools
    ops, _ = tools.operations(kit_api)
    promise, verify, close = ops["create_promise"], ops["verify_identity"], ops["close_call"]
    hooks.pre_hook("create_promise", refs=["product_id"], key_field="product_id",
                   normalize={"amount": {"kind": "amount"}}, op=promise)
    hooks.post_hook("create_promise", ok_when=[["ok", "true"], ["promise_id", "present"]], key_field="product_id",
                    log_fields=["date"], fail_mark=["ok", False], op=promise)
    hooks.pre_hook("verify_identity", normalize={"answer": {"by": "field", "cases": {"x": {"kind": "time"}}}}, op=verify)
    hooks.post_hook("verify_identity", rules=[{"when": [["all_verified", "true"]], "say": "x"}], op=verify)
    with pytest.raises(ValueError, match="unknown field"):
        hooks.post_hook("create_promise", ok_when=[["success", "true"]], op=promise)       # renamed response field
    with pytest.raises(ValueError, match="unknown field"):
        hooks.pre_hook("create_promise", refs=["account_id"], op=promise)                  # renamed request field
    closing.close_hook(outcome_field="outcome", reason_field="reason", outcomes={"promise": [], "paid": []},
                       rules=[], default={"outcome": "promise"}, op=close)
    with pytest.raises(ValueError, match="not in the API enum"):
        closing.close_hook(outcome_field="outcome", reason_field="reason", outcomes={"no_contact": []},
                           rules=[], default={"outcome": "no_contact"}, op=close)
    with pytest.raises(ValueError, match="unknown field"):
        closing.close_hook(outcome_field="result", reason_field="reason", outcomes={"promise": []},
                           rules=[], default={"outcome": "promise"}, op=close)


@pytest.mark.parametrize("text", ["AB1234", "SW1A 2AA", "company 12345678X", "4821b"])
def test_digits_leave_codes_with_letters_alone(text):
    assert rt.normalize_digits(text, 0) is None and rt.normalize_digits(text, 4) is None


# --- calls that run side by side ------------------------------------------------------------------

def test_side_by_side_calls_each_get_their_own_key_and_arguments():
    msgs = {"ok": "Booked {key}. Open: {open:book}.", "retry": "Failed for {key}.", "give_up": "Gave up {key}."}
    cfg = dict(WRITE, messages=msgs)
    state = {"bb_products": "a1,a2,a3"}
    for account in ("a1", "a2", "a3"):                              # one model message, three calls
        state, _ = pre(state, {"account": account, "why": "w-" + account}, key_field="account")
    said = []
    for _ in range(3):                                              # the results come back afterwards
        state, result = post(state, {"done": "true", "ref": "r"}, **cfg)
        said.append(result["data"]["what_to_do_next"])
    assert said == ["Booked a1. Open: a2, a3.", "Booked a2. Open: a3.", "Booked a3. Open: none."]
    assert state["bb_done__book"] == "a1,a2,a3" and state["bb_log__book__why"] == "a1:w-a1,a2:w-a2,a3:w-a3"


def test_a_call_that_got_no_post_hook_does_not_shift_the_next_one():
    state = {"bb_products": "a1,a2"}
    state, _ = pre(state, {"account": "a1"}, key_field="account")
    state["book_failure_count"] = 1                                 # engine error: no post hook ran
    state, _ = pre(state, {"account": "a2"}, key_field="account")
    state, result = post(state, {"done": "true", "ref": "r"}, **WRITE)
    assert result["data"]["what_to_do_next"] == "Booked a2." and state["bb_done__book"] == "a2"


def test_a_retry_of_the_same_key_replaces_its_stale_entry():
    state = {}
    state, _ = pre(state, {"account": "a1", "why": "first"}, key_field="account")
    state, _ = pre(state, {"account": "a1", "why": "again"}, key_field="account")   # in flight: kept apart by key
    state, result = post(state, {"done": "true", "ref": "r"}, **WRITE)
    assert result["data"]["what_to_do_next"] == "Booked a1." and state["bb_last__book__why"] == "again"
    assert state["bb_queue__book"] == "[]"


def test_a_changed_date_note_stays_with_its_own_call():
    state = {"now": "2030-01-02T10:00", "bb_products": "a1,a2", "bb_deadline__a1": "2030-01-10",
             "bb_deadline__a2": "2030-01-20"}
    guard = {"when": {"min": "today", "max_var": "bb_deadline__{key}", "calendar": CAL}}
    state, _ = pre(state, {"account": "a1", "when": "2030-01-15"}, key_field="account", guard=guard)
    state, _ = pre(state, {"account": "a2", "when": "2030-01-15"}, key_field="account", guard=guard)
    state, first = post(state, {"done": True, "ref": "r"}, **WRITE)
    state, second = post(state, {"done": True, "ref": "r"}, **WRITE)
    assert "changed from 2030-01-15" in first["data"]["what_to_do_next"]
    assert second["data"]["what_to_do_next"] == "Booked a2."


def test_open_var_tracks_the_products_still_without_a_record():
    cfg = dict(WRITE, open_var="bb_open", open_tools=["book", "mark"])
    state = {"bb_products": "a1,a2", "bb_key__book": "a1"}
    state, _ = post(state, {"done": "true", "ref": "r"}, **cfg)
    assert state["bb_open"] == "a2"
    state["bb_key__book"] = "a2"
    state, _ = post(state, {"done": False}, **cfg)                       # a failed write leaves it open
    assert state["bb_open"] == "a2"
    state["bb_done__mark"] = "a2"                                        # e.g. a note written by another tool
    state, _ = post(state, {"done": False}, **cfg)
    assert state["bb_open"] == "none"


@pytest.mark.parametrize("bad", [dict(open_var="bb_open"), dict(open_tools=["book"]), dict(open_var="bb_open", open_tools="book")])
def test_open_var_needs_its_tools(bad):
    with pytest.raises(ValueError):
        hooks.post_hook("book", **bad)


def test_an_entry_left_by_a_call_with_no_post_hook_expires():
    # p1's call ended with no post hook and no failure count (e.g. cancelled); later p2 goes alone
    state = {"bb_products": "a1,a2"}
    state, _ = pre(state, {"account": "a1"}, key_field="account")
    queue = json.loads(state["bb_queue__book"])
    queue[0]["at"] -= 60
    state["bb_queue__book"] = json.dumps(queue)
    state, _ = pre(state, {"account": "a2"}, key_field="account")
    state, result = post(state, {"done": "true", "ref": "r"}, **WRITE)
    assert result["data"]["what_to_do_next"] == "Booked a2." and state["bb_done__book"] == "a2"


def test_side_by_side_calls_without_a_key_keep_their_own_arguments():
    state = {}
    state, _ = pre(state, {"why": "first"})
    state, _ = pre(state, {"why": "second"})
    cfg = dict(WRITE, key_field="")
    state, _ = post(state, {"done": "true", "ref": "r"}, **cfg)
    assert state["bb_last__book__why"] == "first"
    state, _ = post(state, {"done": "true", "ref": "r"}, **cfg)
    assert state["bb_last__book__why"] == "second"


def test_a_record_of_last_resort_that_gives_up_still_opens_the_gate():
    note = dict(WRITE, retries=0, open_var="bb_open", open_tools=["promise", "book"])
    state = {"bb_products": "a1,a2", "bb_done__promise": "a1", "bb_key__book": "a2"}
    state, _ = post(state, {"done": False}, **note)            # the note for a2 fails, no retries left
    assert state["bb_failed_out__book"] == "a2" and state["bb_open"] == "none"
