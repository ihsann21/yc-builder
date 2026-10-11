"""Tests for builder.lib.workflow: node, transition and condition helpers, and the static check.

Practice values appear here on purpose: tests are not builder code.
"""
import copy
import json

import pytest

from builder.lib.tools import api_tool, end_call_tool, operations
from builder.lib.workflow import (
    all_of,
    always,
    any_of,
    api_request_node,
    check,
    code_node,
    conversation_node,
    end_call_node,
    extract,
    intent,
    llm,
    say,
    silent,
    transition,
    when,
    when_equals,
    when_true,
    workflow,
)

CALL_VARS = ("customer_id", "first_name", "last_name", "title", "now")


def _load(kit, relative: str) -> dict:
    return json.loads((kit / relative).read_text(encoding="utf-8"))


@pytest.fixture
def brief_a(kit) -> dict:
    return _load(kit, "out/brief-a.workflow.json")


# ---------------------------------------------------------------- conditions


def test_always_and_intent():
    assert always() == {"operator": "always"}
    assert intent("They want to stop") == {"operator": "matches_intent", "description": "They want to stop"}


def test_when_equals_builds_one_or_group():
    assert when_equals("person", "customer") == {
        "logic": "or",
        "conditions": [{"variable": "person", "operator": "equals", "operand": "customer"}],
    }
    assert [c["operand"] for c in when_equals("x", "a", "b")["conditions"]] == ["a", "b"]


@pytest.mark.parametrize("values", [(), ("a", None)])
def test_when_equals_needs_real_values(values):
    with pytest.raises(ValueError):
        when_equals("x", *values)


def test_when_true_tests_both_spellings():
    assert when_true("flag") == {
        "logic": "or",
        "conditions": [
            {"variable": "flag", "operator": "equals", "operand": "true"},
            {"variable": "flag", "operator": "equals", "operand": "True"},
        ],
    }


@pytest.mark.parametrize("op", ["equals", "not_equals", "greater_than", "less_than", "contains"])
def test_when_with_an_operand(op):
    assert when("n", op, 2) == {"logic": "or", "conditions": [{"variable": "n", "operator": op, "operand": 2}]}


@pytest.mark.parametrize("op", ["is_set", "is_not_set"])
def test_when_without_an_operand(op):
    assert when("n", op) == {"logic": "or", "conditions": [{"variable": "n", "operator": op}]}


@pytest.mark.parametrize(
    "args", [("n", "is_set", "x"), ("n", "equals"), ("n", "matches"), ("n", "always"), ("n", "matches_intent", "x")]
)
def test_when_rejects_bad_operators_and_operands(args):
    with pytest.raises(ValueError):
        when(*args)


def test_any_of_flattens_groups():
    assert any_of(when_true("a"), when("b", "is_set")) == {
        "logic": "or",
        "conditions": [
            {"variable": "a", "operator": "equals", "operand": "true"},
            {"variable": "a", "operator": "equals", "operand": "True"},
            {"variable": "b", "operator": "is_set"},
        ],
    }


def test_all_of_nests_an_and_group_inside_the_or_group():
    assert all_of(when("a", "is_set"), when("b", "equals", "x")) == {
        "logic": "or",
        "conditions": [
            {
                "logic": "and",
                "conditions": [
                    {"variable": "a", "operator": "is_set"},
                    {"variable": "b", "operator": "equals", "operand": "x"},
                ],
            }
        ],
    }


@pytest.mark.parametrize("bad", [always(), intent("x"), when_true("a"), {"logic": "and", "conditions": []}])
def test_all_of_takes_only_single_condition_groups(bad):
    with pytest.raises(ValueError):
        all_of(when("b", "is_set"), bad)


@pytest.mark.parametrize("bad", [always(), intent("x"), {"logic": "and", "conditions": []}])
def test_any_of_takes_only_or_groups(bad):
    with pytest.raises(ValueError):
        any_of(when("b", "is_set"), bad)


