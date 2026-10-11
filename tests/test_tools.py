"""Tests for builder.lib.tools: reading the tool API file and building Freya tools.

Practice values (tool names, field names, enums) appear here on purpose: tests are not builder code.
"""
import copy
import json
import time

import pytest

from builder.lib.tools import (
    Field,
    Operation,
    api_tool,
    describe,
    end_call_tool,
    enum,
    field,
    load_api,
    operations,
)

PRACTICE_TOOLS = {
    "verify_identity",
    "get_account",
    "create_promise",
    "add_note",
    "schedule_callback",
    "transfer_to_agent",
    "close_call",
}
BANK = "https://freya-bank-mock.freyavoice.workers.dev/v1"
SERVICE_FAILED = "The service failed. Nothing was recorded. The call may be repeated."


# ---------------------------------------------------------------- helpers


@pytest.fixture
def ops(kit_api: dict) -> dict:
    parsed, warnings = operations(kit_api)
    assert warnings == []
    return parsed


def _known(kit, brief: str) -> dict:
    return json.loads((kit / "out" / f"{brief}.workflow.json").read_text(encoding="utf-8"))


def _all_tools(wf: dict):
    for node in wf["nodes"].values():
        yield from node.get("tools", [])
        yield from node.get("pre_actions", [])
    yield from wf.get("tools", [])


def _find_tool(wf: dict, name: str) -> dict:
    return next(t for t in _all_tools(wf) if t["function"]["name"] == name)


def _names(fields) -> list:
    return [f.name for f in fields]


def _minimal_api(paths: dict, **extra) -> dict:
    return {"openapi": "3.0.3", "servers": [{"url": "https://api.example.test/v2/"}], "paths": paths, **extra}


def _post(schema: dict) -> dict:
    return {
        "post": {
            "summary": "s",
            "requestBody": {"content": {"application/json": {"schema": schema}}},
            "responses": {"200": {"description": "ok"}},
        }
    }


def _count_nulls(value) -> int:
    if value is None:
        return 1
    if isinstance(value, dict):
        return sum(_count_nulls(v) for v in value.values())
    if isinstance(value, list):
        return sum(_count_nulls(v) for v in value)
    return 0


# ---------------------------------------------------------------- the practice API


def test_practice_api_has_the_seven_operations(ops):
    assert set(ops) == PRACTICE_TOOLS
    for name, op in ops.items():
        assert isinstance(op, Operation)
        assert op.name == name
        assert op.method == "POST"
        assert op.url == f"{BANK}/{name}"
        assert op.other_responses == (("500", SERVICE_FAILED),)


def test_verify_identity_request_fields(ops):
    op = ops["verify_identity"]
    assert op.summary == "Check one security answer. Three wrong answers in total end the check."
    assert op.description == ""
    assert _names(op.request) == ["customer_id", "field", "answer"]
    assert all(f.required and f.type == "string" for f in op.request)
    assert op.request[1].enum == ("date_of_birth", "phone_last4")
    assert op.request[2].description.startswith("For date_of_birth: the date as YYYY-MM-DD.")


def test_verify_identity_response_fields(ops):
    resp = {f.name: f for f in ops["verify_identity"].response}
    assert list(resp) == ["ok", "error", "verified", "wrong_answers_left", "all_verified", "hint"]
    assert resp["ok"].type == "boolean"
    assert resp["wrong_answers_left"].type == "integer"
    assert resp["hint"].enum == ("day_month_swapped",)
    assert not any(f.required for f in resp.values())


def test_nested_array_item_fields(ops):
    products = next(f for f in ops["get_account"].response if f.name == "products")
    assert (products.type, products.item_type) == ("array", "object")
    items = {f.name: f for f in products.fields}
    assert list(items) == [
        "product_id",
        "type",
        "card_last4",
        "past_due",
        "days_late",
        "minimum_payment",
        "instalment_amount",
    ]
    assert items["type"].enum == ("credit_card", "personal_loan", "car_loan")
    assert items["card_last4"].description == "credit cards only"
    assert items["past_due"].type == "number"
    assert items["days_late"].type == "integer"


