"""Workflow helpers (conditions, transitions, nodes) and a static check of a whole workflow.

Every helper returns a new dict and deep-copies what it embeds, so the caller's objects are never
shared with the workflow. No helper writes None: an optional key is left out instead.
The shapes follow the kit's docs/workflow-format.md and docs/tools-and-code.md.
"""
from __future__ import annotations

import copy
import re
import warnings
from typing import Iterator

OPERAND_OPERATORS = ("equals", "not_equals", "greater_than", "less_than", "contains")
PRESENCE_OPERATORS = ("is_set", "is_not_set")
EXTRACTION_TYPES = ("string", "integer", "float", "boolean", "date", "datetime", "name", "phone_number")
END_MESSAGE_MODES = ("none", "custom")
LIFECYCLES = ("start_of_call", "end_of_call")
API_CALL = "__function__:api_call"
CODE_EXEC = "__function__:code_exec"
END_CALL = "__function__:end_call"
PREVIOUS = "__previous__"
HOOKS = ("pre_process_code", "post_process_code")


# ---------------------------------------------------------------- conditions


def always() -> dict:
    """The unconditional condition."""
    return {"operator": "always"}


def when_equals(var: str, *values: str) -> dict:
    """True when `var` equals any of `values`; the platform compares as strings."""
    if not values or any(value is None for value in values):
        raise ValueError("when_equals needs at least one value and no None")
    return _or_group([{"variable": var, "operator": "equals", "operand": value} for value in values])


def when_true(var: str) -> dict:
    """True when `var` holds a true boolean, which arrives as "true" or as "True"."""
    return when_equals(var, "true", "True")


def when(var: str, op: str, operand: str | int | float | None = None) -> dict:
    """One deterministic condition in its own OR group. is_set and is_not_set take no operand."""
    if op in PRESENCE_OPERATORS:
        if operand is not None:
            raise ValueError(f"{op} takes no operand")
        return _or_group([{"variable": var, "operator": op}])
    if op in OPERAND_OPERATORS:
        if operand is None:
            raise ValueError(f"{op} needs an operand")
        return _or_group([{"variable": var, "operator": op, "operand": operand}])
    raise ValueError(f"unknown operator {op!r}; use one of {', '.join(OPERAND_OPERATORS + PRESENCE_OPERATORS)}")


def any_of(*groups: dict) -> dict:
    """One OR group holding the conditions of every given OR group."""
    if not groups:
        raise ValueError("any_of needs at least one group")
    conditions = [condition for group in groups for condition in _group_conditions(group, "any_of")]
    return _or_group(copy.deepcopy(conditions))


def all_of(*groups: dict) -> dict:
    """AND of single-condition groups, nested inside the top-level OR group the platform needs."""
    if not groups:
        raise ValueError("all_of needs at least one group")
    inner = []
    for group in groups:
        conditions = _group_conditions(group, "all_of")
        if len(conditions) != 1:
            raise ValueError("all_of takes groups with exactly one condition each")
        inner.append(conditions[0])
    return _or_group([{"logic": "and", "conditions": copy.deepcopy(inner)}])


def intent(description: str) -> dict:
    """A condition the routing model judges against the person's last message."""
    return {"operator": "matches_intent", "description": description}


def transition(target: str, description: str, condition: dict, tool_call: bool = False) -> dict:
    """A transition to `target`. With tool_call the dialogue model triggers it by calling a tool."""
    if not isinstance(target, str) or not target:
        raise ValueError(f"a transition needs a target node name, not {target!r}")
    condition = _copied_dict(condition, "condition")
    result: dict = {"target_node": target, "description": description, "condition": condition}
    if tool_call:
        result["is_tool_call"] = True
    return result


def _or_group(conditions: list) -> dict:
    return {"logic": "or", "conditions": conditions}


def _group_conditions(group: object, helper: str) -> list:
    if not (isinstance(group, dict) and group.get("logic") == "or" and isinstance(group.get("conditions"), list)):
        raise ValueError(f"{helper} takes OR groups such as when() returns, not {group!r}")
    return group["conditions"]


# ---------------------------------------------------------------- on_enter and extraction