def test_group_helpers_need_arguments():
    with pytest.raises(ValueError):
        any_of()
    with pytest.raises(ValueError):
        all_of()


def test_group_helpers_copy_their_inputs():
    inner = when("a", "is_set")
    for merged in (any_of(inner), all_of(inner)):
        merged["conditions"][0]["variable"] = "changed"
    assert inner == when("a", "is_set")


def test_transition_shapes():
    assert transition("next", "always", always()) == {
        "target_node": "next",
        "description": "always",
        "condition": {"operator": "always"},
    }
    assert transition("next", "d", intent("x"), tool_call=True)["is_tool_call"] is True
    assert "is_tool_call" not in transition("next", "d", always())
    with pytest.raises(ValueError):
        transition("next", "d", None)  # type: ignore[arg-type]
    for target in (None, ""):
        with pytest.raises(ValueError):
            transition(target, "d", always())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        code_node("setup", "x = 1\n", None)  # type: ignore[arg-type]


def test_transition_copies_its_condition():
    condition = when("a", "is_set")
    transition("next", "d", condition)["condition"]["conditions"].clear()
    assert condition == when("a", "is_set")


# ---------------------------------------------------------------- on_enter and extraction


def test_on_enter_shapes():
    assert say("Hello {{first_name}}.") == {"type": "tts", "text": "Hello {{first_name}}."}
    assert llm() == {"type": "llm"}
    assert llm("Greet them.") == {"type": "llm", "prompt": "Greet them."}
    assert silent() == {"type": "silent"}


def test_extract_shapes():
    assert extract("day", "date", "The day they want.") == {
        "name": "day",
        "type": "date",
        "description": "The day they want.",
        "min_confidence": 0.7,
    }
    assert extract("choice", "string", "What they chose.", enum=["a", "b"], min_confidence=0.8, pattern="^[ab]$") == {
        "name": "choice",
        "type": "string",
        "description": "What they chose.",
        "enum_values": ["a", "b"],
        "validation_pattern": "^[ab]$",
        "min_confidence": 0.8,
    }


@pytest.mark.parametrize("typ, confidence", [("str", 0.7), ("number", 0.7), ("string", 1.5), ("string", -0.1)])
def test_extract_rejects_bad_values(typ, confidence):
    with pytest.raises(ValueError):
        extract("x", typ, "d", min_confidence=confidence)


# ---------------------------------------------------------------- nodes against the known-good workflow


