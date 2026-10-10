"""Helpers shared by every runtime module. Runs inside Freya: see runtime/__init__.py for the rules."""
import json
import re

TOKEN = re.compile(r"\{([A-Za-z0-9_.:]+)\}")


def decode(value):
    """A JSON string that holds an object or a list, decoded; anything else unchanged."""
    if isinstance(value, str):
        text = value.strip()
        if text[:1] in ("[", "{"):
            try:
                return json.loads(text)
            except Exception:
                return value
    return value


def walk(value, parts):
    """Follow `parts` into nested dicts and lists. Returns (found, value)."""
    for part in parts:
        value = decode(value)
        if isinstance(value, dict) and part in value:
            value = value.get(part)
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return False, None
    return True, value


def lookup(state, key):
    """The value of `key` in a variable table: a flat key, a dotted path into nested values, or a mix.

    The engine writes tool results both as flattened keys ('tool_response.data.x') and, for
    lists and objects, in forms that are not documented. The longest flat prefix wins.
    """
    if not isinstance(state, dict) or key is None:
        return None
    key = str(key)
    if key in state:
        return state.get(key)
    parts = key.split(".")
    cut = len(parts) - 1
    while cut > 0:
        head = ".".join(parts[:cut])
        if head in state:
            found, value = walk(state.get(head), parts[cut:])
            if found:
                return value
        cut -= 1
    return None


def is_true(value):
    """True for True and for the strings 'true' / 'True' (booleans arrive as strings)."""
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def is_false(value):
    """True for False and for the strings 'false' / 'False'."""
    return value is False or (isinstance(value, str) and value.strip().lower() == "false")


def is_missing(value):
    """True for None and for an empty or blank string."""
    return value is None or (isinstance(value, str) and value.strip() == "")


def to_float(value):
    """A number from a number or a numeric string; None otherwise. Booleans are not numbers."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except Exception:
        return None


def to_int(value, default=0):
    """An integer from a number or a numeric string; `default` otherwise."""
    number = to_float(value)
    if number is None:
        return default
    try:
        return int(number)
    except Exception:
        return default


def money(value):
    """An amount with two decimals, or the value as text if it is not a number."""
    number = to_float(value)
    if number is None:
        return as_text(value)
    return "%.2f" % number


def as_text(value):
    """Plain text for a value: '' for None, 'true'/'false' for booleans, 3 for 3.0."""
    if value is None:
        return ""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, float):
        try:
            if value == int(value):
                return str(int(value))
        except Exception:
            return str(value)
    return str(value)


def check(value, op, arg=None):
    """One condition on a value. Unknown operators are false.

    true, false, missing, present, equals, not_equals, in, not_in, contains, lt, lte, gt, gte.
    """
    if op == "true":
        return is_true(value)
    if op == "false":
        return is_false(value)
    if op == "missing":
        return is_missing(value)
    if op == "present":
        return not is_missing(value)
    if op in ("equals", "not_equals"):
        same = value is not None and as_text(value) == as_text(arg)
        return same if op == "equals" else not same
    if op in ("in", "not_in"):
        options = [as_text(x) for x in (arg if isinstance(arg, list) else [arg])]
        inside = value is not None and as_text(value) in options
        return inside if op == "in" else not inside
    if op == "contains":
        return value is not None and as_text(arg).lower() in as_text(value).lower()
    if op in ("lt", "lte", "gt", "gte"):
        return compare(to_float(value), op, to_float(arg))
    return False


def compare(left, op, right):
    """Numeric comparison; false when either side is not a number."""
    if left is None or right is None:
        return False
    if op == "lt":
        return left < right
    if op == "lte":
        return left <= right
    if op == "gt":
        return left > right
    return left >= right


def holds(conditions, get):
    """True when every condition holds. A condition is [name, op] or [name, op, arg]."""
    for cond in conditions or []:
        arg = cond[2] if len(cond) > 2 else None
        if not check(get(cond[0]), cond[1], arg):
            return False
    return True


def fill(template, get):
    """Replace each {name} in `template` with get(name) as text ('' when unknown)."""
    def one(match):
        return as_text(get(match.group(1)))
    return TOKEN.sub(one, as_text(template))


def split_csv(text):
    """The non-empty items of a comma-separated string."""
    return [part.strip() for part in as_text(text).split(",") if part.strip()]


def add_csv(text, item):
    """A comma-separated string with `item` appended once."""
    items = split_csv(text)
    if item not in items:
        items.append(item)
    return ",".join(items)


def var_key(text):
    """Text that is safe inside a variable name."""
    return re.sub(r"[^A-Za-z0-9_]", "_", as_text(text))