def say(text: str) -> dict:
    """on_enter: speak a fixed line ({{var}} works in it)."""
    return {"type": "tts", "text": text}


def llm(prompt: str = "") -> dict:
    """on_enter: the model writes the first line, from `prompt` when given."""
    return {"type": "llm", "prompt": prompt} if prompt else {"type": "llm"}


def silent() -> dict:
    """on_enter: say nothing."""
    return {"type": "silent"}


def extract(
    name: str,
    type: str,
    description: str,
    *,
    enum: list[str] | None = None,
    min_confidence: float = 0.7,
    pattern: str = "",
) -> dict:
    """One extraction_schema entry. min_confidence is always written (the platform default drops values)."""
    if type not in EXTRACTION_TYPES:
        raise ValueError(f"unknown extraction type {type!r}; use one of {', '.join(EXTRACTION_TYPES)}")
    if not 0.0 <= min_confidence <= 1.0:
        raise ValueError(f"min_confidence must be between 0 and 1, not {min_confidence}")
    entry: dict = {"name": name, "type": type, "description": description}
    if enum:
        entry["enum_values"] = list(enum)
    if pattern:
        entry["validation_pattern"] = pattern
    entry["min_confidence"] = min_confidence
    return entry


# ---------------------------------------------------------------- nodes


def code_node(name: str, code: str, next_node: str, timeout_ms: int = 10000) -> dict:
    """A passthrough code node that runs `code` on entry and goes on to `next_node`."""
    snippet = {
        "type": "function",
        "function": {
            "name": "code_exec",
            "handler": CODE_EXEC,
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "default": code},
                    "timeout_ms": {"type": "number", "default": timeout_ms},
                },
            },
        },
    }
    return {**_passthrough("code", name, next_node), "pre_actions": [snippet], "transitions": [_onward(next_node)]}


def api_request_node(
    name: str,
    tool: dict,
    next_node: str,
    *,
    mapping: list[tuple[str, str]] | None = None,
    transitions: list[dict] | None = None,
) -> dict:
    """A passthrough api_request node running `tool` on entry.

    mapping becomes the node-level response_mapping (paths start with 'data.'). Extra transitions
    come first; the last one is always the unconditional transition to `next_node`.
    """
    tool = _copied_dict(tool, "tool")
    if "response_mapping" in tool:
        raise ValueError("a response_mapping inside a pre_actions entry is ignored; pass mapping= to the node")
    node = {**_passthrough("api_request", name, next_node), "pre_actions": [tool]}
    if mapping:
        node["response_mapping"] = _mapping_entries(mapping)
    node["transitions"] = [*copy.deepcopy(transitions or []), _onward(next_node)]
    return node


def conversation_node(
    name: str,
    *,
    task: str,
    tools: list[dict],
    transitions: list[dict],
    on_enter: dict,
    extraction: list[dict] | None = None,
    max_turns: int = 0,
    max_turn_transition: str = "",
    first_entry_only: bool = True,
    routing_prompt: str = "",
    loop_prompt: str = "",
) -> dict:
    """A conversation node. Optional settings are written only when given."""
    node = {
        "name": name,
        "node_type": "conversation",
        "task_message": task,
        "tools": copy.deepcopy(tools),
        "on_enter": _copied_dict(on_enter, "on_enter"),
        "on_enter_first_entry_only": first_entry_only,
        "transitions": copy.deepcopy(transitions),
    }
    if max_turns:
        node["max_node_turns"] = max_turns
    if max_turn_transition:
        node["max_turn_transition"] = max_turn_transition
    if extraction:
        node["extraction_schema"] = copy.deepcopy(extraction)
    if routing_prompt:
        node["routing_prompt"] = routing_prompt
    if loop_prompt:
        node["loop_prompt"] = loop_prompt
    return node