def test_formats_and_required_flags(ops):
    promise = {f.name: f for f in ops["create_promise"].request}
    assert promise["date"].format == "date"
    assert promise["amount"].type == "number"
    assert all(f.required for f in promise.values())
    assert {f.name: f.required for f in ops["add_note"].request} == {
        "customer_id": True,
        "product_id": True,
        "reason": True,
        "text": False,
    }
    assert {f.name: f.required for f in ops["close_call"].request} == {
        "customer_id": True,
        "outcome": True,
        "reason": False,
    }


def test_field_and_enum_lookups(ops):
    op = ops["transfer_to_agent"]
    assert field(op, "queue") == Field(
        name="queue", type="string", enum=("restructuring", "general", "support"), required=True
    )
    assert enum(op, "queue") == ("restructuring", "general", "support")
    assert enum(op, "customer_id") == ()


def test_field_lookup_error_lists_known_fields(ops):
    with pytest.raises(KeyError, match="customer_id, queue"):
        field(ops["transfer_to_agent"], "queeu")


def test_field_lookup_error_points_at_response_fields(ops):
    with pytest.raises(KeyError, match="response"):
        field(ops["verify_identity"], "all_verified")


# ---------------------------------------------------------------- nothing is hard-coded


def _json_schema(path_item: dict) -> dict:
    return path_item["post"]["requestBody"]["content"]["application/json"]


