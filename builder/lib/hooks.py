"""Pre and post hooks for api_call tools (runtime/hooks.py is what runs inside Freya).

pre_hook() and post_hook() validate a config the builder read from the brief and the tool API file
and return the snippet for a tool's pre_process_code / post_process_code (tools.api_tool pre=, post=).
Give every tracked tool both hooks: the pre hook remembers the request, the post hook records it.

Variables the hooks write (read them in routes and in closing.close_hook facts):
    bb_key__<tool>, bb_arg__<tool>__<field>   the last request (pre hook)
    bb_adjusted__<tool>                       what a guard changed in the last request (pre hook)
    bb_count__<tool>                          successful writes (post hook, tracked tools)
    bb_done__<tool>                           keys written successfully, comma-separated
    bb_last__<tool>__<field>                  the arguments of the last successful write
    bb_log__<tool>__<field>                   'key:value' of each successful write, comma-separated
    bb_fail__<tool>__<key>, bb_failed_out__<tool>   failures per key, keys that used up their retries
    any variable named in a rule's "set"
"""
from __future__ import annotations

from builder.lib import embed
from builder.lib.calc import check_calendar, check_no_double_braces, check_var

KINDS = {"date": ("order", "future"), "digits": ("last",), "time": (), "amount": (), "text": ("upper",)}
ORDERS = ("DMY", "MDY")
ROLLS = ("forward", "backward")
GUARD_KEYS = ("min", "max_var", "calendar", "roll")
OPS = ("true", "false", "missing", "present", "equals", "not_equals", "in", "not_in", "contains",
       "lt", "lte", "gt", "gte")
MESSAGE_KEYS = ("ok", "retry", "give_up", "error", "default")
ADJUSTED_NOTE = "Note: {adjusted}. Tell the customer the value that was recorded."


def pre_hook(tool: str, *, normalize: dict | None = None, refs: list[str] | tuple = (),
             guard: dict | None = None, key_field: str = "", now_var: str = "now") -> str:
    """Snippet of a pre hook.

    normalize  {field: spec}; spec is {"kind": "date"|"digits"|"time"|"amount"|"text", ...} or
               {"by": other field, "cases": {value of that field: spec}} (e.g. one answer field whose
               kind depends on which question it answers). date: "order" "DMY"/"MDY" for numbers-only
               dates, "future": true to assume the next such date when the year is missing.
               digits: "last": n keeps the last n digits. text: "upper": true. A value that cannot be
               read for sure is left as it is: a wrong guess would be worse than a rejected value.
    refs       fields that must hold a known product id (bb_products); a wrong one is repaired.
    guard      {date field: {"min": "today", "max_var": "bb_deadline__{key}", "calendar": calendar,
               "roll": "forward"|"backward"}}: keep the date in range and on a business day.
               {key} is the value of key_field. If a bound cannot be read, the value stays.
    key_field  the field that identifies what is written (e.g. a product id), for per-key counts.
    """
    check_var(tool)
    check_var(now_var)
    normalize = dict(normalize or {})
    for field, spec in normalize.items():
        check_normalize(field, spec)
    if isinstance(refs, str) or any(not isinstance(r, str) or not r for r in refs):
        raise ValueError("refs must be a list of field names")
    guard = dict(guard or {})
    for field, spec in guard.items():
        check_guard(field, spec)
    cfg = {"tool": tool, "normalize": normalize, "refs": list(refs), "guard": guard,
           "key_field": key_field, "now_var": now_var}
    check_no_double_braces(cfg)
    return embed.snippet(("common", "dates", "hooks"), "run_pre", cfg, "pre")