def end_call_node(name: str, function_name: str, *, message_mode: str = "none", spoken_message: str = "") -> dict:
    """An end_call node. function_name becomes the call's endedReason.

    message_mode none hangs up silently; custom says spoken_message, which it then requires.
    """
    if message_mode not in END_MESSAGE_MODES:
        raise ValueError(f"message_mode must be one of {', '.join(END_MESSAGE_MODES)}, not {message_mode!r}")
    if (message_mode == "custom") != bool(spoken_message):
        raise ValueError("spoken_message is needed with message_mode custom and is never said with none")
    properties = {"message_mode": {"type": "string", "default": message_mode}}
    if spoken_message:
        properties["spoken_message"] = {"type": "string", "default": spoken_message}
    return {
        "name": name,
        "node_type": "end_call",
        "on_enter": silent(),
        "disable_inactivity_monitor": True,
        "transitions": [],
        "terminal": {
            "type": "function",
            "function": {
                "name": function_name,
                "handler": END_CALL,
                "parameters": {"type": "object", "properties": properties},
            },
        },
    }


def workflow(
    *,
    initial: str,
    nodes: dict,
    system_prompt: str = "",
    tools: list[dict] | None = None,
    global_nodes: dict | None = None,
    test_variables: dict | None = None,
) -> dict:
    """The workflow object. Never writes agent_config or context_variables."""
    result: dict = {"initial_node": initial}
    if system_prompt:
        result["system_prompt"] = system_prompt
    result["nodes"] = copy.deepcopy(nodes)
    result["global_nodes"] = copy.deepcopy(global_nodes or {})
    if tools:
        result["tools"] = copy.deepcopy(tools)
    if test_variables:
        result["test_variables"] = copy.deepcopy(test_variables)
    return result


def _passthrough(node_type: str, name: str, next_node: str) -> dict:
    return {
        "name": name,
        "node_type": node_type,
        "passthrough": True,
        "passthrough_default_transition": next_node,
        "on_enter": silent(),
        "disable_inactivity_monitor": True,
    }


def _onward(next_node: str) -> dict:
    return transition(next_node, "always", always())


def _copied_dict(value: object, what: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{what} must be a dict, not {value!r}")
    return copy.deepcopy(value)


def _mapping_entries(mapping: list[tuple[str, str]]) -> list[dict]:
    entries = []
    for path, variable in mapping:
        if not isinstance(path, str) or not path.startswith("data."):
            raise ValueError(f"response_mapping path {path!r} must start with 'data.'")
        if not isinstance(variable, str) or not variable:
            raise ValueError(f"response_mapping for {path} needs a variable name, not {variable!r}")
        entries.append({"path": path, "variable": variable})
    return entries


# ---------------------------------------------------------------- check

NODE_TYPES = (
    "conversation",
    "api_request",
    "code",
    "end_call",
    "transfer_call",
    "integration",
    "knowledge_base",
    "reschedule_call",
    "invoke_agent",
    "exit",
)
TOP_LEVEL_KEYS = ("initial_node", "nodes", "system_prompt", "global_nodes", "test_variables", "tools", "nodePositions")
DROPPED_TOP_LEVEL = {
    "agent_config": "agent_config must be left out (the platform fills it in; a sent one can stop calls from starting)",
    "context_variables": "context_variables must be left out (the platform drops it on save)",
}
TOP_LEVEL_SHAPES = (
    ("global_nodes", dict, "an object"),
    ("test_variables", dict, "an object"),
    ("tools", list, "a list"),
)
NODE_LISTS = ("tools", "pre_actions", "transitions", "extraction_schema", "response_mapping")
WARNING = "warning: "
_PLACEHOLDER = re.compile(r"^\{\{\s*([^{}:\s]+)(?::json)?\s*\}\}$")


def check(wf: dict, call_variables: tuple[str, ...] = (), known_vars: tuple[str, ...] = ()) -> list[str]:
    """Problems that make the platform reject or silently mangle `wf`; an empty list means none.

    Non-fatal findings start with "warning: " and come after the problems. Never raises, never
    changes `wf`.
    call_variables: the variables tool defaults bake on purpose: the call variables, plus any other
        variable a tool default is meant to take (its {{x}} default then never warns).
    known_vars: other variables known to be set before the tools run (for example by code); a
        model-filled default with such a name warns, because the value would be baked.
    """
    if not isinstance(wf, dict):
        return ["the workflow is not a JSON object"]
    nodes = wf["nodes"] if isinstance(wf.get("nodes"), dict) else {}
    global_nodes = wf["global_nodes"] if isinstance(wf.get("global_nodes"), dict) else {}
    problems = _null_paths(wf, "") + _top_level_problems(wf, nodes)
    for key, node, is_global in _every_node(nodes, global_nodes):
        problems += _node_problems(key, node, nodes, global_nodes, is_global)
    for label, tool, place in _every_tool(wf, nodes, global_nodes):
        problems += _tool_problems(label, tool, place)
    problems += _reach_warnings(wf, nodes, global_nodes)
    problems += _placeholder_warnings(wf, nodes, global_nodes, call_variables, known_vars)
    problems += _extraction_warnings(nodes, global_nodes)
    return sorted(problems, key=lambda problem: problem.startswith(WARNING))


def _null_paths(value: object, path: str) -> list[str]:
    if value is None:
        return [f"null value at {path or 'the top level'}"]
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in _null_paths(v, f"{path}.{k}" if path else str(k))]
    if isinstance(value, list):
        return [p for i, v in enumerate(value) for p in _null_paths(v, f"{path}[{i}]")]
    return []


