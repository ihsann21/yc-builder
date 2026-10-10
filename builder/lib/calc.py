"""Code nodes that compute what the model must not compute itself: date facts and product facts.

Each function validates its config (every value comes from the brief or the tool API file) and
returns the Python snippet for a passthrough code node (see workflow.code_node). The snippet runs
runtime/dates.py or runtime/products.py inside Freya and writes its results into the variable table.
"""
from __future__ import annotations

import re

from builder.lib import embed

ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CLOCK = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
DATE_RULES = {
    "today": (),
    "next_business_day": (),
    "business_days_after": ("n",),
    "calendar_days_after": ("n",),
    "end_of_month": (),
    "last_business_day_of_week": (),
}
ROLLS = ("", "forward", "backward")
WEEKDAY_MODES = ("", "following_week", "first_after_today")
DATE_FALLBACK = ("Date facts are not available right now. Do not work out any date yourself; "
                 "say that you cannot confirm dates at the moment.")
ACCOUNT_FALLBACK = ("The account details could not be loaded. Do not state or invent any amount; "
                    "say you do not have the information right now.")
TOKEN = re.compile(r"\{([A-Za-z0-9_.:]+)\}")
ITEM_TOKENS = ("id", "type", "type_words", "name", "full", "floor", "floor_label", "days", "band",
               "deadline", "deadline_spoken", "deadline_shifts", "attempts", "offers")


def dates_code(*, calendar: dict, dates: list[dict] | tuple = (), windows: list[dict] | tuple = (),
               weekday_mode: str = "", week_start: int = 0, calendar_days: int = 40, now_var: str = "now",
               facts_var: str = "date_facts", fallback: str = DATE_FALLBACK) -> str:
    """Snippet of the date code node.

    calendar      {"workdays": [0..6, Monday = 0], "holidays": ["YYYY-MM-DD", ...]} from the brief.
    dates         named dates: {"name", "rule", rule parameters, optional "roll", optional "label",
                  optional "shifts": "forward" | "backward"}; each lands in bb_date__<name> and
                  bb_date__<name>__spoken, and in the facts text if it has a label. With "shifts", a day guide
                  goes into bb_shifts__<name> (for the product facts: {deadline_shifts}): one line per day
                  from today to a week past that date, saying whether the day can be used, which business
                  day to use instead (the next one or the previous one, as the brief says), or that it is
                  after the date. The model looks the customer's day up instead of working it out.
    windows       {"name", "days": [rules], "from": "HH:MM", "to": "HH:MM", "after_now", "inclusive",
                  "var", "label"}: allowed slots, written as text into `var` and as data into bb_window__<name>.
    weekday_mode  how the brief defines "next <weekday>": "following_week", "first_after_today", or "" for no lines.
    The facts text (today, next business day, labelled dates, weekday lines, a calendar listing that
    reaches past the farthest named date) goes into `facts_var`; `fallback` replaces it if `now` cannot be read.
    """
    check_calendar(calendar)
    for item in dates:
        check_named(item, "dates")
        check_rule(item, "dates entry " + repr(item.get("name")))
        if item.get("shifts", "") not in ROLLS:
            raise ValueError("dates entry " + repr(item.get("name")) + ": shifts must be one of " + repr(ROLLS))
    for window in windows:
        check_window(window)
    if weekday_mode not in WEEKDAY_MODES:
        raise ValueError("weekday_mode must be one of " + repr(WEEKDAY_MODES))
    if not (isinstance(week_start, int) and 0 <= week_start <= 6):
        raise ValueError("week_start must be 0 (Monday) to 6 (Sunday)")
    if not (isinstance(calendar_days, int) and 1 <= calendar_days <= 400):
        raise ValueError("calendar_days must be an integer from 1 to 400")
    for name in (now_var, facts_var):
        check_var(name)
    cfg = {"calendar": {"workdays": list(calendar["workdays"]), "holidays": list(calendar["holidays"])},
           "dates": [dict(item) for item in dates], "windows": [dict(w) for w in windows],
           "weekday_mode": weekday_mode, "week_start": week_start, "calendar_days": calendar_days,
           "now_var": now_var, "facts_var": facts_var, "fallback": fallback}
    check_no_double_braces(cfg)
    return embed.snippet(("common", "dates"), "run_dates", cfg, "code")


def product_sources(node: str, tool: str, list_field: str, mapped_var: str = "") -> list[str]:
    """Where the engine may put the product list of an api_request node: the mapped variable, then
    the result keys named after the node and after the tool (the engine's naming is not documented)."""
    sources = [mapped_var] if mapped_var else []
    return sources + [node + "_response.data." + list_field, tool + "_response.data." + list_field]