def _mutated(kit_api: dict) -> dict:
    """The practice API with a renamed path, renamed fields, new enums, a $ref, an allOf, no servers."""
    api = copy.deepcopy(kit_api)
    del api["servers"]
    paths = api["paths"]
    paths["/confirm_caller"] = paths.pop("/verify_identity")
    api["components"] = {
        "schemas": {
            "IdentityCheck": {
                "type": "object",
                "properties": {
                    "client_ref": {"type": "string"},
                    "question": {"type": "string", "enum": ["postcode", "birth_year"]},
                    "reply": {"type": "string", "description": "The caller's reply, as said."},
                },
                "required": ["client_ref", "question", "reply"],
            },
            "Owner": {"type": "object", "properties": {"client_ref": {"type": "string"}}, "required": ["client_ref"]},
            "Product": {"type": "object", "properties": {"item_id": {"type": "string"}, "balance": {"type": "number"}}},
        }
    }
    _json_schema(paths["/confirm_caller"])["schema"] = {"$ref": "#/components/schemas/IdentityCheck"}
    _json_schema(paths["/get_account"])["schema"] = {
        "allOf": [
            {"$ref": "#/components/schemas/Owner"},
            {
                "type": "object",
                "properties": {"segment": {"type": "string", "enum": ["retail", "business"]}},
                "required": ["segment"],
            },
        ]
    }
    close = _json_schema(paths["/close_call"])["schema"]
    close["properties"]["result"] = close["properties"].pop("outcome")
    close["properties"]["result"]["enum"] = ["settled", "escalated", "unreachable"]
    close["required"] = ["customer_id", "result"]
    account_ok = paths["/get_account"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    account_ok["properties"]["products"]["items"] = {"$ref": "#/components/schemas/Product"}
    return api


def test_mutated_api_parses_without_hard_coded_names(kit_api):
    api = _mutated(kit_api)
    before = copy.deepcopy(api)
    ops, warnings = operations(api)
    assert api == before
    assert set(ops) == (PRACTICE_TOOLS - {"verify_identity"}) | {"confirm_caller"}
    assert any("servers" in w for w in warnings)
    caller = ops["confirm_caller"]
    assert caller.url == "/confirm_caller"
    assert _names(caller.request) == ["client_ref", "question", "reply"]
    assert all(f.required for f in caller.request)
    assert enum(caller, "question") == ("postcode", "birth_year")
    assert field(caller, "reply").description == "The caller's reply, as said."
    account = ops["get_account"]
    assert [(f.name, f.required) for f in account.request] == [("client_ref", True), ("segment", True)]
    assert enum(account, "segment") == ("retail", "business")
    products = next(f for f in account.response if f.name == "products")
    assert _names(products.fields) == ["item_id", "balance"]
    assert enum(ops["close_call"], "result") == ("settled", "escalated", "unreachable")
    with pytest.raises(KeyError):
        field(ops["close_call"], "outcome")


def test_api_tool_follows_the_mutated_api(kit_api):
    ops, _ = operations(_mutated(kit_api))
    tool = api_tool(ops["confirm_caller"], description="Check one answer.", bake={"client_ref": "{{client_ref}}"})
    params = tool["function"]["parameters"]["properties"]
    assert params["url"] == {"type": "string", "default": "/confirm_caller"}
    body = params["body"]
    assert list(body["properties"]) == ["client_ref", "question", "reply"]
    assert body["required"] == ["question", "reply"]
    assert body["properties"]["question"] == {
        "type": "string",
        "enum": ["postcode", "birth_year"],
        "default": "{{question}}",
    }


def test_describe_follows_the_mutated_api(kit_api):
    ops, _ = operations(_mutated(kit_api))
    text = describe(ops)
    assert "confirm_caller: POST /confirm_caller" in text
    assert "postcode | birth_year" in text
    assert "segment" in text and "item_id" in text


# ---------------------------------------------------------------- unexpected shapes


def test_not_an_object_or_no_paths_warns():
    ops, warnings = operations("not an api")  # type: ignore[arg-type]
    assert ops == {} and warnings
    ops, warnings = operations({"openapi": "3.0.3"})
    assert ops == {} and warnings


def test_bad_path_items_and_operations_are_skipped_with_warnings():
    api = _minimal_api(
        {
            "/a": "oops",
            "/b": {"post": "oops"},
            "/c": {"summary": "no operation here"},
            "/d": _post({"type": "object", "properties": {"x": {"type": "string"}}}),
        }
    )
    ops, warnings = operations(api)
    assert list(ops) == ["d"]
    assert len(warnings) == 3
    assert ops["d"].url == "https://api.example.test/v2/d"
    assert _names(ops["d"].request) == ["x"]


def test_non_json_request_content_is_ignored_with_a_warning():
    body = {"content": {"text/plain": {"schema": {"type": "string"}}}}
    ops, warnings = operations(_minimal_api({"/x": {"post": {"requestBody": body, "responses": {}}}}))
    assert ops["x"].request == ()
    assert any("text/plain" in w for w in warnings)


def test_json_media_type_with_parameters_is_read():
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    body = {"content": {"application/json; charset=utf-8": {"schema": schema}}}
    ops, warnings = operations(_minimal_api({"/x": {"post": {"requestBody": body}}}))
    assert _names(ops["x"].request) == ["a"]
    assert warnings == []


@pytest.mark.parametrize(
    "ref, needle",
    [("other.json#/components/schemas/X", "local"), ("#/components/schemas/Missing", "not found")],
)
def test_unusable_refs_warn(ref, needle):
    ops, warnings = operations(_minimal_api({"/x": _post({"$ref": ref})}))
    assert ops["x"].request == ()
    assert any(needle in w for w in warnings)


def test_recursive_ref_stops_with_a_warning():
    node = {
        "type": "object",
        "properties": {"label": {"type": "string"}, "child": {"$ref": "#/components/schemas/Node"}},
    }
    api = _minimal_api({"/x": _post({"$ref": "#/components/schemas/Node"})}, components={"schemas": {"Node": node}})
    ops, warnings = operations(api)
    assert _names(ops["x"].request) == ["label", "child"]
    child = field(ops["x"], "child")
    assert child.type == "object"
    assert child.fields == ()
    assert any("Node" in w for w in warnings)


def test_odd_schemas_are_read_best_effort():
    schema = {
        "type": "object",
        "required": ["a"],
        "properties": {
            "a": {"type": ["string", "null"]},
            "b": {"type": "integer", "required": True, "enum": [1, 2, None]},
            "c": {"properties": {"d": {"type": "boolean"}}},
            "e": "not a schema",
        },
    }
    ops, warnings = operations(_minimal_api({"/x": _post(schema)}))
    a, b, c, e = ops["x"].request
    assert (a.type, a.required) == ("string", True)
    assert (b.required, b.enum) == (True, ("1", "2"))
    assert c.type == "object" and _names(c.fields) == ["d"]
    assert (e.name, e.type) == ("e", "")
    assert len(warnings) == 2


def test_one_of_is_read_as_a_union_with_a_warning():
    schema = {
        "oneOf": [
            {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]},
            {"type": "object", "properties": {"b": {"type": "string"}}},
        ]
    }
    ops, warnings = operations(_minimal_api({"/x": _post(schema)}))
    assert [(f.name, f.required) for f in ops["x"].request] == [("a", False), ("b", False)]
    assert any("oneOf" in w for w in warnings)


