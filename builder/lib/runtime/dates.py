"""Dates inside Freya: business days, named dates from rules, a calendar listing and time windows.

Runs inside Freya (see runtime/__init__.py). Every rule value (workdays, holidays, counts, windows,
labels) comes from CFG, which the builder fills from the brief.

A calendar is a dict: {"workdays": [0..6, Monday = 0], "holidays": ["YYYY-MM-DD", ...]}.
A date rule is a dict with "rule" and its parameters:
    today                                   today
    next_business_day                       the first business day after today
    business_days_after       n             the n-th business day after today ("count_today": true counts today)
    calendar_days_after       n             today + n days
    end_of_month              months_ahead  the last day of this month (or of a later one)
    last_business_day_of_week weeks_ahead   the last business day of this week; "after_today": true moves
                                            to the next week when that day is today or already past
Rules that land on a calendar day accept "roll": "forward" or "backward" to reach a business day.
"""
import datetime
import re

from builder.lib.runtime.common import lookup, var_key  # embed: drop

DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August",
               "September", "October", "November", "December")
MAX_SCAN = 3700
MAX_CALENDAR_DAYS = 400
ONE_DAY = datetime.timedelta(days=1)
DAY_RE = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})")
CLOCK_RE = re.compile(r"^\s*\d{4}-\d{2}-\d{2}[T ](\d{1,2}):(\d{2})")


def parse_day(text):
    """The date at the start of an ISO text ('2030-01-02', '2030-01-02T09:30'), or None."""
    match = DAY_RE.match(str(text or ""))
    if not match:
        return None
    try:
        return datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except Exception:
        return None


def parse_clock(text):
    """'HH:MM' from an ISO date-time text, or ''."""
    match = CLOCK_RE.match(str(text or ""))
    if not match:
        return ""
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        return ""
    return "%02d:%02d" % (hour, minute)


def spoken(day):
    """'Wednesday 2 January 2030'."""
    return DAY_NAMES[day.weekday()] + " " + str(day.day) + " " + MONTH_NAMES[day.month - 1] + " " + str(day.year)


def is_business_day(day, cal):
    """True when `day` is a workday and not a holiday."""
    return day.weekday() in cal.get("workdays", []) and day.isoformat() not in cal.get("holidays", [])


def on_or_after(day, cal):
    """The first business day from `day` on, or None."""
    for step in range(MAX_SCAN):
        if is_business_day(day, cal):
            return day
        day = day + ONE_DAY
    return None


def on_or_before(day, cal):
    """The last business day up to `day`, or None."""
    for step in range(MAX_SCAN):
        if is_business_day(day, cal):
            return day
        day = day - ONE_DAY
    return None


def nth_business_day_after(day, n, cal, count_today=False):
    """The n-th business day after `day`; `day` counts only with count_today. n <= 0: `day` rolled forward."""
    if n <= 0:
        return on_or_after(day, cal)
    count = 1 if count_today and is_business_day(day, cal) else 0
    if count >= n:
        return day
    for step in range(MAX_SCAN):
        day = day + ONE_DAY
        if is_business_day(day, cal):
            count += 1
            if count >= n:
                return day
    return None


def week_start_of(day, week_start):
    """The first day of the week that holds `day`; week_start 0 = Monday ... 6 = Sunday."""
    return day - datetime.timedelta(days=(day.weekday() - week_start) % 7)


def last_business_day_of_week(day, cal, week_start):
    """The last business day of the week that holds `day`, or None."""
    start = week_start_of(day, week_start)
    probe = start + datetime.timedelta(days=6)
    while probe >= start:
        if is_business_day(probe, cal):
            return probe
        probe = probe - ONE_DAY
    return None


def end_of_month(day, months_ahead):
    """The last calendar day of the month `months_ahead` after the month of `day`."""
    index = day.month + months_ahead
    year = day.year + index // 12
    month = index % 12 + 1
    return datetime.date(year, month, 1) - ONE_DAY


