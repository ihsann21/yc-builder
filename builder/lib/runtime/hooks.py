"""Pre and post hooks of api_call tools, inside Freya.

Runs inside Freya (see runtime/__init__.py). Field names, kinds, limits, retry counts and every
message come from CFG, which the builder fills from the tool API file and the brief.

Pre hook (run_pre, names: vars, config): normalise body fields the model filled (dates, digits,
times, amounts), repair a reference to a known product, keep a date inside its allowed range, and
remember the request (bb_key__<tool>, bb_arg__<tool>__<field>) for the post hook.

Post hook (run_post, names: vars, result): drop the response headers, decide whether a write
succeeded, count successes and failures per key, choose the next-step sentence the model must
follow and put it into the result, and record facts for the close hook.
"""
import datetime
import re

from builder.lib.runtime.common import (  # embed: drop
    add_csv, as_text, decode, fill, holds, lookup, split_csv, to_int, var_key,  # embed: drop
)  # embed: drop
from builder.lib.runtime.dates import is_business_day, on_or_after, on_or_before, parse_day  # embed: drop

MONTHS = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
          "september": 9, "october": 10, "november": 11, "december": 12, "jan": 1, "feb": 2, "mar": 3,
          "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}
UNITS = {"zero": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
         "eight": 8, "nine": 9}
TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
         "seventeen": 17, "eighteen": 18, "nineteen": 19}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
            "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
            "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18, "nineteenth": 19,
            "twentieth": 20, "thirtieth": 30}
ISO_DATE = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?$")
NUMERIC_DATE = re.compile(r"^\s*(\d{1,4})\s*[./\- ]\s*(\d{1,2})\s*[./\- ]\s*(\d{1,4})\s*$")
CLOCK = re.compile(r"^\s*(\d{1,2})(?:\s*[:.h]\s*(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.|h)?\s*$")
DIGIT_GROUP = re.compile(r"\d[\d\s().+\-]*\d|\d")
AMOUNT_GROUP = re.compile(r"\d[\d.,]*")
NAMED_TIMES = {"noon": "12:00", "midday": "12:00", "midnight": "00:00"}


# --- values --------------------------------------------------------------------------------------

def iso(year, month, day):
    """'YYYY-MM-DD' for a real date, or None."""
    try:
        return datetime.date(year, month, day).isoformat()
    except Exception:
        return None


def words_of(text):
    """Lower-case words and numbers of a text; '14th' becomes '14', hyphens split words."""
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", as_text(text).lower())
    return re.sub(r"[^a-z0-9]+", " ", text).split()


def small_number(words, index):
    """(value, next index) for a number below 100 said in words at words[index], or (None, index)."""
    word = words[index] if index < len(words) else ""
    if word in TEENS:
        return TEENS[word], index + 1
    if word in ORDINALS:
        return ORDINALS[word], index + 1
    if word in TENS:
        value = TENS[word]
        following = words[index + 1] if index + 1 < len(words) else ""
        if UNITS.get(following, 0) > 0:
            return value + UNITS[following], index + 2
        if 0 < ORDINALS.get(following, 0) < 10:
            return value + ORDINALS[following], index + 2
        return value, index + 1
    if word in UNITS:
        return UNITS[word], index + 1
    return None, index


def spoken_numbers(words):
    """The numbers in a list of words, in order: '14' -> 14, 'twenty second' -> 22,
    'nineteen sixty three' -> 19, 63, 'one nine six three' -> 1963, 'two thousand and five' -> 2005."""
    out = []
    run = ""
    index = 0
    while index < len(words):
        word = words[index]
        following = words[index + 1] if index + 1 < len(words) else ""
        if word in UNITS and following == "thousand":
            index += 2
            if index < len(words) and words[index] == "and":
                index += 1
            rest, index = small_number(words, index)
            out.append(UNITS[word] * 1000 + (rest or 0))
            continue
        if word in UNITS:
            run = run + str(UNITS[word])
            index += 1
            continue
        if run:
            out.append(int(run))
            run = ""
        if word.isdigit():
            out.append(int(word))
            index += 1
            continue
        value, after = small_number(words, index)
        if value is not None:
            out.append(value)
            index = after
        else:
            index += 1
    if run:
        out.append(int(run))
    return out