def test_component_request_bodies_and_responses_are_followed():
    made = {"type": "object", "properties": {"id": {"type": "string"}}}
    api = _minimal_api(
        {
            "/x": {
                "post": {
                    "requestBody": {"$ref": "#/components/requestBodies/In"},
                    "responses": {
                        "201": {"$ref": "#/components/responses/Made"},
                        "404": {"$ref": "#/components/responses/Gone"},
                    },
                }
            }
        },
        components={
            "requestBodies": {
                "In": {"content": {"application/json": {"schema": {"type": "object", "properties": {"a": {}}}}}}
            },
            "responses": {
                "Made": {"description": "made", "content": {"application/json": {"schema": made}}},
                "Gone": {"description": "No such thing."},
            },
        },
    )
    ops, warnings = operations(api)
    op = ops["x"]
    assert _names(op.request) == ["a"]
    assert _names(op.response) == ["id"]
    assert op.other_responses == (("404", "No such thing."),)
    assert warnings == []


def test_a_second_method_on_one_path_is_skipped_with_a_warning():
    api = _minimal_api({"/x": {"get": {"summary": "read"}, "post": {"summary": "write"}}})
    ops, warnings = operations(api)
    assert list(ops) == ["x"]
    assert (ops["x"].method, ops["x"].summary) == ("GET", "read")
    assert any("POST" in w for w in warnings)


def test_parameters_are_reported_as_unread():
    api = _minimal_api({"/x": {"post": {"parameters": [{"name": "q", "in": "query"}]}}})
    ops, warnings = operations(api)
    assert ops["x"].request == ()
    assert any("parameters" in w for w in warnings)


def test_server_variables_and_operation_servers():
    api = {
        "servers": [{"url": "https://{host}/api/", "variables": {"host": {"default": "h.example.test"}}}],
        "paths": {
            "/x": {"post": {}},
            "/y": {"post": {"servers": [{"url": "https://other.example.test"}]}},
        },
    }
    ops, warnings = operations(api)
    assert ops["x"].url == "https://h.example.test/api/x"
    assert ops["y"].url == "https://other.example.test/y"
    assert warnings == []


def test_a_relative_server_url_warns():
    ops, warnings = operations({"servers": [{"url": "/v1"}], "paths": {"/x": {"post": {}}}})
    assert ops["x"].url == "/v1/x"
    assert any("absolute" in w for w in warnings)


@pytest.mark.parametrize("path", ["/accounts/{id}/lookup", "/"])
def test_names_that_are_not_tool_names_warn(path):
    ops, warnings = operations(_minimal_api({path: {"post": {}}}))
    assert list(ops) == [{"/accounts/{id}/lookup": "accounts_id_lookup", "/": ""}[path]]
    assert any("tool name" in w for w in warnings)


def test_number_and_boolean_enums_keep_their_type_in_the_tool():
    schema = {
        "type": "object",
        "properties": {"n": {"type": "integer", "enum": [1, 2]}, "flag": {"type": "boolean", "enum": [True]}},
    }
    ops, warnings = operations(_minimal_api({"/x": _post(schema)}))
    assert warnings == []
    assert enum(ops["x"], "n") == ("1", "2")
    leaves = api_tool(ops["x"], description="d")["function"]["parameters"]["properties"]["body"]["properties"]
    assert leaves["n"]["enum"] == [1, 2]
    assert leaves["flag"]["enum"] == [True]