def roll(day, direction, cal):
    """`day` moved to a business day: 'forward', 'backward', or unchanged."""
    if day is None:
        return None
    if direction == "forward":
        return on_or_after(day, cal)
    if direction == "backward":
        return on_or_before(day, cal)
    return day


def week_rule(rule, today, cal, week_start):
    """last_business_day_of_week, with weeks_ahead and after_today."""
    ahead = int(rule.get("weeks_ahead", 0))
    day = last_business_day_of_week(today + datetime.timedelta(days=7 * ahead), cal, week_start)
    if rule.get("after_today") and (day is None or day <= today):
        day = last_business_day_of_week(today + datetime.timedelta(days=7 * (ahead + 1)), cal, week_start)
    return day


def resolve(rule, today, cal, week_start=0):
    """The date a rule names, or None for an unknown rule."""
    kind = rule.get("rule")
    if kind == "business_days_after":
        return nth_business_day_after(today, int(rule.get("n", 1)), cal, bool(rule.get("count_today")))
    if kind == "last_business_day_of_week":
        return week_rule(rule, today, cal, week_start)
    if kind == "today":
        day = today
    elif kind == "next_business_day":
        day = nth_business_day_after(today, 1, cal)
    elif kind == "calendar_days_after":
        day = today + datetime.timedelta(days=int(rule.get("n", 0)))
    elif kind == "end_of_month":
        day = end_of_month(today, int(rule.get("months_ahead", 0)))
    else:
        return None
    return roll(day, rule.get("roll", ""), cal)


def weekday_table(today, mode, week_start):
    """([(name, date) for 'this <weekday>'], [(name, date) for 'next <weekday>']) in week order.

    'this' is the weekday in the current week. 'next' is the weekday in the following week
    (mode following_week) or the first such weekday after today (mode first_after_today).
    """
    start = week_start_of(today, week_start)
    this = []
    nxt = []
    for offset in range(7):
        day = start + datetime.timedelta(days=offset)
        name = DAY_NAMES[day.weekday()]
        this.append((name, day))
        if mode == "first_after_today":
            ahead = (day.weekday() - today.weekday()) % 7 or 7
            nxt.append((name, today + datetime.timedelta(days=ahead)))
        else:
            nxt.append((name, day + datetime.timedelta(days=7)))
    return this, nxt


def weekday_lines(today, mode, week_start):
    """Three lines: what this/next mean, then the 'this' list and the 'next' list."""
    first = DAY_NAMES[week_start]
    last = DAY_NAMES[(week_start + 6) % 7]
    meaning = "the first such weekday after today" if mode == "first_after_today" else "that weekday in the following week"
    head = "THIS <weekday> = that weekday in the current week (" + first + " to " + last + "). NEXT <weekday> = " + meaning + "."
    this, nxt = weekday_table(today, mode, week_start)
    return [head,
            "; ".join(["this " + name + " = " + day.isoformat() for name, day in this]),
            "; ".join(["next " + name + " = " + day.isoformat() for name, day in nxt])]


def calendar_lines(today, count, cal):
    """One line per day from today: '  2030-01-02 Wednesday B (today)', 'X weekend', 'X holiday'."""
    lines = []
    for offset in range(count):
        day = today + datetime.timedelta(days=offset)
        if is_business_day(day, cal):
            tag = "B"
        elif day.isoformat() in cal.get("holidays", []):
            tag = "X holiday"
        else:
            tag = "X weekend"
        lines.append("  " + day.isoformat() + " " + DAY_NAMES[day.weekday()] + " " + tag + (" (today)" if offset == 0 else ""))
    return lines


def add_minute(clock):
    """'HH:MM' one minute later; '24:00' after '23:59'."""
    hour = int(clock[:2])
    minute = int(clock[3:5]) + 1
    if minute == 60:
        hour += 1
        minute = 0
    return "%02d:%02d" % (hour, minute)