def test_code_node_matches_the_known_good_ones(brief_a):
    for name, nxt in (("setup", "greet"), ("account_facts", "negotiate")):
        known = brief_a["nodes"][name]
        code = known["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
        assert code_node(name, code, nxt) == known


def test_api_request_node_matches_the_known_good_one(brief_a, kit_api):
    ops, _ = operations(kit_api)
    bake = {"customer_id": "{{customer_id}}"}
    tool = api_tool(ops["get_account"], description="Get the late product.", bake=bake, retries=2)
    built = api_request_node("load_account", tool, "account_facts", mapping=[("data.products", "products")])
    assert built == brief_a["nodes"]["load_account"]


def test_conversation_nodes_match_the_known_good_ones(brief_a):
    nodes = brief_a["nodes"]
    greet = nodes["greet"]
    confirmed = "The person clearly confirmed they are the customer"
    verified = when_true("verify_identity_response.data.all_verified")
    assert conversation_node(
        "greet",
        task=greet["task_message"],
        tools=greet["tools"],
        transitions=[transition("identity", confirmed, when_equals("person", "customer"))],
        on_enter=say(greet["on_enter"]["text"]),
        extraction=[
            extract(
                "person",
                "string",
                greet["extraction_schema"][0]["description"],
                enum=["customer", "someone_else", "unclear"],
            )
        ],
        max_turns=60,
    ) == greet
    identity = nodes["identity"]
    assert conversation_node(
        "identity",
        task=identity["task_message"],
        tools=identity["tools"],
        transitions=[transition("load_account", "Both security answers verified", verified)],
        on_enter=llm(identity["on_enter"]["prompt"]),
        max_turns=60,
    ) == identity
    negotiate = nodes["negotiate"]
    assert conversation_node(
        "negotiate",
        task=negotiate["task_message"],
        tools=negotiate["tools"],
        transitions=[],
        on_enter=llm(negotiate["on_enter"]["prompt"]),
        max_turns=80,
    ) == negotiate


def test_workflow_rebuilds_the_known_good_one(brief_a):
    rebuilt = workflow(
        initial="setup",
        nodes=brief_a["nodes"],
        system_prompt=brief_a["system_prompt"],
        tools=brief_a["tools"],
        global_nodes={},
        test_variables=brief_a["test_variables"],
    )
    assert rebuilt == brief_a


def test_conversation_node_optional_keys():
    assert conversation_node("talk", task="t", tools=[], transitions=[], on_enter=silent()) == {
        "name": "talk",
        "node_type": "conversation",
        "task_message": "t",
        "tools": [],
        "on_enter": {"type": "silent"},
        "on_enter_first_entry_only": True,
        "transitions": [],
    }
    full = conversation_node(
        "talk",
        task="t",
        tools=[],
        transitions=[],
        on_enter=silent(),
        extraction=[extract("x", "string", "d")],
        max_turns=12,
        max_turn_transition="bye",
        first_entry_only=False,
        routing_prompt="r",
        loop_prompt="l",
    )
    assert full["max_node_turns"] == 12
    assert full["max_turn_transition"] == "bye"
    assert full["on_enter_first_entry_only"] is False
    assert (full["routing_prompt"], full["loop_prompt"]) == ("r", "l")
    assert full["extraction_schema"] == [extract("x", "string", "d")]


def test_conversation_node_copies_its_inputs():
    tools = [{"type": "function", "function": {"name": "t"}}]
    node = conversation_node("talk", task="t", tools=tools, transitions=[], on_enter=silent())
    node["tools"][0]["function"]["name"] = "changed"
    assert tools[0]["function"]["name"] == "t"


def test_api_request_node_puts_extra_transitions_first(kit_api):
    ops, _ = operations(kit_api)
    failed = transition("give_up", "failed", when("load_failure_count", "greater_than", 0))
    node = api_request_node("load", api_tool(ops["get_account"], description="d"), "next", transitions=[failed])
    assert node["transitions"] == [failed, transition("next", "always", always())]
    assert node["passthrough_default_transition"] == "next"
    assert "response_mapping" not in node


def test_api_request_node_rejects_mappings_the_platform_would_ignore(kit_api):
    ops, _ = operations(kit_api)
    for bad in [("products", "p"), ("data.products", None), ("data.products", "")]:
        with pytest.raises(ValueError):
            api_request_node("load", api_tool(ops["get_account"], description="d"), "next", mapping=[bad])
    tool_with_mapping = api_tool(ops["get_account"], description="d", mapping=[("data.products", "p")])
    with pytest.raises(ValueError):
        api_request_node("load", tool_with_mapping, "next")


def test_end_call_node_shapes():
    assert end_call_node("bye", "finished") == {
        "name": "bye",
        "node_type": "end_call",
        "on_enter": {"type": "silent"},
        "disable_inactivity_monitor": True,
        "transitions": [],
        "terminal": {
            "type": "function",
            "function": {
                "name": "finished",
                "handler": "__function__:end_call",
                "parameters": {"type": "object", "properties": {"message_mode": {"type": "string", "default": "none"}}},
            },
        },
    }
    custom = end_call_node("bye", "finished", message_mode="custom", spoken_message="Goodbye.")
    assert custom["terminal"]["function"]["parameters"]["properties"] == {
        "message_mode": {"type": "string", "default": "custom"},
        "spoken_message": {"type": "string", "default": "Goodbye."},
    }


@pytest.mark.parametrize(
    "kwargs",
    [{"message_mode": "custom"}, {"message_mode": "none", "spoken_message": "Bye."}, {"message_mode": "shout"}],
)
def test_end_call_node_rejects_inconsistent_farewells(kwargs):
    with pytest.raises(ValueError):
        end_call_node("bye", "finished", **kwargs)


def test_workflow_leaves_out_empty_optional_keys():
    wf = workflow(initial="a", nodes={"a": end_call_node("a", "done")})
    assert wf == {"initial_node": "a", "nodes": {"a": end_call_node("a", "done")}, "global_nodes": {}}


def test_workflow_copies_its_inputs():
    nodes = {"a": end_call_node("a", "done")}
    wf = workflow(initial="a", nodes=nodes)
    wf["nodes"]["a"]["name"] = "changed"
    assert nodes["a"]["name"] == "a"


# ---------------------------------------------------------------- check: real workflows


@pytest.mark.parametrize("brief", ["brief-a", "brief-b"])
def test_check_passes_the_known_good_workflows(kit, brief):
    assert check(_load(kit, f"out/{brief}.workflow.json"), call_variables=CALL_VARS) == []


def test_check_flags_the_null_values_of_base_agent(kit):
    problems = check(_load(kit, "examples/base-agent.json"), call_variables=CALL_VARS)
    assert any("null" in p and "nodes.identity.max_turn_transition" in p for p in problems)
    assert any("null" in p and "nodes.collection.passthrough_default_transition" in p for p in problems)


def test_check_does_not_touch_its_input(brief_a):
    before = copy.deepcopy(brief_a)
    check(brief_a, call_variables=CALL_VARS)
    assert brief_a == before


# ---------------------------------------------------------------- check: one rule at a time

LOOKUP = {
    "type": "function",
    "config": {"timeoutMs": 5000, "maxRetries": 0},
    "function": {
        "name": "lookup",
        "handler": "__function__:api_call",
        "description": "Look it up. CALL it when the person gives the code.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "default": "https://api.example.test/lookup"},
                "method": {"type": "string", "default": "POST"},
                "body": {
                    "type": "object",
                    "required": ["code"],
                    "properties": {
                        "ref": {"type": "string", "default": "{{ref}}"},
                        "code": {"type": "string", "description": "The code.", "default": "{{code}}"},
                    },
                },
            },
        },
    },
    "post_process_code": "try:\n    result.pop('header', None)\nexcept Exception:\n    pass\n",
    "response_mapping": [{"path": "data.status", "variable": "status"}],
}