def test_a_nullable_any_of_keeps_the_real_type():
    nullable = {"anyOf": [{"type": "null"}, {"type": "string", "description": "Free text."}]}
    ops, warnings = operations(_minimal_api({"/x": _post({"type": "object", "properties": {"note": nullable}})}))
    note = field(ops["x"], "note")
    assert (note.type, note.description) == ("string", "Free text.")
    assert warnings == []


def test_a_nullable_ref_body_keeps_its_required_fields():
    body = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
    api = _minimal_api(
        {"/x": _post({"anyOf": [{"$ref": "#/components/schemas/In"}, {"type": "null"}]})},
        components={"schemas": {"In": body}},
    )
    ops, warnings = operations(api)
    assert [(f.name, f.required) for f in ops["x"].request] == [("a", True)]
    assert warnings == []


def test_a_pathological_ref_diamond_is_cut_short():
    depth = 22
    schemas = {
        f"L{i}": {
            "type": "object",
            "properties": {side: {"$ref": f"#/components/schemas/L{i + 1}"} for side in ("a", "b")},
        }
        for i in range(depth)
    }
    schemas[f"L{depth}"] = {"type": "object", "properties": {"x": {"type": "string"}}}
    api = _minimal_api({"/x": _post({"$ref": "#/components/schemas/L0"})}, components={"schemas": schemas})
    started = time.perf_counter()
    ops, warnings = operations(api)
    assert time.perf_counter() - started < 5
    assert _names(ops["x"].request) == ["a", "b"]
    assert any("expansions" in w for w in warnings)


def test_operations_does_not_touch_its_input(kit_api):
    before = copy.deepcopy(kit_api)
    operations(kit_api)
    assert kit_api == before


# ---------------------------------------------------------------- describe and load_api


def test_describe_lists_tools_fields_and_codes(ops):
    text = describe(ops)
    for name in PRACTICE_TOOLS:
        assert f"{name}: POST {BANK}/{name}" in text
    assert "Check one security answer." in text
    assert "date_of_birth | phone_last4" in text
    assert "format date" in text
    assert "required" in text
    assert "500: " + SERVICE_FAILED in text
    assert "For date_of_birth: the date as YYYY-MM-DD." in text
    lines = text.splitlines()
    at = next(i for i, line in enumerate(lines) if line.strip().startswith("products"))
    assert "array of object" in lines[at]
    child = lines[at + 1]
    assert child.strip().startswith("product_id")
    assert len(child) - len(child.lstrip()) > len(lines[at]) - len(lines[at].lstrip())


def test_load_api_reads_json_with_a_bom(tmp_path, kit_api):
    path = tmp_path / "api.json"
    path.write_text(json.dumps(kit_api), encoding="utf-8-sig")
    assert load_api(path) == kit_api
    assert load_api(str(path)) == kit_api


@pytest.mark.parametrize("text", ["[1, 2]", "{not json"])
def test_load_api_rejects_what_is_not_a_json_object(tmp_path, text):
    path = tmp_path / "api.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        load_api(path)


# ---------------------------------------------------------------- api_tool against the known-good tools

KNOWN_API_TOOLS = [
    ("brief-a", "verify_identity"),
    ("brief-a", "schedule_callback"),
    ("brief-a", "transfer_to_agent"),
    ("brief-a", "create_promise"),
    ("brief-a", "get_account"),
    ("brief-a", "close_call"),
    ("brief-b", "add_note"),
    ("brief-b", "create_promise"),
    ("brief-b", "close_call"),
]