def products_code(*, sources: list[str], list_field: str, id_field: str, type_field: str, amount_field: str,
                  days_field: str, item_fields: list[str], types: dict[str, dict], bands: list[dict],
                  line: str, header: str = "", default_type: dict | None = None, band_field: str = "",
                  known_dates: tuple[str, ...] = (), facts_var: str = "account_facts",
                  empty: str = ACCOUNT_FALLBACK, fallback: str = ACCOUNT_FALLBACK,
                  say_line: str = "", say_var: str = "debt_statement") -> str:
    """Snippet of the product code node (place it after the account lookup node).

    sources      variables that may hold the list (see product_sources); a scan of the table follows.
    *_field      field names of the response items, from the tool API file; item_fields lists them all.
    types        per type value: {"name": template, "floor_field": item field, "floor_label": text,
                 optional "floor_percent": percent of the full amount when there is no floor field (rounded
                 half up to the cent), optional "floor_min": that floor is never below it}. A computed
                 floor is never above the full amount; a floor field is used as it is.
    bands        [{"name", "min", "max", "deadline": named date of dates_code, "attempts", "offers": template}],
                 matched on band_field (days_field by default), inclusive, first match wins.
    line, header templates for the facts text; header may use {count}.
    say_line     optional template of what the agent says about one product when it states the debt
                 (e.g. "Your {name} is {full} past due and {days} days late."); the sentences of all
                 products, in order, go into the variable say_var, to be spoken word for word with
                 on_enter=wf.say("... {{debt_statement}} ..."), so no product, amount or day count is skipped.
    Template placeholders: {id} {type} {type_words} {name} {full} {floor} {floor_label} {days} {band}
    {deadline} {deadline_spoken} {deadline_shifts} {attempts} {offers} {field:<item field>} {date:<named date>}
    {date_spoken:<named date>} {shifts:<named date>}. {deadline_shifts} is the shifts text of the band's
    deadline (needs "shifts" on that date in dates_code). Amounts are written with two decimals.
    Writes bb_products, bb_product_count, bb_single_product, bb_account_state and per product
    bb_full__/bb_floor__/bb_days__/bb_band__/bb_deadline__/bb_type__/bb_name__<id>.
    """
    if not sources or any(not isinstance(s, str) or not s for s in sources):
        raise ValueError("sources must be a non-empty list of variable names")
    for label, value in (("list_field", list_field), ("id_field", id_field), ("amount_field", amount_field),
                         ("days_field", days_field)):
        if not isinstance(value, str) or not value:
            raise ValueError(label + " must name a field of the tool API response")
    fields = tuple(item_fields)
    for value in (id_field, type_field, amount_field, days_field, band_field):
        if value and value not in fields:
            raise ValueError("field " + repr(value) + " is not in item_fields " + repr(fields))
    type_list = list(types.values()) + ([default_type] if default_type else [])
    for tcfg in type_list:
        if tcfg.get("floor_field") and tcfg["floor_field"] not in fields:
            raise ValueError("floor_field " + repr(tcfg["floor_field"]) + " is not in item_fields")
        for key, low, high in (("floor_percent", 0, 100), ("floor_min", 0, None)):
            value = tcfg.get(key)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                      or value <= low or (high is not None and value > high)):
                raise ValueError(key + " must be a number above " + str(low)
                                 + (" and at most " + str(high) if high else "") + ": " + repr(value))
    check_bands(bands, known_dates)
    templates = [line, header, say_line] + [t.get("name", "") for t in type_list] + [b.get("offers", "") for b in bands]
    for template in templates:
        check_tokens(template, fields, known_dates)
    check_var(facts_var)
    check_var(say_var)
    cfg = {"sources": list(sources), "list_field": list_field, "id_field": id_field, "type_field": type_field,
           "amount_field": amount_field, "days_field": days_field, "band_field": band_field,
           "item_fields": list(fields), "types": {k: dict(v) for k, v in types.items()},
           "default_type": dict(default_type or {}), "bands": [dict(b) for b in bands], "line": line,
           "header": header, "facts_var": facts_var, "empty": empty, "fallback": fallback,
           "say_line": say_line, "say_var": say_var}
    check_no_double_braces(cfg)
    return embed.snippet(("common", "products"), "run_products", cfg, "code")


