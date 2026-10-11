"""The close tool's pre hook inside Freya: set the outcome and the reason from what happened in the call.

Runs inside Freya (see runtime/__init__.py). The outcome table, the order of the rules and every name
come from CFG, which the builder fills from the brief and the tool API file.

The model fills the close tool's fields at the end of the call; this hook overrides them with the
first rule that holds on the call state, so the bank's records follow the tool results and not the
model's memory of the conversation.

Facts a rule can test ([fact, op, value]):
    count:<tool>              successful writes (bb_count__<tool>; the engine's <tool>_success_count
                              when no hook ever ran for that tool)
    gave_up:<tool>            keys whose writes failed more often than the retries allow; also 1 when
                              the tool's last call ended in an engine error (an HTTP error skips the post hook)
    last:<tool>.<field>       an argument of the last successful write (engine <tool>_args.<field> as fallback)
    logged:<tool>.<field>     how many keys have a logged value
    all_logged:<tool>.<field> the value every product has logged, if they all logged the same one; '' otherwise
    var:<name>                any variable
    model:outcome, model:reason   what the model filled in
A reason is a literal; a dict with "fact" and an optional "map" from fact value to reason; a dict
with "first_logged": "<tool>.<field>" and an optional "skip" list (in product order); or a dict with
"model": true. A rule applies only if its outcome is in the table and its reason is allowed for that
outcome; when a computed reason cannot be resolved, the model's reason (if allowed) or the rule's
"fallback" is used. A rule with "keep_model": true keeps a valid model choice.
"""
from builder.lib.runtime.common import as_text, holds, lookup, split_csv, to_int, var_key  # embed: drop


def tool_and_field(text):
    """('tool', 'field') from 'tool.field'."""
    parts = as_text(text).split(".", 1)
    return parts[0], (parts[1] if len(parts) > 1 else "")


def log_entries(state, text):
    """[[key, value], ...] logged for 'tool.field', first entry per key, in logging order."""
    tool, field = tool_and_field(text)
    entries = []
    seen = []
    for item in split_csv(state.get("bb_log__" + tool + "__" + var_key(field))):
        parts = item.split(":", 1)
        if parts[0] not in seen:
            seen.append(parts[0])
            entries.append([parts[0], parts[1] if len(parts) > 1 else ""])
    return entries


def logged_in_order(state, text, cfg):
    """(order of keys, {key: value}) for 'tool.field'; product order, or logging order without products."""
    entries = log_entries(state, text)
    values = dict(entries)
    order = split_csv(state.get(cfg.get("products_var", "bb_products"))) or [entry[0] for entry in entries]
    return order, values


def all_logged(state, text, cfg):
    """The value every key logged for 'tool.field', if all keys logged the same one; '' otherwise."""
    order, values = logged_in_order(state, text, cfg)
    if not order:
        return ""
    found = []
    for key in order:
        if key not in values:
            return ""
        found.append(values[key])
    for value in found:
        if value != found[0]:
            return ""
    return found[0]


def first_logged(state, text, skip, cfg):
    """The first logged value for 'tool.field' in key order that is not in `skip`, or ''."""
    order, values = logged_in_order(state, text, cfg)
    for key in order:
        if key in values and values[key] not in skip:
            return values[key]
    return ""


def fact_value(state, name, model, cfg):
    """The value of one fact (see the module docstring), or None for an unknown fact."""
    parts = as_text(name).split(":", 1)
    kind = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    if kind == "count":
        own = state.get("bb_count__" + rest)
        return to_int(own) if own is not None else to_int(lookup(state, rest + "_success_count"))
    if kind == "gave_up":
        failed = len(split_csv(state.get("bb_failed_out__" + rest)))
        if failed == 0 and as_text(lookup(state, rest + "_response.status")) == "error":
            failed = 1           # an HTTP error skips the post hook; the engine still records the last result
        return failed
    if kind == "last":
        tool, field = tool_and_field(rest)
        own = state.get("bb_last__" + tool + "__" + var_key(field))
        return own if own is not None else lookup(state, tool + "_args." + field)
    if kind == "logged":
        return len(log_entries(state, rest))
    if kind == "all_logged":
        return all_logged(state, rest, cfg)
    if kind == "var":
        return lookup(state, rest)
    if kind == "model":
        return model.get(rest, "")
    return None


