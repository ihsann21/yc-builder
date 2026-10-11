"""The words that end a call, chosen in code inside Freya.

Runs inside Freya (see runtime/__init__.py). CFG["parts"] is a list of {"when": [conditions], "say": text};
every part whose conditions hold on the variable table (an empty list always holds) adds its text, in
order. The result goes into CFG["var"] for a fixed spoken line (on_enter say). A model asked to pick the
right sentences at the end of a call skipped the mandatory ones (measured), so the choice is code.
"""
from builder.lib.runtime.common import holds, lookup  # embed: drop


def state_getter(state):
    """A getter for conditions on the variable table."""
    def get(name):
        return lookup(state, name)
    return get


def write_wrap(state, cfg):
    """Join the texts of the parts whose conditions hold."""
    said = []
    for part in cfg.get("parts", []):
        if holds(part.get("when"), state_getter(state)) and part.get("say"):
            said.append(part.get("say"))
    state[cfg.get("var", "bb_wrap")] = " ".join(said)


def run_wrap(state, cfg):
    """Entry point of the wrap code node. Never raises: on failure it writes the fallback text."""
    try:
        write_wrap(state, cfg)
    except Exception as error:
        state[cfg.get("var", "bb_wrap")] = cfg.get("fallback", "")
        state["bb_wrap_error"] = str(error)