def check_bands(bands: list[dict], known_dates: tuple[str, ...]) -> None:
    """Named bands with min <= max, no overlap, and (if known_dates is given) known deadlines."""
    spans = []
    for band in bands:
        check_named(band, "bands")
        low, high = band.get("min"), band.get("max")
        for bound in (low, high):
            if bound is not None and not isinstance(bound, (int, float)):
                raise ValueError("band " + repr(band["name"]) + ": min and max must be numbers")
        if low is not None and high is not None and low > high:
            raise ValueError("band " + repr(band["name"]) + ": min is greater than max")
        if known_dates and band.get("deadline") and band["deadline"] not in known_dates:
            raise ValueError("band " + repr(band["name"]) + ": deadline " + repr(band["deadline"]) + " is not a named date")
        spans.append((float("-inf") if low is None else low, float("inf") if high is None else high, band["name"]))
    spans.sort()
    for first, second in zip(spans, spans[1:]):
        if second[0] <= first[1]:
            raise ValueError("bands " + repr(first[2]) + " and " + repr(second[2]) + " overlap")


def check_tokens(template: str, fields: tuple[str, ...], known_dates: tuple[str, ...]) -> None:
    """Every {placeholder} of a product template is one the runtime fills."""
    for token in TOKEN.findall(template or ""):
        kind, _, rest = token.partition(":")
        if not rest and token in ITEM_TOKENS + ("count",):
            continue
        if kind == "field" and rest in fields:
            continue
        if kind in ("date", "date_spoken", "shifts") and rest and (not known_dates or rest in known_dates):
            continue
        raise ValueError("unknown placeholder {" + token + "} in template " + repr(template))


def check_calendar(calendar: dict) -> None:
    """Workdays are distinct integers 0..6; holidays are ISO dates."""
    workdays = calendar.get("workdays") if isinstance(calendar, dict) else None
    holidays = calendar.get("holidays") if isinstance(calendar, dict) else None
    if not isinstance(workdays, (list, tuple)) or not workdays:
        raise ValueError("calendar.workdays must be a non-empty list of weekday numbers (Monday = 0)")
    if any(not isinstance(d, int) or not 0 <= d <= 6 for d in workdays) or len(set(workdays)) != len(workdays):
        raise ValueError("calendar.workdays must hold distinct integers from 0 (Monday) to 6 (Sunday)")
    if not isinstance(holidays, (list, tuple)) or any(not isinstance(h, str) or not ISO_DAY.match(h) for h in holidays):
        raise ValueError("calendar.holidays must be a list of 'YYYY-MM-DD' strings")


def check_rule(rule: dict, where: str) -> None:
    """A known rule kind with its required integer parameters and a valid roll."""
    kind = rule.get("rule")
    if kind not in DATE_RULES:
        raise ValueError(where + ": unknown rule " + repr(kind) + "; known: " + ", ".join(DATE_RULES))
    for param in DATE_RULES[kind]:
        if not isinstance(rule.get(param), int) or rule.get(param) < 0:
            raise ValueError(where + ": rule " + kind + " needs a non-negative integer " + repr(param))
    for param in ("months_ahead", "weeks_ahead"):
        if param in rule and (not isinstance(rule[param], int) or rule[param] < 0):
            raise ValueError(where + ": " + param + " must be a non-negative integer")
    if rule.get("roll", "") not in ROLLS:
        raise ValueError(where + ": roll must be one of " + repr(ROLLS))


def check_window(window: dict) -> None:
    """A named window with day rules, valid clock times, a target variable and a label."""
    check_named(window, "windows")
    days = window.get("days")
    if not isinstance(days, (list, tuple)) or not days:
        raise ValueError("window " + repr(window.get("name")) + " needs a non-empty 'days' list of rules")
    for rule in days:
        check_rule(rule, "window " + repr(window.get("name")))
    for key in ("from", "to"):
        if not CLOCK.match(str(window.get(key, ""))):
            raise ValueError("window " + repr(window.get("name")) + ": " + key + " must be 'HH:MM' (24-hour)")
    check_var(window.get("var"))
    if not isinstance(window.get("label"), str) or not window.get("label"):
        raise ValueError("window " + repr(window.get("name")) + " needs a 'label' for its facts text")


def check_named(item: dict, where: str) -> None:
    """The item has a usable 'name'."""
    if not isinstance(item, dict) or not NAME.match(str(item.get("name", ""))):
        raise ValueError(where + ": every entry needs a 'name' of letters, digits and underscores")


def check_var(name: object) -> None:
    """A variable name the platform accepts."""
    if not isinstance(name, str) or not NAME.match(name):
        raise ValueError("variable name " + repr(name) + " must start with a letter and hold only letters, digits and underscores")


def check_no_double_braces(value: object, path: str = "config") -> None:
    """No config string may hold '{{' or '}}': runtime text is filled by the runtime, not by Freya."""
    if isinstance(value, str):
        if "{{" in value or "}}" in value:
            raise ValueError(path + " contains a double brace; use the runtime's {name} placeholders instead")
    elif isinstance(value, dict):
        for key, item in value.items():
            check_no_double_braces(item, path + "." + str(key))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            check_no_double_braces(item, path + "[" + str(index) + "]")
