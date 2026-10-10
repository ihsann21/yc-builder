"""The close tool's pre hook: the outcome and reason follow the call state, not the model's memory.

close_hook() validates an outcome table and ordered rules that the builder read from the brief (and
the outcome enum of the tool API file) and returns the snippet for the close tool's
pre_process_code. The rule language and the facts are described in runtime/closing.py.
"""
from __future__ import annotations

import re

from builder.lib import embed
from builder.lib.calc import check_no_double_braces, check_var
from builder.lib.hooks import OPS

FACT = re.compile(r"^(count|gave_up|logged|all_logged|last|var|model):(.+)$")
NEEDS_FIELD = ("logged", "all_logged", "last")


def close_hook(*, outcome_field: str, reason_field: str, outcomes: dict[str, list[str]], rules: list[dict],
               default: dict, products_var: str = "bb_products") -> str:
    """Snippet of the close tool's pre hook.

    outcome_field, reason_field  the close tool's body fields (from the tool API file).
    outcomes   {outcome: [allowed reasons]}; [] means the outcome takes no reason. Take the outcome
               names from the tool API enum and the reasons from the brief's table.
    rules      ordered; the first that holds and names an allowed outcome and reason wins.
    default    {"outcome", "reason"} when no rule applies (e.g. the model sent nothing usable).
    """
    for name in (outcome_field, reason_field):
        check_var(name)
    if not isinstance(outcomes, dict) or not outcomes:
        raise ValueError("outcomes must map each outcome to its allowed reasons ([] for none)")
    for outcome, reasons in outcomes.items():
        if not isinstance(reasons, (list, tuple)) or any(not isinstance(r, str) or not r for r in reasons):
            raise ValueError("outcomes[" + repr(outcome) + "] must be a list of reason names")
    for rule in rules:
        check_rule(rule, outcomes)
    check_choice(default.get("outcome"), default.get("reason", ""), outcomes, "default")
    cfg = {"outcome_field": outcome_field, "reason_field": reason_field,
           "outcomes": {k: list(v) for k, v in outcomes.items()}, "rules": [dict(r) for r in rules],
           "default": dict(default), "products_var": products_var}
    check_no_double_braces(cfg)
    return embed.snippet(("common", "closing"), "run_close", cfg, "pre")


def check_rule(rule: dict, outcomes: dict) -> None:
    """A rule: keep_model alone, or conditions on known facts with an outcome and a reason source."""
    if not isinstance(rule, dict):
        raise ValueError("each rule must be a dict")
    if rule.get("keep_model"):
        if set(rule) != {"keep_model"}:
            raise ValueError("a keep_model rule takes no other keys")
        return
    if set(rule) - {"if", "outcome", "reason", "fallback"} or not isinstance(rule.get("if"), (list, tuple)) or not rule["if"]:
        raise ValueError("a rule needs 'if' (conditions) and 'outcome', and may have 'reason' and 'fallback': " + repr(rule))
    if "fallback" in rule:
        if isinstance(rule.get("reason"), str) or rule.get("reason") is None:
            raise ValueError("'fallback' only goes with a computed reason: " + repr(rule))
        check_choice(rule.get("outcome"), rule["fallback"], outcomes, "rule fallback " + repr(rule))
    for cond in rule["if"]:
        if not isinstance(cond, (list, tuple)) or len(cond) not in (2, 3) or cond[1] not in OPS:
            raise ValueError("condition " + repr(cond) + " must be [fact, op] or [fact, op, value]")
        check_fact(cond[0])
    source = rule.get("reason")
    if isinstance(source, str) or source is None:
        check_choice(rule.get("outcome"), source or "", outcomes, "rule " + repr(rule))
    else:
        if rule.get("outcome") not in outcomes or not outcomes[rule["outcome"]]:
            raise ValueError("rule " + repr(rule) + ": a computed reason needs an outcome that takes reasons")
        check_source(source)


def check_fact(name: object) -> None:
    """A fact name of the closing rule language."""
    match = FACT.match(str(name))
    if not match:
        raise ValueError("unknown fact " + repr(name) + "; facts: count:, gave_up:, logged:, all_logged:, last:, var:, model:")
    kind, rest = match.groups()
    if kind in NEEDS_FIELD and "." not in rest:
        raise ValueError("fact " + repr(name) + " needs the form " + kind + ":<tool>.<field>")
    if kind == "model" and rest not in ("outcome", "reason"):
        raise ValueError("fact " + repr(name) + ": model facts are model:outcome and model:reason")


def check_source(source: dict) -> None:
    """A computed reason: a fact with an optional map, the first logged value, or the model's reason."""
    if not isinstance(source, dict):
        raise ValueError("a reason must be a string or a dict")
    if set(source) == {"model"} and source["model"] is True:
        return
    if "fact" in source and set(source) <= {"fact", "map"}:
        check_fact(source["fact"])
        return
    if "first_logged" in source and set(source) <= {"first_logged", "skip"} and "." in str(source["first_logged"]):
        return
    raise ValueError("reason " + repr(source) + " must be {'fact', 'map'}, {'first_logged': 'tool.field', 'skip'} or {'model': true}")


def check_choice(outcome: object, reason: object, outcomes: dict, where: str) -> None:
    """The outcome is in the table and the reason is allowed for it ('' for outcomes without reasons)."""
    if outcome not in outcomes:
        raise ValueError(where + ": outcome " + repr(outcome) + " is not in the outcome table")
    allowed = outcomes[outcome]
    if (allowed and reason not in allowed) or (not allowed and reason):
        raise ValueError(where + ": reason " + repr(reason) + " is not allowed for outcome " + repr(outcome))
