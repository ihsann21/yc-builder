"""Product facts inside Freya: find the account lookup's list of products and spell out each one.

Runs inside Freya (see runtime/__init__.py). Field names, type names, bands and every sentence come
from CFG, which the builder fills from the tool API file and the brief.

Finding the list is the part that broke a previous builder: the engine stores a lookup result
under a mapped variable, under <node>_response.* or <tool>_response.*, as a list, a JSON string or
one flattened key per field. find_items() tries all of them.
"""
from builder.lib.runtime.common import (  # embed: drop
    as_text, decode, fill, lookup, money, to_float, var_key,  # embed: drop
)  # embed: drop

MAX_ITEMS = 100


def as_items(value, list_field):
    """The list of item dicts held by `value` (a list, a JSON string, or an object holding the list)."""
    value = decode(value)
    if isinstance(value, dict):
        inner = decode(value.get("data"))
        holder = inner if isinstance(inner, dict) else value
        value = decode(holder.get(list_field))
    if not isinstance(value, list):
        return []
    items = [decode(x) for x in value]
    return [x for x in items if isinstance(x, dict)]


def flat_items(state, base, cfg):
    """Items stored as one flattened key per field: '<base>.0.<field>', '<base>.1.<field>', ..."""
    items = []
    for index in range(MAX_ITEMS):
        prefix = base + "." + str(index) + "."
        if lookup(state, prefix + cfg["id_field"]) is None:
            break
        item = dict()
        for name in cfg.get("item_fields", []):
            value = lookup(state, prefix + name)
            if value is not None:
                item[name] = value
        items.append(item)
    return items


def scan_items(state, cfg):
    """Last resort: any variable that holds the list, or flattened keys under any name."""
    marker = "." + cfg["list_field"] + ".0." + cfg["id_field"]
    for key in list(state.keys()):
        items = as_items(state.get(key), cfg["list_field"])
        if items and items[0].get(cfg["id_field"]) is not None:
            return items
        if str(key).endswith(marker):
            items = flat_items(state, str(key)[:len(str(key)) - len(".0." + cfg["id_field"])], cfg)
            if items:
                return items
    return []


def find_items(state, cfg):
    """The product list, from the configured sources first, then from anywhere in the table."""
    for key in cfg.get("sources", []):
        items = as_items(lookup(state, key), cfg["list_field"])
        if items:
            return items
    for key in cfg.get("sources", []):
        items = flat_items(state, key, cfg)
        if items:
            return items
    return scan_items(state, cfg)


def pick_band(item, cfg):
    """The first band whose [min, max] holds the item's band field (the days field by default).

    A value outside every band gets the nearest band, so its deadline (and the promise-date guard
    that reads it) never goes blank; None only when the value is not a number.
    """
    value = to_float(item.get(cfg.get("band_field") or cfg["days_field"]))
    if value is None:
        return None
    nearest = None
    distance = None
    for band in cfg.get("bands", []):
        low = band.get("min")
        high = band.get("max")
        if (low is None or value >= low) and (high is None or value <= high):
            return band
        gap = low - value if low is not None and value < low else value - high
        if distance is None or gap < distance:
            nearest = band
            distance = gap
    return nearest


def item_values(item, cfg, state):
    """(values, get): the placeholder values of one item and a getter for templates."""
    ptype = as_text(item.get(cfg["type_field"])) if cfg.get("type_field") else ""
    tcfg = cfg.get("types", dict()).get(ptype) or cfg.get("default_type") or dict()
    band = pick_band(item, cfg) or dict()
    deadline = band.get("deadline")
    floor = item.get(tcfg.get("floor_field")) if tcfg.get("floor_field") else None
    full = item.get(cfg["amount_field"])
    values = dict()
    values["id"] = as_text(item.get(cfg["id_field"]))
    values["type"] = ptype
    values["type_words"] = ptype.replace("_", " ")
    values["full"] = "" if full is None else money(full)
    values["floor"] = "" if floor is None else money(floor)
    values["floor_label"] = tcfg.get("floor_label", "")
    values["days"] = as_text(item.get(cfg["days_field"]))
    values["band"] = band.get("name", "")
    values["deadline"] = as_text(lookup(state, "bb_date__" + deadline)) if deadline else ""
    values["deadline_spoken"] = as_text(lookup(state, "bb_date__" + deadline + "__spoken")) if deadline else ""
    values["deadline_shifts"] = as_text(lookup(state, "bb_shifts__" + deadline)) if deadline else ""
    values["attempts"] = as_text(band.get("attempts"))

    def get(name):
        if name in values:
            return values.get(name)
        if name.startswith("field:"):
            return item.get(name[6:])
        if name.startswith("date:"):
            return lookup(state, "bb_date__" + name[5:])
        if name.startswith("date_spoken:"):
            return lookup(state, "bb_date__" + name[12:] + "__spoken")
        if name.startswith("shifts:"):
            return lookup(state, "bb_shifts__" + name[7:])
        return None

    values["name"] = fill(tcfg.get("name", "{type_words}"), get)
    values["offers"] = fill(band.get("offers", ""), get)
    values["floor_raw"] = floor
    return values, get


def write_products(state, cfg):
    """Find the products, write per-product variables and the facts text."""
    ids = []
    lines = []
    for item in find_items(state, cfg):
        values, get = item_values(item, cfg, state)
        key = var_key(values["id"])
        ids.append(values["id"])
        state["bb_full__" + key] = item.get(cfg["amount_field"], "")
        state["bb_floor__" + key] = "" if values["floor_raw"] is None else values["floor_raw"]
        state["bb_days__" + key] = item.get(cfg["days_field"], "")
        state["bb_band__" + key] = values["band"]
        state["bb_deadline__" + key] = values["deadline"]
        state["bb_type__" + key] = values["type"]
        state["bb_name__" + key] = values["name"]
        lines.append(fill(cfg.get("line", ""), get))
    state["bb_products"] = ",".join(ids)
    state["bb_product_count"] = len(ids)
    state["bb_single_product"] = ids[0] if len(ids) == 1 else ""
    facts_var = cfg.get("facts_var", "account_facts")
    if not ids:
        state[facts_var] = cfg.get("empty", "")
        state["bb_account_state"] = "empty"
        return

    def count(name):
        return len(ids) if name == "count" else None

    header = fill(cfg.get("header", ""), count)
    state[facts_var] = (header + "\n" if header else "") + "\n".join(lines)
    state["bb_account_state"] = "ok"


def run_products(state, cfg):
    """Entry point of the product code node. Never raises: on failure it writes the fallback text."""
    try:
        write_products(state, cfg)
    except Exception as error:
        state[cfg.get("facts_var", "account_facts")] = cfg.get("fallback", "")
        state["bb_account_state"] = "error"
        state["bb_account_error"] = str(error)