def _rebuild(op: Operation, known: dict) -> dict:
    """Call api_tool with what the known tool chose: description, notes, bakes, hooks, config."""
    config = known["config"]
    fn = known["function"]
    leaves = fn["parameters"]["properties"]["body"]["properties"]
    bake = {k: v["default"] for k, v in leaves.items() if v["default"] == "{{customer_id}}"}
    placeholders = {
        k: v["default"][2:-2] for k, v in leaves.items() if k not in bake and v["default"] != "{{" + k + "}}"
    }
    notes = {k: v["description"] for k, v in leaves.items() if "description" in v}
    return api_tool(
        op,
        description=fn["description"],
        bake=bake,
        placeholders=placeholders,
        notes=notes,
        pre=known.get("pre_process_code", ""),
        post=known.get("post_process_code", ""),
        retries=config["maxRetries"],
        timeout_ms=config["timeoutMs"],
        lifecycle=(config.get("alwaysRunsAt") or [""])[0],
    )


@pytest.mark.parametrize("brief, name", KNOWN_API_TOOLS)
def test_api_tool_rebuilds_the_known_good_tool(kit, ops, brief, name):
    known = _find_tool(_known(kit, brief), name)
    op = ops[name]
    expected = copy.deepcopy(known)
    leaves = expected["function"]["parameters"]["properties"]["body"]["properties"]
    for f in op.request:  # the OpenAPI description comes first, the builder's note is appended
        if f.description:
            leaves[f.name]["description"] = " ".join(x for x in (f.description, leaves[f.name].get("description")) if x)
    assert _rebuild(op, known) == expected


def test_api_tool_minimal_shape(ops):
    tool = api_tool(ops["add_note"], description="Write a note.")
    assert set(tool) == {"type", "config", "function"}
    assert tool["type"] == "function"
    assert tool["config"] == {"timeoutMs": 12000, "maxRetries": 0}
    fn = tool["function"]
    assert (fn["name"], fn["handler"], fn["description"]) == ("add_note", "__function__:api_call", "Write a note.")
    params = fn["parameters"]
    assert params["type"] == "object"
    assert list(params["properties"]) == ["url", "method", "headers", "body"]
    assert params["properties"]["method"] == {"type": "string", "default": "POST"}
    assert params["properties"]["headers"] == {
        "type": "object",
        "properties": {"Content-Type": {"type": "string", "default": "application/json"}},
    }
    body = params["properties"]["body"]
    assert body["type"] == "object"
    assert body["required"] == ["customer_id", "product_id", "reason"]
    assert body["properties"]["text"] == {"type": "string", "default": "{{text}}"}


def test_api_tool_hooks_and_mapping_only_when_given(ops):
    tool = api_tool(ops["add_note"], description="d", pre="  \n", post="", mapping=[])
    assert set(tool) == {"type", "config", "function"}
    tool = api_tool(ops["add_note"], description="d", pre="x = 1\n", post="y = 2\n", mapping=[("data.ok", "note_ok")])
    assert tool["pre_process_code"] == "x = 1\n"
    assert tool["post_process_code"] == "y = 2\n"
    assert tool["response_mapping"] == [{"path": "data.ok", "variable": "note_ok"}]


def test_api_tool_start_of_call_lifecycle(ops):
    tool = api_tool(ops["get_account"], description="d", lifecycle="start_of_call", retries=2, timeout_ms=5000)
    assert tool["config"] == {"timeoutMs": 5000, "maxRetries": 2, "alwaysRunsAt": ["start_of_call"]}


def test_api_tool_untyped_field_falls_back_to_string_and_drops_format():
    op = Operation(
        name="x",
        method="POST",
        url="https://api.example.test/x",
        summary="",
        description="",
        request=(
            Field(name="when", format="date-time", required=True),
            Field(name="n", type="integer", description="A count."),
        ),
        response=(),
        other_responses=(),
    )
    tool = api_tool(op, description="d", notes={"n": "Say it as digits."})
    body = tool["function"]["parameters"]["properties"]["body"]
    assert body["properties"]["when"] == {"type": "string", "default": "{{when}}"}
    assert body["properties"]["n"] == {
        "type": "integer",
        "description": "A count. Say it as digits.",
        "default": "{{n}}",
    }
    assert body["required"] == ["when"]


