"""A list from an earlier tool result, written as plain lines for a prompt.

Runs inside Freya (see runtime/__init__.py). The engine does not store a list or object under a
response_mapping variable (measured: a mapped list stayed unset while a mapped number arrived); it
keeps the result as flattened keys ('<node>_response.data.<list>.0.<field>'). find_items() reads every
form, and this module writes one line per item, 'field: value; field: value', with no braces.
"""
from builder.lib.runtime.common import as_text  # embed: drop
from builder.lib.runtime.products import find_items  # embed: drop


def item_line(index, item, fields):
    """'N. field: value; field: value' for the configured fields that the item has."""
    parts = []
    for name in fields:
        if name in item:
            parts.append(name + ": " + as_text(item.get(name)))
    return str(index) + ". " + "; ".join(parts)


def run_list(state, cfg):
    """Entry point of the list code node. Never raises: on failure it writes the empty text."""
    var = cfg.get("var", "bb_list")
    try:
        items = find_items(state, cfg)
        lines = [item_line(i + 1, items[i], cfg.get("item_fields", [])) for i in range(len(items))]
        state[var] = "\n".join(lines) if lines else cfg.get("empty", "")
        state[var + "_count"] = len(items)
    except Exception as error:
        state[var] = cfg.get("empty", "")
        state[var + "_count"] = 0
        state["bb_list_error"] = str(error)