def post_hook(tool: str, *, rules: list[dict] | tuple = (), messages: dict | None = None,
              ok_when: list | None = None, key_field: str = "", retries: int = 0,
              log_fields: list[str] | tuple = (), fail_mark: list | None = None,
              next_key: str = "what_to_do_next", strip_header: bool = True,
              adjusted_note: str = ADJUSTED_NOTE) -> str:
    """Snippet of a post hook.

    rules      [{"when": [[field, op, value?], ...], "say": template, "set": {var: value}}]: the first
               rule whose conditions all hold on the response data decides the message and sets
               variables (e.g. an identity state the routes read). ops: see OPS.
    messages   templates: "ok", "retry", "give_up" (tracked writes), "error" (no usable response),
               "default" (no rule matched). Placeholders: {key} {tries} {retries_left} {adjusted},
               {open:<tool>:<tool>...} (the products in bb_products, in order, that none of those tools
               has written yet, or "none") and any response field or variable name.
    ok_when    conditions that mean a write succeeded; giving it turns tracking on.
    retries    how many more attempts the brief allows after a failed write (message 'retry' until
               they are used up, then 'give_up').
    log_fields request fields to keep as 'key:value' for each successful write.
    fail_mark  [field, value] written into a failed response so the model cannot read it as success.
    next_key   the result field that carries the message; the system prompt must tell the model to obey it.
    """
    check_var(tool)
    for rule in rules:
        check_rule(rule)
    messages = dict(messages or {})
    for key, text in messages.items():
        if key not in MESSAGE_KEYS or not isinstance(text, str):
            raise ValueError("messages keys must be among " + repr(MESSAGE_KEYS) + " with text values")
    if ok_when is not None:
        check_conditions(ok_when, "ok_when")
    if not isinstance(retries, int) or retries < 0:
        raise ValueError("retries must be a non-negative integer")
    if not ok_when and (retries or log_fields or fail_mark):
        raise ValueError("retries, log_fields and fail_mark need ok_when (they apply to tracked writes)")
    if fail_mark is not None and (not isinstance(fail_mark, (list, tuple)) or len(fail_mark) != 2):
        raise ValueError("fail_mark must be [field, value]")
    if isinstance(log_fields, str) or not isinstance(next_key, str) or not next_key:
        raise ValueError("log_fields must be a list of field names and next_key a field name")
    cfg = {"tool": tool, "rules": [dict(r) for r in rules], "messages": messages, "ok_when": list(ok_when or []),
           "key_field": key_field, "retries": retries, "log_fields": list(log_fields),
           "fail_mark": list(fail_mark) if fail_mark else [], "next_key": next_key,
           "strip_header": strip_header, "adjusted_note": adjusted_note}
    check_no_double_braces(cfg)
    return embed.snippet(("common", "hooks"), "run_post", cfg, "post")


def check_normalize(field: str, spec: dict) -> None:
    """A normalize spec: a known kind with known parameters, or a 'by'/'cases' selector."""
    if not isinstance(spec, dict):
        raise ValueError("normalize." + field + " must be a dict")
    if "by" in spec:
        cases = spec.get("cases")
        if set(spec) - {"by", "cases"} or not isinstance(cases, dict) or not cases:
            raise ValueError("normalize." + field + ": a selector needs only 'by' and a non-empty 'cases' dict")
        for value, case in cases.items():
            check_normalize(field + "[" + str(value) + "]", case)
        return
    kind = spec.get("kind")
    if kind not in KINDS:
        raise ValueError("normalize." + field + ": kind must be one of " + ", ".join(KINDS))
    extra = set(spec) - {"kind"} - set(KINDS[kind])
    if extra:
        raise ValueError("normalize." + field + ": unknown keys " + repr(sorted(extra)))
    if "order" in spec and spec["order"] not in ORDERS:
        raise ValueError("normalize." + field + ": order must be one of " + repr(ORDERS))
    if "last" in spec and (not isinstance(spec["last"], int) or spec["last"] < 0):
        raise ValueError("normalize." + field + ": last must be a non-negative integer")


def check_guard(field: str, spec: dict) -> None:
    """A guard spec: known keys, a calendar, a valid roll and bounds."""
    if not isinstance(spec, dict) or set(spec) - set(GUARD_KEYS):
        raise ValueError("guard." + field + " must be a dict with keys among " + repr(GUARD_KEYS))
    check_calendar(spec.get("calendar"))
    if spec.get("roll", "forward") not in ROLLS:
        raise ValueError("guard." + field + ": roll must be one of " + repr(ROLLS))
    if spec.get("min", "today") != "today":
        raise ValueError("guard." + field + ": min can only be 'today'")
    if "max_var" in spec and (not isinstance(spec["max_var"], str) or not spec["max_var"]):
        raise ValueError("guard." + field + ": max_var must name a variable (it may use {key})")


def check_rule(rule: dict) -> None:
    """A post-hook rule: conditions, a message, optional variables to set."""
    if not isinstance(rule, dict) or not rule.get("when") or set(rule) - {"when", "say", "set"}:
        raise ValueError("each rule needs 'when' (a list of conditions) and may have 'say' and 'set'")
    check_conditions(rule["when"], "rule.when")
    for name in dict(rule.get("set") or {}):
        check_var(name)


def check_conditions(conditions: list, where: str) -> None:
    """Conditions are [field, op] or [field, op, value] with a known op."""
    if not isinstance(conditions, (list, tuple)) or not conditions:
        raise ValueError(where + " must be a non-empty list of conditions")
    for cond in conditions:
        if not isinstance(cond, (list, tuple)) or len(cond) not in (2, 3) or cond[1] not in OPS:
            raise ValueError(where + ": " + repr(cond) + " must be [field, op] or [field, op, value]; ops: " + ", ".join(OPS))