def test_api_tool_does_not_touch_its_inputs(ops):
    bake = {"customer_id": "{{customer_id}}"}
    notes = {"reason": "Why."}
    mapping = [("data.ok", "ok")]
    tool = api_tool(ops["add_note"], description="d", bake=bake, notes=notes, mapping=mapping)
    assert bake == {"customer_id": "{{customer_id}}"}
    assert notes == {"reason": "Why."}
    assert mapping == [("data.ok", "ok")]
    tool["function"]["parameters"]["properties"]["body"]["properties"]["reason"]["enum"].append("other")
    assert enum(ops["add_note"], "reason") == ("refused", "hardship", "dispute", "paid", "service_error")


def test_api_tool_writes_no_null(ops):
    for op in ops.values():
        assert _count_nulls(api_tool(op, description="d")) == 0


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"bake": {"nope": "x"}}, "bake.*nope"),
        ({"placeholders": {"nope": "x"}}, "placeholders.*nope"),
        ({"notes": {"nope": "x"}}, "notes.*nope"),
        ({"lifecycle": "each_turn"}, "each_turn"),
        ({"lifecycle": "sometimes"}, "sometimes"),
        ({"mapping": [("ok", "flag")]}, "data"),
        ({"mapping": [("data.ok", "")]}, "variable"),
        ({"bake": {"customer_id": "{{customer_id}}"}, "placeholders": {"customer_id": "cid"}}, "customer_id"),
        ({"lifecycle": "end_of_call", "mapping": [("data.ok", "flag")]}, "end_of_call"),
    ],
)
def test_api_tool_value_errors(ops, kwargs, message):
    with pytest.raises(ValueError, match=message):
        api_tool(ops["close_call"], description="d", **kwargs)


# ---------------------------------------------------------------- end_call_tool


def _props(tool: dict) -> dict:
    return tool["function"]["parameters"]["properties"]


def test_end_call_tool_matches_the_known_good_one(kit):
    known = _find_tool(_known(kit, "brief-a"), "end_call")
    built = end_call_tool(
        description=known["function"]["description"],
        trigger_phrase="Have a good day.",
        polite_replies=_props(known)["trigger_pattern_both"]["default"].split("|"),
    )
    assert _props(built)["trigger_pattern_both"]["default"] == "goodbye|bye"      # the kit's list minus the risky ones
    _props(built)["trigger_pattern_both"] = _props(known)["trigger_pattern_both"]
    assert built == known


def test_end_call_tool_trigger_pattern():
    tool = end_call_tool(
        description="d", trigger_phrase="goodbye now.", polite_replies=["bye"], timeout_ms=5000, trigger_timeout=2
    )
    assert _props(tool)["trigger_pattern"]["default"] == "goodbye now"
    assert _props(tool)["trigger_timeout"]["default"] == 2
    assert tool["config"] == {"timeoutMs": 5000}
    tool = end_call_tool(description="d", trigger_phrase="  See You  ", polite_replies=["bye", "ok", "Bye now"])
    assert _props(tool)["trigger_pattern"]["default"] == "See You|see you"
    assert _props(tool)["trigger_pattern_both"]["default"] == "bye|Bye now"


def test_end_call_keeps_only_farewells_the_customer_cannot_say_by_accident():
    # the engine matches these against the customer's words too: "ok" inside "took" ended a call
    tool = end_call_tool(description="d", trigger_phrase="Goodbye.", polite_replies=["OK", "Okay", "Thanks", "Thank you"])
    assert _props(tool)["trigger_pattern_both"]["default"] == "Goodbye|Bye"


@pytest.mark.parametrize(
    "phrase, replies",
    [("", ["bye"]), (" . ", ["bye"]), ("a|b", ["bye"]), ("Bye.", []), ("Bye.", ["ok|fine"]), ("Bye.", ["ok", ""])],
)
def test_end_call_tool_rejects_unusable_patterns(phrase, replies):
    with pytest.raises(ValueError):
        end_call_tool(description="d", trigger_phrase=phrase, polite_replies=replies)