def year_and_day(numbers):
    """(year, day) when the numbers allow exactly one reading, (None, day) for a lone day, else (None, None).

    A year is a 4-digit number or a spoken pair such as 19, 88; the one number left must be a day.
    '19 March 20 05' has two readings (1920 or 2005), so it gives (None, None).
    """
    readings = []
    for index in range(len(numbers)):
        if 1000 <= numbers[index] <= 2999:
            readings.append([numbers[index], numbers[:index] + numbers[index + 1:]])
    for index in range(len(numbers) - 1):
        if numbers[index] in (19, 20) and 0 <= numbers[index + 1] <= 99:
            readings.append([numbers[index] * 100 + numbers[index + 1], numbers[:index] + numbers[index + 2:]])
    found = [[year, rest[0]] for year, rest in readings if len(rest) == 1 and 1 <= rest[0] <= 31]
    if len(found) == 1:
        return found[0][0], found[0][1]
    if not readings and len(numbers) == 1 and 1 <= numbers[0] <= 31:
        return None, numbers[0]
    return None, None


def parse_date_text(text, order="DMY", today=None, future=False):
    """'YYYY-MM-DD' from a date the way a person or a model wrote it, or None if it is not certain.

    ISO stays ISO. Numbers only: order says which comes first (a 4-digit first number is a year).
    Words: one month name, a day and a 4-digit year, in any order, digits or words. Two-digit years
    and impossible dates give None. With future=True and `today`, a missing year is the next such date.
    """
    text = as_text(text)
    match = ISO_DATE.match(text)
    if match:
        return iso(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    match = NUMERIC_DATE.match(text)
    if match:
        first, second, third = match.group(1), match.group(2), match.group(3)
        if len(first) == 4:
            return iso(int(first), int(second), int(third))
        if len(third) != 4:
            return None
        if order == "MDY":
            return iso(int(third), int(first), int(second))
        return iso(int(third), int(second), int(first))
    words = words_of(text)
    months = [MONTHS[w] for w in words if w in MONTHS]
    if len(months) != 1:
        return None
    year, day = year_and_day(spoken_numbers([w for w in words if w not in MONTHS]))
    if day is None:
        return None
    if year is None and future and today is not None:
        guess = iso(today.year, months[0], day)
        if guess is not None and guess < today.isoformat():
            guess = iso(today.year + 1, months[0], day)
        return guess
    if year is None:
        return None
    return iso(year, months[0], day)


def normalize_digits(text, last=0):
    """The digits of one number in a text, the last `last` of them if asked; None if unsure.

    One run of digits (spaces, dots, dashes, brackets and + allowed inside) or only digit words.
    Two numbers ('3906 ... in 2019') or other words between digit words give None.
    """
    text = as_text(text)
    if re.search(r"[A-Za-z][0-9]|[0-9][A-Za-z]", text):
        return None                      # a code with letters in it ('AB1234', 'SW1A'): not only digits
    groups = DIGIT_GROUP.findall(text)
    if groups:
        if len(groups) != 1:
            return None
        digits = re.sub(r"\D", "", groups[0])
    else:
        words = words_of(text)
        if not words or [w for w in words if w not in UNITS]:
            return None
        digits = "".join([str(UNITS[w]) for w in words])
    if last and len(digits) < last:
        return None
    return digits[len(digits) - last:] if last else digits


def parse_time(text):
    """'HH:MM' (24-hour) from '15:30', '3pm', '3:30 p.m.', '15h', 'noon'; None if unclear."""
    text = as_text(text).strip().lower()
    if text in NAMED_TIMES:
        return NAMED_TIMES[text]
    match = CLOCK.match(text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    half = (match.group(3) or "").replace(".", "")
    if match.group(2) is None and not half and hour < 10:
        return None                      # a bare '5' could be 05:00 or 17:00
    if half in ("am", "pm"):
        if hour < 1 or hour > 12:
            return None
        if half == "pm" and hour < 12:
            hour += 12
        if half == "am" and hour == 12:
            hour = 0
    if hour > 23 or minute > 59:
        return None
    return "%02d:%02d" % (hour, minute)


def half_up(number):
    """A number rounded to two decimals, halves away from zero."""
    sign = -1 if number < 0 else 1
    return sign * int(abs(number) * 100 + 0.5) / 100.0


def parse_amount(value):
    """A money amount from a number, or from text holding exactly one number ('1,250.50', '1.250,50',
    '455,20', '$ 99'); None for words, several numbers or anything unreadable."""
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, (int, float)):
            return half_up(float(value))
        groups = AMOUNT_GROUP.findall(as_text(value))
        if len(groups) != 1:
            return None
        number = groups[0].rstrip(".,")
        if "," in number and "." in number:
            decimal = "," if number.rfind(",") > number.rfind(".") else "."
            number = number.replace("." if decimal == "," else ",", "").replace(",", ".")
        elif number.count(",") == 1 and len(number.split(",")[1]) in (1, 2):
            number = number.replace(",", ".")
        elif "," in number or number.count(".") > 1:
            number = number.replace(",", "").replace(".", "")
        return half_up(float(number))
    except Exception:
        return None


def normalize(value, spec, today):
    """The value in the form `spec` asks for, or the value unchanged when it cannot be read for sure."""
    kind = spec.get("kind")
    if kind == "date":
        out = parse_date_text(value, spec.get("order", "DMY"), today, bool(spec.get("future")))
    elif kind == "digits":
        out = normalize_digits(value, int(spec.get("last", 0)))
    elif kind == "time":
        out = parse_time(value)
    elif kind == "amount":
        out = parse_amount(value)
    elif kind == "text":
        out = " ".join(as_text(value).split())
        out = out.upper() if spec.get("upper") else out
    else:
        out = None
    return value if out is None else out


def repair_ref(value, state):
    """A product reference the model got wrong, mapped to a known id; unchanged when unsure.

    Known ids are bb_products. Tries: exact id, id ignoring case, a 1-based position, the product
    type in words, the product's spoken name, and the only product.
    """
    ids = split_csv(state.get("bb_products"))
    if not ids:
        return value
    text = as_text(value).strip()
    if text in ids:
        return text
    for pid in ids:
        if pid.lower() == text.lower():
            return pid
    if text.isdigit() and 1 <= int(text) <= len(ids):
        return ids[int(text) - 1]
    words = " ".join(words_of(text))
    for prefix in ("bb_type__", "bb_name__"):
        found = [pid for pid in ids if words and " ".join(words_of(state.get(prefix + var_key(pid)))) == words]
        if len(found) == 1:
            return found[0]
    if len(ids) == 1:
        return ids[0]
    return value


def guard_date(value, low, high, cal, direction):
    """(date, note): the date kept within [low, high] and moved onto a business day; note says why."""
    day = parse_day(value)
    if day is None:
        return value, ""
    notes = []
    if low is not None and day < low:
        day = low
        notes.append("before the earliest allowed date")
    if high is not None and day > high:
        day = high
        notes.append("after the latest allowed date")
    if cal and not is_business_day(day, cal):
        moved = on_or_before(day, cal) if direction == "backward" else on_or_after(day, cal)
        if moved is not None and high is not None and moved > high:
            moved = on_or_before(day, cal)
        if moved is not None and low is not None and moved < low:
            moved = None
        if moved is not None:
            day = moved
            notes.append("not a business day")
    return day.isoformat(), ", ".join(notes)


# --- pre hook ------------------------------------------------------------------------------------

def guard_field(body, name, spec, state, cfg, key):
    """Apply one guard spec to body[name]. Returns a note on what changed, or ''.

    The guard runs only when every bound it was given can be read; otherwise the value stays.
    """
    if name not in body:
        return ""
    low = None
    high = None
    if spec.get("min") == "today":
        low = parse_day(lookup(state, cfg.get("now_var", "now")))
        if low is None:
            return ""
    if spec.get("max_var"):
        def get(token):
            return var_key(key) if token == "key" else None
        high = parse_day(lookup(state, fill(spec.get("max_var"), get)))
        if high is None:
            return ""
    old = body[name]
    if not isinstance(old, str) or parse_day(old) is None:
        return ""
    new, why = guard_date(old, low, high, spec.get("calendar"), spec.get("roll", "forward"))
    if new == old:
        return ""
    body[name] = new
    if not why:
        return ""                        # only the form changed (a time part dropped): nothing to tell
    return name + " changed from " + old + " to " + new + " (" + why + ")"


def normalize_field(body, name, spec, today):
    """Normalise body[name] by its spec (a kind, or a selector on another field)."""
    if name not in body:
        return
    chosen = spec.get("cases", dict()).get(as_text(body.get(spec.get("by")))) if spec.get("by") else spec
    if chosen:
        body[name] = normalize(body[name], chosen, today)


def run_pre(state, request, cfg):
    """Entry point of a pre hook. Never raises. Each field is handled on its own, so one bad value
    cannot stop the others or the record of the request; errors go to bb_pre_error__<tool>."""
    tool = cfg.get("tool", "tool")
    body = request.get("body") if isinstance(request, dict) else None
    if not isinstance(body, dict):
        return
    errors = []
    today = parse_day(lookup(state, cfg.get("now_var", "now")))
    for name, spec in cfg.get("normalize", dict()).items():
        try:
            normalize_field(body, name, spec, today)
        except Exception as error:
            errors.append(name + ": " + str(error))
    for name in cfg.get("refs", []):
        try:
            if name in body:
                body[name] = repair_ref(body[name], state)
        except Exception as error:
            errors.append(name + ": " + str(error))
    key = as_text(body.get(cfg.get("key_field"))) if cfg.get("key_field") else ""
    notes = []
    for name, spec in cfg.get("guard", dict()).items():
        try:
            note = guard_field(body, name, spec, state, cfg, key)
            if note:
                notes.append(note)
        except Exception as error:
            errors.append(name + ": " + str(error))
    prefix = "bb_arg__" + tool + "__"
    for name in list(state.keys()):
        if str(name).startswith(prefix):
            state.pop(name, None)
    for name in body:
        state[prefix + var_key(name)] = body[name]
    state["bb_adjusted__" + tool] = "; ".join(notes)
    state["bb_key__" + tool] = key
    state["bb_pre_error__" + tool] = "; ".join(errors)


# --- post hook -----------------------------------------------------------------------------------

def record_success(state, tool, key, cfg):
    """Count a successful write and keep its arguments and logged fields."""
    state["bb_count__" + tool] = to_int(state.get("bb_count__" + tool)) + 1
    if key:
        state["bb_done__" + tool] = add_csv(state.get("bb_done__" + tool), key)
    prefix = "bb_arg__" + tool + "__"
    for name in list(state.keys()):
        if str(name).startswith(prefix):
            state["bb_last__" + tool + "__" + str(name)[len(prefix):]] = state.get(name)
    for field in cfg.get("log_fields", []):
        value = clean_entry(state.get(prefix + var_key(field)))
        log = "bb_log__" + tool + "__" + var_key(field)
        state[log] = add_csv(state.get(log), clean_entry(key) + ":" + value)


def clean_entry(value):
    """Text safe inside a 'key:value,key:value' log: separators become spaces."""
    return as_text(value).replace(",", " ").replace(":", " ")


def open_items(state, tools):
    """The products (bb_products, in order) that none of `tools` has written yet, or 'none'."""
    done = []
    for tool in tools:
        done = done + split_csv(state.get("bb_done__" + tool))
    items = [item for item in split_csv(state.get("bb_products")) if item not in done]
    return ", ".join(items) if items else "none"


def record_failure(state, tool, key, cfg):
    """Count a failed write for this key. Returns how many times it has failed."""
    counter = "bb_fail__" + tool + "__" + var_key(key or "-")
    failures = to_int(state.get(counter)) + 1
    state[counter] = failures
    state["bb_count__" + tool] = to_int(state.get("bb_count__" + tool))
    if failures > to_int(cfg.get("retries")):
        state["bb_failed_out__" + tool] = add_csv(state.get("bb_failed_out__" + tool), key or "-")
    return failures


def data_getter(data):
    """A getter for conditions on response data (nested keys allowed)."""
    def get(name):
        return lookup(data, name)
    return get


def first_rule(cfg, data):
    """The first rule whose conditions hold on the response data, or None."""
    for rule in cfg.get("rules", []):
        if holds(rule.get("when"), data_getter(data)):
            return rule
    return None


def choose_message(cfg, service_ok, data, tracked, success, failures):
    """(message template, variables to set) for this result."""
    messages = cfg.get("messages", dict())
    if service_ok:
        rule = first_rule(cfg, data)
        if rule is not None:
            return rule.get("say", ""), rule.get("set", dict())
    if tracked:
        if success:
            return messages.get("ok", ""), dict()
        if failures > to_int(cfg.get("retries")):
            return messages.get("give_up", ""), dict()
        return messages.get("retry", ""), dict()
    if not service_ok:
        return messages.get("error", ""), dict()
    return messages.get("default", ""), dict()


def run_post(state, result, cfg):
    """Entry point of a post hook. Never raises; an error is kept in bb_post_error__<tool>."""
    tool = cfg.get("tool", "tool")
    try:
        if not isinstance(result, dict):
            return
        if cfg.get("strip_header", True):
            result.pop("header", None)
        data = decode(result.get("data"))
        if isinstance(data, dict):
            result["data"] = data
        service_ok = isinstance(data, dict) and as_text(result.get("status") or "success") == "success"
        key = as_text(state.get("bb_key__" + tool))
        if not key and cfg.get("key_field"):
            key = as_text(lookup(state, tool + "_args." + cfg.get("key_field")))
        tracked = bool(cfg.get("ok_when"))
        success = (service_ok and holds(cfg.get("ok_when"), data_getter(data))) if tracked else service_ok
        failures = 0
        if tracked and success:
            record_success(state, tool, key, cfg)
        elif tracked:
            failures = record_failure(state, tool, key, cfg)
            mark = cfg.get("fail_mark")
            if mark and isinstance(data, dict):
                data[mark[0]] = mark[1]
        template, updates = choose_message(cfg, service_ok, data, tracked, success, failures)
        for name, value in updates.items():
            state[name] = value
        adjusted = as_text(state.get("bb_adjusted__" + tool))

        def get(name):
            if name == "key":
                return key
            if name == "tries":
                return failures
            if name == "retries_left":
                left = to_int(cfg.get("retries")) - failures
                return left if left > 0 else 0
            if name == "adjusted":
                return adjusted
            if name.startswith("open:"):
                return open_items(state, name[5:].split(":"))
            value = lookup(data, name) if isinstance(data, dict) else None
            return lookup(state, name) if value is None else value

        message = fill(template, get)
        if message and adjusted and success and "{adjusted}" not in template:
            message = message + " " + fill(cfg.get("adjusted_note", ""), get)
        if message:
            target = data if isinstance(data, dict) else result
            target[cfg.get("next_key", "what_to_do_next")] = message
        state["bb_adjusted__" + tool] = ""
    except Exception as error:
        state["bb_post_error__" + tool] = str(error)