def window_slots(today, clock, spec, cal, week_start=0):
    """[[iso date, 'HH:MM' from, 'HH:MM' to], ...] for a window spec; today starts after now if asked."""
    slots = []
    seen = []
    for rule in spec.get("days", []):
        day = resolve(rule, today, cal, week_start)
        if day is None or day.isoformat() in seen:
            continue
        seen.append(day.isoformat())
        start = spec.get("from", "00:00")
        end = spec.get("to", "23:59")
        if day == today and spec.get("after_now") and clock:
            later = add_minute(clock)
            if later > start:
                start = later
        if start <= end:
            slots.append([day.isoformat(), start, end])
    return slots


def window_text(window, slots):
    """The window as one sentence for a prompt."""
    label = window.get("label", "")
    if not slots:
        return label + ": no day and time is possible."
    parts = [spoken(parse_day(s[0])) + " (" + s[0] + ") from " + s[1] + " to " + s[2] for s in slots]
    ends = "Both ends are included." if window.get("inclusive", True) else "The end time itself is not included."
    return label + ": " + "; ".join(parts) + ". " + ends + " Any other day or time is outside."


def today_line(today, clock, cal):
    """'TODAY: ... time now HH:MM. Today is a business day.'"""
    text = "TODAY: " + spoken(today) + " (" + today.isoformat() + ")"
    if clock:
        text = text + ", time now " + clock
    return text + ". Today is " + ("a business day." if is_business_day(today, cal) else "NOT a business day.")


def write_dates(state, cfg):
    """Compute everything and write it into `state`. Raises when the current date cannot be read."""
    cal = cfg["calendar"]
    week_start = int(cfg.get("week_start", 0))
    now = lookup(state, cfg.get("now_var", "now"))
    today = parse_day(now)
    if today is None:  # Exception, not ValueError: only the builtins in embed.ALLOWED_BUILTINS exist
        raise Exception("cannot read a date from the call variable " + str(cfg.get("now_var", "now")) + ": " + str(now))
    clock = parse_clock(now)
    following = nth_business_day_after(today, 1, cal)
    state["bb_today"] = today.isoformat()
    state["bb_time"] = clock
    state["bb_weekday"] = DAY_NAMES[today.weekday()]
    state["bb_business_today"] = "yes" if is_business_day(today, cal) else "no"
    state["bb_next_business_day"] = following.isoformat() if following else ""
    lines = [today_line(today, clock, cal)]
    if following:
        lines.append("NEXT BUSINESS DAY: " + spoken(following) + " (" + following.isoformat() + ").")
    farthest = today
    for item in cfg.get("dates", []):
        day = resolve(item, today, cal, week_start)
        key = "bb_date__" + var_key(item.get("name"))
        state[key] = day.isoformat() if day else ""
        state[key + "__spoken"] = spoken(day) if day else ""
        if day and day > farthest:
            farthest = day
        if day and item.get("label"):
            lines.append(item.get("label") + ": " + spoken(day) + " (" + day.isoformat() + ").")
    if cfg.get("weekday_mode"):
        lines.extend(weekday_lines(today, cfg.get("weekday_mode"), week_start))
    count = int(cfg.get("calendar_days", 40))
    if (farthest - today).days + 8 > count:
        count = (farthest - today).days + 8
    if count > MAX_CALENDAR_DAYS:
        count = MAX_CALENDAR_DAYS
    lines.append("CALENDAR (B = business day; X = not a business day):")
    lines.extend(calendar_lines(today, count, cal))
    state[cfg.get("facts_var", "date_facts")] = "\n".join(lines)
    for window in cfg.get("windows", []):
        slots = window_slots(today, clock, window, cal, week_start)
        state["bb_window__" + var_key(window.get("name"))] = ";".join([s[0] + " " + s[1] + "-" + s[2] for s in slots])
        state[window.get("var")] = window_text(window, slots)


def run_dates(state, cfg):
    """Entry point of the date code node. Never raises: on failure it writes the fallback text."""
    try:
        write_dates(state, cfg)
        state["bb_dates_state"] = "ok"
    except Exception as error:
        fallback = cfg.get("fallback", "")
        state[cfg.get("facts_var", "date_facts")] = fallback
        for window in cfg.get("windows", []):
            state[window.get("var")] = fallback
        state["bb_dates_state"] = "error"
        state["bb_dates_error"] = str(error)