def test_a_lifecycle_tool_retries_by_default_a_normal_tool_does_not(kit_api):
    ops, _ = operations(kit_api)
    assert api_tool(ops["close_call"], description="x", lifecycle="end_of_call")["config"]["maxRetries"] == 2
    assert api_tool(ops["create_promise"], description="x")["config"]["maxRetries"] == 0
    assert api_tool(ops["close_call"], description="x", lifecycle="end_of_call", retries=0)["config"]["maxRetries"] == 0


def test_end_call_takes_every_closing_sentence():
    tool = end_call_tool(description="d", trigger_phrase=["Goodbye now.", "PLEASE HOLD ON."], polite_replies=["bye"])
    assert tool["function"]["parameters"]["properties"]["trigger_pattern"]["default"] == "Goodbye now|goodbye now|PLEASE HOLD ON|please hold on"
    single = end_call_tool(description="d", trigger_phrase="Bye.", polite_replies=["bye"])
    assert single["function"]["parameters"]["properties"]["trigger_pattern"]["default"] == "Bye|bye"
    with pytest.raises(ValueError):
        end_call_tool(description="d", trigger_phrase=["Bye", " "], polite_replies=["bye"])


ENVELOPE_API = {
    "openapi": "3.0.0",
    "servers": [{"url": "https://mock.example"}],
    "paths": {
        "/svc/v1/items.list": {"post": {
            "operationId": "items_list",
            "requestBody": {"content": {"application/json": {"schema": {
                "type": "object", "required": ["data"],
                "properties": {
                    "data": {"type": "object", "required": ["owner"],
                             "properties": {"owner": {"type": "string"}, "flow": {"type": "string"}}},
                    "meta": {"type": "object", "properties": {"lang": {"type": "string"}}},
                }}}}},
            "responses": {"200": {"description": "ok"}}}},
        "/svc/v1/items.get": {"post": {"responses": {"200": {"description": "ok"}}}},
    },
}


def test_a_path_that_is_no_tool_name_takes_the_operation_id_or_underscores():
    ops, warnings = operations(ENVELOPE_API)
    assert sorted(ops) == ["items_list", "svc_v1_items_get"]
    assert ops["items_list"].url == "https://mock.example/svc/v1/items.list"
    assert not any("items.list" in w for w in warnings)   # an operationId is the intended name: no warning
    assert any("named 'svc_v1_items_get'" in w for w in warnings)


def test_envelope_tool_has_the_inner_fields_and_its_pre_hook_wraps_them():
    from builder.lib import embed

    ops, _ = operations(ENVELOPE_API)
    tool = api_tool(ops["items_list"], description="x", bake={"owner": "{{owner_id}}"},
                    envelope="data", envelope_parts={"meta": {"lang": "xx"}}, pre="vars['seen'] = 1")
    body = tool["function"]["parameters"]["properties"]["body"]
    assert list(body["properties"]) == ["owner", "flow"] and body["properties"]["owner"]["default"] == "{{owner_id}}"
    code = tool["pre_process_code"]
    assert code.startswith("vars['seen'] = 1\n") and "{{" not in code and "}}" not in code
    assert embed.check(code) == []
    config, state = {"body": {"owner": "7", "flow": "f"}}, {}
    exec(code, {"config": config, "vars": state})
    assert config["body"] == {"meta": {"lang": "xx"}, "data": {"owner": "7", "flow": "f"}} and state == {"seen": 1}


@pytest.mark.parametrize("kwargs", [
    {"envelope": "nope"},
    {"envelope": "data", "envelope_parts": {"other": 1}},
    {"envelope": "data", "envelope_parts": {"meta": {"lang": "{{lang}}"}}},
    {"envelope_parts": {"meta": {}}},
    {"envelope": "data", "bake": {"data": "x"}},
])
def test_envelope_mistakes_are_refused(kwargs):
    ops, _ = operations(ENVELOPE_API)
    with pytest.raises((ValueError, KeyError)):
        api_tool(ops["items_list"], description="x", **kwargs)