def _plain_lookup() -> dict:
    return {k: copy.deepcopy(v) for k, v in LOOKUP.items() if k != "response_mapping"}


def _lifecycle_tool() -> dict:
    tool = _plain_lookup()
    tool["config"]["alwaysRunsAt"] = ["end_of_call"]
    return tool


def _end_tool() -> dict:
    return end_call_tool(description="Ends the call.", trigger_phrase="Goodbye.", polite_replies=["bye"])


def _valid() -> dict:
    """A small workflow that passes every rule: code node, conversation node, end_call node."""
    return workflow(
        initial="setup",
        nodes={
            "setup": code_node("setup", "vars['ready'] = 'yes'\n", "talk"),
            "talk": conversation_node(
                "talk",
                task="Ask for the code and call lookup.",
                tools=[copy.deepcopy(LOOKUP)],
                transitions=[transition("bye", "Finished", when_equals("choice", "done"))],
                on_enter=say("Hello."),
                extraction=[extract("choice", "string", "What the person chose.", enum=["done", "stay"])],
                max_turns=5,
                max_turn_transition="bye",
            ),
            "bye": end_call_node("bye", "finished"),
        },
        test_variables={"ref": "r-1"},
    )


def _problems(wf, **kwargs) -> list:
    kwargs.setdefault("call_variables", ("ref",))
    return check(wf, **kwargs)