def _top_level_problems(wf: dict, nodes: dict) -> list[str]:
    problems = []
    for key in wf:
        if key in DROPPED_TOP_LEVEL:
            problems.append(DROPPED_TOP_LEVEL[key])
        elif key not in TOP_LEVEL_KEYS:
            problems.append(f"unknown top-level key {key!r}")
    if not isinstance(wf.get("nodes"), dict):
        problems.append("nodes is missing or not an object")
    for key, kind, word in TOP_LEVEL_SHAPES:
        if key in wf and not isinstance(wf[key], kind):
            problems.append(f"{key} must be {word}")
    if isinstance(wf.get("tools"), list):
        problems += [f"tools[{i}] is not an object" for i, tool in enumerate(wf["tools"]) if not isinstance(tool, dict)]
    initial = wf.get("initial_node")
    if not initial:
        problems.append("initial_node is missing")
    elif not isinstance(initial, str) or initial not in nodes:
        problems.append(f"initial_node {initial!r} is not a node")
    return problems


def _every_node(nodes: dict, global_nodes: dict) -> Iterator[tuple[str, object, bool]]:
    for key, node in nodes.items():
        yield str(key), node, False
    for key, node in global_nodes.items():
        yield str(key), node, True


def _dict_nodes(nodes: dict, global_nodes: dict) -> Iterator[tuple[str, dict, bool]]:
    for key, node, is_global in _every_node(nodes, global_nodes):
        if isinstance(node, dict):
            yield key, node, is_global


def _where(key: str, is_global: bool) -> str:
    return f"global node {key!r}" if is_global else f"node {key!r}"


def _node_problems(key: str, node: object, nodes: dict, global_nodes: dict, is_global: bool) -> list[str]:
    where = _where(key, is_global)
    if not isinstance(node, dict):
        return [f"{where} is not an object"]
    problems = []
    if node.get("name") != key:
        problems.append(f"{where}: name {node.get('name')!r} must equal its key")
    node_type = node.get("node_type", "conversation" if is_global else None)
    if node_type is None:
        problems.append(f"{where}: node_type is missing")
    elif node_type not in NODE_TYPES:
        problems.append(f"{where}: unknown node_type {node_type!r}")
    for list_key in NODE_LISTS:
        problems += _list_shape_problems(where, node, list_key)
    if node_type in NODE_TYPES:
        problems += _placement_problems(where, node, node_type)
    problems += _passthrough_problems(where, node)
    problems += _target_problems(where, node, nodes, global_nodes, is_global)
    problems += _and_group_problems(where, node, is_global)
    if node_type == "end_call":
        problems += _end_call_problems(where, node)
    if isinstance(node.get("response_mapping"), list):
        problems += _mapping_problems(where, node["response_mapping"])
    return problems


def _list_shape_problems(where: str, node: dict, key: str) -> list[str]:
    value = node.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        return [f"{where}: {key} must be a list"]
    return [f"{where}: {key}[{i}] is not an object" for i, item in enumerate(value) if not isinstance(item, dict)]