def reason_of(source, state, model, cfg):
    """The reason a rule names (see the module docstring); '' when it cannot be resolved."""
    if source is None:
        return ""
    if isinstance(source, str):
        return source
    if source.get("model"):
        return model.get("reason", "")
    if source.get("fact"):
        value = as_text(fact_value(state, source.get("fact"), model, cfg))
        return as_text(source.get("map", dict()).get(value, value))
    if source.get("first_logged"):
        return first_logged(state, source.get("first_logged"), source.get("skip", []), cfg)
    return ""


def valid_choice(outcome, reason, outcomes):
    """[outcome, reason] if the table allows it ('' reason for outcomes without reasons), else None."""
    if outcome not in outcomes:
        return None
    allowed = outcomes.get(outcome) or []
    if not allowed:
        return [outcome, ""]
    return [outcome, reason] if reason in allowed else None


def apply_rule(rule, state, model, cfg):
    """[outcome, reason] if the rule applies, else None."""
    if rule.get("keep_model"):
        return valid_choice(model.get("outcome", ""), model.get("reason", ""), cfg["outcomes"])

    def get(name):
        return fact_value(state, name, model, cfg)

    if not holds(rule.get("if"), get):
        return None
    outcome = rule.get("outcome")
    choice = valid_choice(outcome, reason_of(rule.get("reason"), state, model, cfg), cfg["outcomes"])
    if choice is None and isinstance(rule.get("reason"), dict):
        # the computed reason is missing (e.g. an argument was never captured): the facts still hold,
        # so take the model's reason if it fits this outcome, else the rule's fallback
        choice = valid_choice(outcome, model.get("reason", ""), cfg["outcomes"])
        if choice is None and rule.get("fallback"):
            choice = valid_choice(outcome, rule.get("fallback"), cfg["outcomes"])
    return choice


def words(text):
    """The lower-case name-like words of a text: 'Handed_Over / Desk.' -> ['handed_over', 'desk']."""
    out = []
    word = ""
    for char in as_text(text).lower() + " ":
        if char.isalnum() or char == "_":
            word = word + char
        elif word:
            out.append(word)
            word = ""
    return out


def read_model(outcome_text, reason_text, outcomes):
    """The model's choice read leniently: case, both values in one field, an outcome named only by its reason."""
    outcome = as_text(outcome_text).strip()
    reason = as_text(reason_text).strip()
    names = dict()
    for name in outcomes:
        names[name.lower()] = name
    reasons = dict()
    for name in outcomes:
        for item in outcomes.get(name) or []:
            reasons[item.lower()] = item
    if outcome not in outcomes:
        found = [names[w] for w in words(outcome) if w in names]
        if found:
            if not reason:
                rest = [reasons[w] for w in words(outcome) if w in reasons and (outcomes.get(found[0]) or []).count(reasons[w])]
                reason = rest[0] if rest else ""
            outcome = found[0]
    if reason and reason not in reasons.values() and reason.lower() in reasons:
        reason = reasons[reason.lower()]
    if outcome not in outcomes and reason:
        owners = [name for name in outcomes if (outcomes.get(name) or []).count(reason)]
        outcome = owners[0] if len(owners) == 1 else ""
    return {"outcome": outcome, "reason": reason}


def run_close(state, request, cfg):
    """Entry point of the close tool's pre hook. Never raises; an error is kept in bb_close_error."""
    try:
        body = request.get("body") if isinstance(request, dict) else None
        if not isinstance(body, dict):
            return
        outcome_field = cfg["outcome_field"]
        reason_field = cfg["reason_field"]
        body_in = [body.get(outcome_field), body.get(reason_field)]
        model = read_model(body.get(outcome_field), body.get(reason_field), cfg["outcomes"])
        chosen = None
        for rule in cfg.get("rules", []):
            chosen = apply_rule(rule, state, model, cfg)
            if chosen:
                break
        if not chosen:
            chosen = [cfg["default"].get("outcome"), cfg["default"].get("reason", "")]
        body[outcome_field] = chosen[0]
        if cfg["outcomes"].get(chosen[0]) and chosen[1]:
            body[reason_field] = chosen[1]
        else:
            body.pop(reason_field, None)
        state["bb_close"] = chosen[0] + ("/" + chosen[1] if chosen[1] else "")
        state["bb_close_model"] = as_text(body_in[0]) + "/" + as_text(body_in[1])     # what the model sent, for diagnosis
    except Exception as error:
        state["bb_close_error"] = str(error)