def _has(problems: list, *needles: str) -> bool:
    return any(all(n in p for n in needles) for p in problems)


def _only_warnings(problems: list) -> bool:
    return bool(problems) and all(p.startswith("warning: ") for p in problems)


def test_the_small_workflow_passes():
    assert _problems(_valid()) == []


def test_check_reports_null_paths():
    wf = _valid()
    wf["nodes"]["talk"]["max_turn_transition"] = None
    wf["test_variables"]["missing"] = None
    problems = _problems(wf)
    assert _has(problems, "null", "nodes.talk.max_turn_transition")
    assert _has(problems, "null", "test_variables.missing")


@pytest.mark.parametrize("key", ["agent_config", "context_variables", "nodePositionz"])
def test_check_reports_forbidden_and_unknown_top_level_keys(key):
    wf = _valid()
    wf[key] = {}
    problems = _problems(wf)
    assert _has(problems, key)
    assert not _only_warnings(problems)


def test_check_allows_node_positions():
    wf = _valid()
    wf["nodePositions"] = {}
    assert _problems(wf) == []


def test_check_initial_node_must_exist():
    wf = _valid()
    del wf["initial_node"]
    assert _has(_problems(wf), "initial_node")
    wf = _valid()
    wf["initial_node"] = "nowhere"
    assert _has(_problems(wf), "initial_node", "nowhere")


def test_check_node_name_must_match_its_key():
    wf = _valid()
    wf["nodes"]["talk"]["name"] = "chat"
    assert _has(_problems(wf), "talk", "chat")


def test_check_unknown_node_type():
    wf = _valid()
    wf["nodes"]["talk"]["node_type"] = "dialog"
    assert _has(_problems(wf), "talk", "dialog")
    wf = _valid()
    del wf["nodes"]["talk"]["node_type"]
    assert _has(_problems(wf), "talk", "node_type")


def test_check_tools_only_on_conversation_nodes():
    wf = _valid()
    wf["nodes"]["setup"]["tools"] = [_plain_lookup()]
    assert _has(_problems(wf), "setup", "tools")


def test_check_pre_actions_not_on_conversation_nodes():
    wf = _valid()
    wf["nodes"]["talk"]["pre_actions"] = copy.deepcopy(wf["nodes"]["setup"]["pre_actions"])
    assert _has(_problems(wf), "talk", "pre_actions")


def test_check_empty_lists_are_not_misplaced():
    wf = _valid()
    wf["nodes"]["talk"]["pre_actions"] = []
    wf["nodes"]["setup"]["tools"] = []
    assert _problems(wf) == []


def test_check_passthrough_needs_a_default_transition():
    wf = _valid()
    del wf["nodes"]["setup"]["passthrough_default_transition"]
    assert _has(_problems(wf), "setup", "passthrough_default_transition")


def test_check_passthrough_must_end_with_always():
    wf = _valid()
    wf["nodes"]["setup"]["transitions"] = [transition("talk", "ready", when_equals("ready", "yes"))]
    assert _has(_problems(wf), "setup", "always")


def test_check_targets_must_be_nodes():
    wf = _valid()
    wf["nodes"]["talk"]["transitions"].append(transition("nowhere", "d", always()))
    assert _has(_problems(wf), "talk", "nowhere")
    wf = _valid()
    wf["nodes"]["talk"]["max_turn_transition"] = "nowhere"
    assert _has(_problems(wf), "talk", "nowhere")
    wf = _valid()
    wf["nodes"]["setup"]["passthrough_default_transition"] = "nowhere"
    assert _has(_problems(wf), "setup", "nowhere")