def _placement_problems(where: str, node: dict, node_type: str) -> list[str]:
    problems = []
    if node_type != "conversation" and _list(node.get("tools")):
        problems.append(
            f"{where}: tools on a {node_type} node are stripped by the platform (only conversation nodes keep them)"
        )
    if node_type == "conversation" and _list(node.get("pre_actions")):
        problems.append(
            f"{where}: pre_actions on a conversation node are stripped by the platform "
            "(run the call in an api_request node in front)"
        )
    return problems


def _passthrough_problems(where: str, node: dict) -> list[str]:
    if node.get("passthrough") is not True:
        return []
    problems = []
    if not node.get("passthrough_default_transition"):
        problems.append(f"{where}: passthrough node without passthrough_default_transition")
    transitions = _list(node.get("transitions"))
    last = transitions[-1] if transitions else None
    if not (isinstance(last, dict) and _is_always(last.get("condition"))):
        problems.append(f"{where}: a passthrough node must end with an always transition (it deadlocks otherwise)")
    return problems


def _target_problems(where: str, node: dict, nodes: dict, global_nodes: dict, is_global: bool) -> list[str]:
    transitions = [t for t in _list(node.get("transitions")) if isinstance(t, dict)]
    targets = [("transition target", t.get("target_node")) for t in transitions]
    targets += [(key, node[key]) for key in ("passthrough_default_transition", "max_turn_transition") if node.get(key)]
    return [
        problem
        for what, target in targets
        for problem in _target_problem(where, what, target, nodes, global_nodes, is_global)
    ]


def _target_problem(
    where: str, what: str, target: object, nodes: dict, global_nodes: dict, is_global: bool
) -> list[str]:
    if target == PREVIOUS:
        return [] if is_global else [f"{where}: {what} {PREVIOUS} is allowed only in global nodes"]
    if isinstance(target, str) and target in nodes:
        return []
    hint = " (it is a global node)" if isinstance(target, str) and target in global_nodes else ""
    return [f"{where}: {what} {target!r} is not a node{hint}"]


def _and_group_problems(where: str, node: dict, is_global: bool) -> list[str]:
    problems = [
        f"{where}: the transition to {item.get('target_node')!r} has logic 'and' at the top level; "
        "nest it in an 'or' group"
        for item in _list(node.get("transitions"))
        if isinstance(item, dict) and _is_and_group(item.get("condition"))
    ]
    if is_global and _is_and_group(node.get("condition")):
        problems.append(f"{where}: its condition has logic 'and' at the top level; nest it in an 'or' group")
    return problems


def _end_call_problems(where: str, node: dict) -> list[str]:
    problems = []
    if not isinstance(node.get("terminal"), dict):
        problems.append(f"{where}: end_call node without terminal")
    if node.get("transitions"):
        problems.append(f"{where}: an end_call node must have no transitions")
    return problems


def _every_tool(wf: dict, nodes: dict, global_nodes: dict) -> Iterator[tuple[str, dict, str]]:
    """(label, tool, place) for every tool object; place is tools, pre_actions or workflow."""
    for key, node, is_global in _dict_nodes(nodes, global_nodes):
        for place, word in (("tools", "tool"), ("pre_actions", "pre_action")):
            for i, tool in enumerate(_list(node.get(place))):
                if isinstance(tool, dict):
                    yield f"{_where(key, is_global)} {word} {_tool_name(tool, i)!r}", tool, place
    for i, tool in enumerate(_list(wf.get("tools"))):
        if isinstance(tool, dict):
            yield f"workflow tool {_tool_name(tool, i)!r}", tool, "workflow"


def _tool_problems(label: str, tool: dict, place: str) -> list[str]:
    problems = []
    raw_function = tool.get("function")
    function = raw_function if isinstance(raw_function, dict) else {}
    handler = function.get("handler")
    for hook in HOOKS:
        code = tool.get(hook)
        if code is None or (isinstance(code, str) and not code.strip()):
            continue
        if handler != API_CALL:
            problems.append(f"{label}: {hook} is stripped from a {handler!r} tool (only {API_CALL} keeps hooks)")
        problems += _code_problems(f"{label} {hook}", code)
    code = _default(function, "code")
    if handler == CODE_EXEC and code is not None:
        problems += _code_problems(f"{label} code", code)
    if place == "pre_actions" and "response_mapping" in tool:
        problems.append(f"{label}: a response_mapping inside a pre_actions entry is ignored; put it on the node")
    elif isinstance(tool.get("response_mapping"), list):
        problems += _mapping_problems(label, tool["response_mapping"])
    elif "response_mapping" in tool:
        problems.append(f"{label}: response_mapping must be a list")
    return problems + _lifecycle_problems(label, tool, place)