def _redirect() -> dict:
    return {
        "name": "off_topic",
        "description": "Brings the person back to the subject.",
        "condition": intent("The person talks about something else"),
        "task_message": "Redirect the person.",
        "on_enter": say("Let us get back to it."),
        "passthrough": True,
        "passthrough_default_transition": "__previous__",
        "excluded_nodes": ["bye"],
        "transitions": [transition("__previous__", "always", always())],
    }


def test_check_previous_is_allowed_only_in_global_nodes():
    wf = _valid()
    wf["global_nodes"] = {"off_topic": _redirect()}
    assert _problems(wf) == []
    wf["nodes"]["talk"]["transitions"].append(transition("__previous__", "back", always()))
    assert _has(_problems(wf), "talk", "__previous__")


def test_check_top_level_and_group():
    wf = _valid()
    wf["nodes"]["talk"]["transitions"][0]["condition"] = {
        "logic": "and",
        "conditions": [{"variable": "choice", "operator": "is_set"}],
    }
    assert _has(_problems(wf), "talk", "'and'")
    wf = _valid()
    wf["global_nodes"] = {"off_topic": _redirect()}
    wf["global_nodes"]["off_topic"]["condition"] = {"logic": "and", "conditions": [intent("x")]}
    assert _has(_problems(wf), "off_topic", "'and'")


def test_check_end_call_node_needs_a_terminal_and_no_transitions():
    wf = _valid()
    del wf["nodes"]["bye"]["terminal"]
    assert _has(_problems(wf), "bye", "terminal")
    wf = _valid()
    wf["nodes"]["bye"]["transitions"] = [transition("talk", "d", always())]
    assert _has(_problems(wf), "bye", "transitions")


def test_check_warns_about_unreachable_nodes():
    wf = _valid()
    wf["nodes"]["orphan"] = end_call_node("orphan", "lost")
    problems = _problems(wf)
    assert _only_warnings(problems)
    assert _has(problems, "orphan", "reachable")


def test_check_global_node_targets_are_reachable():
    wf = _valid()
    wf["nodes"]["help"] = end_call_node("help", "helped")
    redirect = _redirect()
    redirect["passthrough_default_transition"] = "help"
    redirect["transitions"] = [transition("help", "always", always())]
    wf["global_nodes"] = {"off_topic": redirect}
    assert _problems(wf) == []


def test_check_warns_when_nothing_can_end_the_call():
    wf = _valid()
    wf["nodes"]["bye"] = conversation_node(
        "bye", task="Say goodbye. No tool call in this turn.", tools=[], transitions=[], on_enter=say("Goodbye.")
    )
    problems = _problems(wf)
    assert len(problems) == 1 and _only_warnings(problems) and "end_call" in problems[0]
    with_tool = copy.deepcopy(wf)
    with_tool["nodes"]["bye"]["tools"] = [_end_tool()]
    assert _problems(with_tool) == []
    with_lifecycle = copy.deepcopy(wf)  # a lifecycle tool runs at the end; it does not end the call
    with_lifecycle["tools"] = [_lifecycle_tool()]
    assert _problems(with_lifecycle) == problems


@pytest.mark.parametrize(
    "code, needle",
    [("x = {'a': {'b': 1}}\n", "}}"), ("vars['x'] = '{{first_name}}'\n", "{{"), ("def broken(:\n", "compile")],
)
def test_check_code_node_code(code, needle):
    wf = _valid()
    wf["nodes"]["setup"] = code_node("setup", code, "talk")
    problems = _problems(wf)
    assert _has(problems, "setup", needle)
    assert not _only_warnings(problems)


@pytest.mark.parametrize("hook", ["pre_process_code", "post_process_code"])
def test_check_hook_code_must_compile_and_have_no_braces(hook):
    wf = _valid()
    wf["nodes"]["talk"]["tools"][0][hook] = "if True\n    pass\n"
    assert _has(_problems(wf), "lookup", hook, "compile")
    wf = _valid()
    wf["nodes"]["talk"]["tools"][0][hook] = "x = '{{code}}'\n"
    assert _has(_problems(wf), "lookup", hook, "{{")


def test_check_lifecycle_tool_hooks_are_checked_too():
    wf = _valid()
    tool = _lifecycle_tool()
    tool["pre_process_code"] = "def broken(:\n"
    wf["tools"] = [tool]
    assert _has(_problems(wf), "workflow tool", "lookup", "compile")


def test_check_hooks_only_on_api_call_tools():
    wf = _valid()
    tool = _end_tool()
    tool["post_process_code"] = "x = 1\n"
    wf["nodes"]["talk"]["tools"].append(tool)
    assert _has(_problems(wf), "end_call", "__function__:end_call")


def test_check_response_mapping_paths_start_with_data():
    wf = _valid()
    wf["nodes"]["talk"]["tools"][0]["response_mapping"] = [{"path": "status", "variable": "status"}]
    assert _has(_problems(wf), "lookup", "data.")


def _with_api_node(node: dict) -> dict:
    wf = _valid()
    wf["nodes"]["load"] = node
    wf["nodes"]["setup"] = code_node("setup", "x = 1\n", "load")
    return wf


def test_check_node_level_mapping_paths_start_with_data():
    node = api_request_node("load", _plain_lookup(), "talk", mapping=[("data.status", "status")])
    assert _problems(_with_api_node(node)) == []
    node["response_mapping"] = [{"path": "status", "variable": "status"}]
    assert _has(_problems(_with_api_node(node)), "load", "data.")


def test_check_response_mapping_inside_pre_actions():
    node = api_request_node("load", _plain_lookup(), "talk")
    node["pre_actions"][0]["response_mapping"] = [{"path": "data.status", "variable": "status"}]
    assert _has(_problems(_with_api_node(node)), "load", "pre_action", "response_mapping")


def test_check_each_turn_never_fires():
    wf = _valid()
    tool = _lifecycle_tool()
    tool["config"]["alwaysRunsAt"] = ["each_turn"]
    wf["tools"] = [tool]
    assert _has(_problems(wf), "lookup", "each_turn")


def test_check_workflow_level_tool_needs_always_runs_at():
    wf = _valid()
    wf["tools"] = [_plain_lookup()]
    assert _has(_problems(wf), "workflow tool", "lookup", "alwaysRunsAt")


@pytest.mark.parametrize("runs_at, needle", [("end_of_call", "must be a list"), (["end_of_calls"], "end_of_calls")])
def test_check_malformed_always_runs_at(runs_at, needle):
    wf = _valid()
    tool = _lifecycle_tool()
    tool["config"]["alwaysRunsAt"] = runs_at
    wf["tools"] = [tool]
    problems = _problems(wf)
    assert _has(problems, "lookup", needle)
    assert not _only_warnings(problems)


def test_check_warns_about_a_mapping_on_an_end_of_call_tool():
    wf = _valid()
    tool = _lifecycle_tool()
    tool["response_mapping"] = [{"path": "data.status", "variable": "final_status"}]
    wf["tools"] = [tool]
    problems = _problems(wf)
    assert len(problems) == 1 and _only_warnings(problems)
    assert _has(problems, "lookup", "end_of_call")
    tool["config"]["alwaysRunsAt"] = ["start_of_call"]
    assert _problems(wf) == []


def test_check_mapping_entries_need_a_variable():
    wf = _valid()
    wf["nodes"]["talk"]["tools"][0]["response_mapping"] = [{"path": "data.status"}]
    assert _has(_problems(wf), "lookup", "variable")