def _lifecycle_problems(label: str, tool: dict, place: str) -> list[str]:
    raw = _get(tool, "config", "alwaysRunsAt")
    if raw is not None and not isinstance(raw, list):
        return [f"{label}: config.alwaysRunsAt must be a list"]
    runs_at = _list(raw)
    problems = []
    for value in runs_at:
        if value == "each_turn":
            problems.append(f"{label}: alwaysRunsAt each_turn is accepted by the platform but never fires")
        elif value not in LIFECYCLES:
            problems.append(f"{label}: alwaysRunsAt value {value!r} is not one of {', '.join(LIFECYCLES)}")
    if place == "workflow" and not runs_at:
        problems.append(f"{label}: a workflow-level tool without config.alwaysRunsAt never runs")
    if "end_of_call" in runs_at and "start_of_call" not in runs_at and _list(tool.get("response_mapping")):
        problems.append(f"{WARNING}{label}: response_mapping is not applied to an end_of_call tool")
    return problems


def _code_problems(label: str, code: object) -> list[str]:
    """No double braces, and the snippet compiles."""
    if not isinstance(code, str):
        return [f"{label}: code is not a string"]
    problems = []
    if "{{" in code or "}}" in code:
        problems.append(f"{label}: contains '{{{{' or '}}}}' (the platform may template it); read values from vars")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            compile(code, label, "exec")
    except (SyntaxError, ValueError) as exc:
        lineno = getattr(exc, "lineno", None)
        line = f" (line {lineno})" if lineno else ""
        problems.append(f"{label}: does not compile: {getattr(exc, 'msg', None) or exc}{line}")
    return problems


def _mapping_problems(label: str, mapping: list) -> list[str]:
    problems = []
    for i, raw in enumerate(mapping):
        entry = raw if isinstance(raw, dict) else {}
        path, variable = entry.get("path"), entry.get("variable")
        if not (isinstance(path, str) and path.startswith("data.")):
            problems.append(f"{label}: response_mapping path {path!r} must start with 'data.'")
        if not (isinstance(variable, str) and variable):
            problems.append(f"{label}: response_mapping[{i}] has no variable")
    return problems


def _reach_warnings(wf: dict, nodes: dict, global_nodes: dict) -> list[str]:
    initial = wf.get("initial_node")
    if not isinstance(initial, str) or initial not in nodes:
        return []
    reached = _reachable(initial, nodes, global_nodes)
    found = [
        f"{WARNING}node {key!r} is not reachable from initial_node {initial!r}" for key in nodes if key not in reached
    ]
    if not _can_end([nodes[key] for key in reached] + list(global_nodes.values())):
        found.append(
            f"{WARNING}no end_call node is reachable and no reachable node offers an end_call tool: "
            "nothing ends the call"
        )
    return found


def _reachable(initial: str, nodes: dict, global_nodes: dict) -> set[str]:
    """Nodes reachable from initial_node; a global node can fire anywhere, so its targets count too."""
    todo = [initial] + [target for node in global_nodes.values() for target in _targets(node)]
    seen: set[str] = set()
    while todo:
        key = todo.pop()
        if key in seen or key not in nodes:
            continue
        seen.add(key)
        todo.extend(_targets(nodes[key]))
    return seen


def _targets(node: object) -> list[str]:
    if not isinstance(node, dict):
        return []
    targets = [t.get("target_node") for t in _list(node.get("transitions")) if isinstance(t, dict)]
    targets += [node.get("passthrough_default_transition"), node.get("max_turn_transition")]
    return [target for target in targets if isinstance(target, str)]


def _can_end(live_nodes: list) -> bool:
    """An end_call node, or a tool with the end_call handler. A lifecycle tool ends nothing."""
    for node in live_nodes:
        if not isinstance(node, dict):
            continue
        if node.get("node_type") == "end_call":
            return True
        if any(isinstance(tool, dict) and _handler(tool) == END_CALL for tool in _list(node.get("tools"))):
            return True
    return False


def _placeholder_warnings(
    wf: dict, nodes: dict, global_nodes: dict, call_variables: tuple[str, ...], known_vars: tuple[str, ...]
) -> list[str]:
    """A model-filled body field whose variable is set elsewhere gets baked: the model never sees it."""
    sources = _variable_sources(wf, nodes, global_nodes, known_vars)
    found = []
    for label, tool, place in _every_tool(wf, nodes, global_nodes):
        if place == "pre_actions" or _handler(tool) != API_CALL:
            continue
        for field_name, var in _model_filled(tool):
            if var in sources and var not in call_variables:
                found.append(
                    f"{WARNING}{label}: body field {field_name!r} defaults to {{{{{var}}}}}, "
                    f"but {var!r} is also set by {', '.join(sources[var])}; "
                    "the value would be baked and the model never sees the field"
                )
    return found


def _variable_sources(wf: dict, nodes: dict, global_nodes: dict, known_vars: tuple[str, ...]) -> dict[str, list[str]]:
    pairs: list[tuple[str, str]] = []
    for key, node, is_global in _dict_nodes(nodes, global_nodes):
        where = _where(key, is_global)
        pairs += [(name, f"the extraction of {where}") for name in _names(node.get("extraction_schema"), "name")]
        mapped = _names(node.get("response_mapping"), "variable")
        pairs += [(name, f"the response_mapping of {where}") for name in mapped]
    for label, tool, place in _every_tool(wf, nodes, global_nodes):
        if place != "pre_actions":  # a mapping there is ignored, so it sets nothing
            mapped = _names(tool.get("response_mapping"), "variable")
            pairs += [(name, f"the response_mapping of {label}") for name in mapped]
    test_variables = wf.get("test_variables")
    pairs += [(str(name), "test_variables") for name in (test_variables if isinstance(test_variables, dict) else {})]
    pairs += [(name, "known_vars") for name in known_vars]
    sources: dict[str, list[str]] = {}
    for name, source in pairs:
        sources.setdefault(name, []).append(source)
    return sources


def _model_filled(tool: dict) -> list[tuple[str, str]]:
    """(field, variable) for each body leaf whose default is exactly one {{variable}} placeholder."""
    leaves = _get(tool, "function", "parameters", "properties", "body", "properties")
    found = []
    for name, leaf in leaves.items() if isinstance(leaves, dict) else ():
        default = leaf.get("default") if isinstance(leaf, dict) else None
        match = _PLACEHOLDER.match(default) if isinstance(default, str) else None
        if match:
            found.append((str(name), match.group(1)))
    return found


def _extraction_warnings(nodes: dict, global_nodes: dict) -> list[str]:
    return [
        f"{WARNING}{_where(key, is_global)}: extraction {entry.get('name')!r} has no min_confidence "
        "(the default 0.95 drops values silently)"
        for key, node, is_global in _dict_nodes(nodes, global_nodes)
        for entry in _list(node.get("extraction_schema"))
        if isinstance(entry, dict) and "min_confidence" not in entry
    ]


def _list(value: object) -> list:
    return value if isinstance(value, list) else []


def _names(entries: object, key: str) -> list[str]:
    return [e[key] for e in _list(entries) if isinstance(e, dict) and isinstance(e.get(key), str)]


def _get(value: object, *keys: str) -> object:
    for key in keys:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def _default(function: dict, name: str) -> object:
    return _get(function, "parameters", "properties", name, "default")


def _handler(tool: dict) -> object:
    return _get(tool, "function", "handler")


def _tool_name(tool: dict, index: int) -> str:
    name = _get(tool, "function", "name")
    return name if isinstance(name, str) else f"#{index}"


def _is_always(condition: object) -> bool:
    return isinstance(condition, dict) and condition.get("operator") == "always"


def _is_and_group(condition: object) -> bool:
    return isinstance(condition, dict) and condition.get("logic") == "and"