def test_check_warns_when_a_model_filled_field_would_be_baked():
    by_extraction = _valid()
    by_extraction["nodes"]["talk"]["extraction_schema"].append(extract("code", "string", "d"))
    by_mapping = _valid()
    by_mapping["nodes"]["talk"]["tools"][0]["response_mapping"].append({"path": "data.code", "variable": "code"})
    by_test_variable = _valid()
    by_test_variable["test_variables"]["code"] = "c-1"
    cases = [(by_extraction, {}), (by_mapping, {}), (by_test_variable, {}), (_valid(), {"known_vars": ("code",)})]
    for wf, kwargs in cases:
        problems = _problems(wf, **kwargs)
        assert len(problems) == 1 and _only_warnings(problems)
        assert _has(problems, "lookup", "'code'")


def test_check_call_variables_are_meant_to_be_baked():
    wf = _valid()
    wf["test_variables"]["code"] = "c-1"
    assert _problems(wf, call_variables=("ref", "code")) == []
    assert _has(_problems(wf, call_variables=()), "warning: ", "'ref'")


def test_check_warns_about_a_missing_min_confidence():
    wf = _valid()
    del wf["nodes"]["talk"]["extraction_schema"][0]["min_confidence"]
    problems = _problems(wf)
    assert len(problems) == 1 and _only_warnings(problems)
    assert _has(problems, "choice", "min_confidence")


def test_check_accepts_a_date_like_string_extraction():
    wf = _valid()
    wf["nodes"]["talk"]["extraction_schema"].append(extract("pay_day", "string", "The day they will pay, as said."))
    assert _problems(wf) == []


def test_check_lists_problems_before_warnings():
    wf = _valid()
    wf["nodes"]["orphan"] = end_call_node("orphan", "lost")
    wf["agent_config"] = {}
    problems = _problems(wf)
    assert not problems[0].startswith("warning: ")
    assert problems[-1].startswith("warning: ")


@pytest.mark.parametrize(
    "wf",
    [
        "not a workflow",
        [],
        {},
        {"initial_node": "a", "nodes": []},
        {"initial_node": "a", "nodes": {"a": "x"}},
        {
            "initial_node": "a",
            "nodes": {
                "a": {
                    "name": "a",
                    "node_type": "conversation",
                    "transitions": "x",
                    "tools": "y",
                    "extraction_schema": [1],
                }
            },
        },
        {
            "initial_node": "a",
            "nodes": {
                "a": {
                    "name": "a",
                    "node_type": "code",
                    "pre_actions": [{"function": "x"}, 4],
                    "transitions": [1, {"target_node": 3}],
                    "response_mapping": "x",
                }
            },
            "tools": [None, {"config": "x"}],
            "global_nodes": {"g": {"name": "g", "transitions": [{"target_node": ["x"]}]}},
        },
    ],
)
def test_check_never_crashes(wf):
    problems = check(wf)
    assert isinstance(problems, list) and problems


def test_when_status_tests_the_number_and_the_text():
    from builder.lib import workflow as wf
    group = wf.when_status("load", 404, 500)
    assert [(c["variable"], c["operand"]) for c in group["conditions"]] == [
        ("load_status_code", 404), ("load_status_code", "404"), ("load_status_code", 500), ("load_status_code", "500")]
    import pytest
    with pytest.raises(ValueError):
        wf.when_status("load", "404")


def test_check_refuses_tool_named_results_in_an_api_request_node():
    from builder.lib import workflow as wf
    tool = {"type": "function", "function": {"name": "items_list", "handler": "__function__:api_call",
                                             "parameters": {"type": "object", "properties": {}}}}
    def flow(var):
        node = wf.api_request_node("load", tool, "main", transitions=[
            wf.transition("fail", "failed", wf.when(var, "greater_than", 0))])
        return {"initial_node": "load", "nodes": {"load": node, "main": wf.end_call_node("main", "end"),
                                                  "fail": wf.end_call_node("fail", "end")}}
    assert any("named after the node" in p for p in wf.check(flow("items_list_failure_count")))
    assert not any("named after the node" in p for p in wf.check(flow("load_failure_count")))
