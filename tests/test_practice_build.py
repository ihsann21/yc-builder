"""builder/lib assembled into a whole workflow (practice Brief A), checked offline end to end.

The workflow is dev/practice_a.build(): the kit builder's prompts with our plumbing. These tests
run the embedded code the way one call would, step by step, and read the close tool's outcome.
"""
import copy

import pytest

from builder.lib import embed
from builder.lib import workflow as wf
from dev import practice_a
from dev.practice import CALL_VARIABLES, kit_workflow


@pytest.fixture(scope="module")
def built(kit):
    return practice_a.build()


def tools_of(node: dict) -> list[str]:
    return [t["function"]["name"] for t in node.get("tools", [])]


def hook(built: dict, name: str, which: str) -> str:
    for node in built["nodes"].values():
        for tool in node.get("tools", []):
            if tool["function"]["name"] == name:
                return tool[which]
    return next(t[which] for t in built["tools"] if t["function"]["name"] == name)


def code_of(built: dict, node: str) -> str:
    return built["nodes"][node]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]


def test_passes_the_static_check(built):
    assert wf.check(built, CALL_VARIABLES) == []


def test_same_shape_and_prompts_as_the_kit_workflow(kit, built):
    ref = kit_workflow(kit, "a")
    assert built["system_prompt"] == ref["system_prompt"] and built["test_variables"] == ref["test_variables"]
    assert list(built["nodes"]) == list(ref["nodes"])
    for key, node in built["nodes"].items():
        theirs = ref["nodes"][key]
        assert node["node_type"] == theirs["node_type"]
        assert tools_of(node) == tools_of(theirs)
        assert node.get("task_message") == theirs.get("task_message")
        assert [t["target_node"] for t in node["transitions"]] == [t["target_node"] for t in theirs["transitions"]]
    assert [t["function"]["name"] for t in built["tools"]] == ["close_call"]
    assert built["tools"][0]["config"]["alwaysRunsAt"] == ["end_of_call"]


def test_every_embedded_snippet_passes_the_snippet_check(built):
    snippets = [code_of(built, "setup"), code_of(built, "account_facts")]
    for name in ("verify_identity", "schedule_callback", "transfer_to_agent", "create_promise", "close_call"):
        snippets.append(hook(built, name, "pre_process_code"))
    for name in ("verify_identity", "schedule_callback", "transfer_to_agent", "create_promise"):
        snippets.append(hook(built, name, "post_process_code"))
    for code in snippets:
        assert embed.check(code) == []


class Call:
    """One call driven through the workflow's own embedded code: tools are answered by the test."""

    def __init__(self, built: dict, now: str = "2026-10-14T11:00"):
        self.built = built
        self.state = {"customer_id": "c1", "first_name": "Ann", "last_name": "Lee", "title": "Ms", "now": now}
        embed.run(code_of(built, "setup"), state=self.state)

    def tool(self, name: str, body: dict, data, status: str = "success") -> tuple[dict, dict]:
        request = {"url": "u", "method": "POST", "headers": {}, "body": dict(body, customer_id="c1")}
        embed.run(hook(self.built, name, "pre_process_code"), state=self.state, request=request)
        result = {"status": status, "data": copy.deepcopy(data), "header": {"h": "v"}}
        embed.run(hook(self.built, name, "post_process_code"), state=self.state, result=result)
        return request["body"], result

    def account(self, products: list[dict]) -> str:
        self.state["products"] = products
        embed.run(code_of(self.built, "account_facts"), state=self.state)
        return self.state["account_facts"]

    def close(self, outcome: str = "", reason: str = "") -> tuple[str, str | None]:
        body = {"customer_id": "c1", "outcome": outcome, "reason": reason}
        embed.run(hook(self.built, "close_call", "pre_process_code"), state=self.state, request={"body": body})
        return body["outcome"], body.get("reason")


CARD = {"product_id": "p1", "type": "credit_card", "card_last4": "4821", "past_due": 455.2, "days_late": 9,
        "minimum_payment": 45}


def verified_call(built) -> Call:
    call = Call(built)
    call.tool("verify_identity", {"field": "date_of_birth", "answer": "14 March 1988"},
              {"ok": True, "verified": True, "all_verified": False, "wrong_answers_left": 3})
    _, result = call.tool("verify_identity", {"field": "phone_last4", "answer": "four eight two one"},
                          {"ok": True, "verified": True, "all_verified": True, "wrong_answers_left": 3})
    assert "verified" in result["data"]["what_to_do_next"] and call.state["bb_identity"] == "verified"
    return call


def test_a_promise_call(built):
    call = verified_call(built)
    assert "credit card ending 4821" in call.account([CARD])
    body, result = call.tool("create_promise", {"product_id": "credit card", "amount": "455.20", "date": "2026-10-17"},
                             {"ok": True, "promise_id": "pr_1"})
    assert body["product_id"] == "p1" and body["amount"] == 455.2
    assert body["date"] == "2026-10-19"                                     # Saturday moved to Monday
    assert "date changed from 2026-10-17 to 2026-10-19" in result["data"]["what_to_do_next"]
    assert call.close("no_promise", "refused") == ("promise", None)


def test_a_promise_that_fails_twice(built):
    call = verified_call(built)
    call.account([CARD])
    _, first = call.tool("create_promise", {"product_id": "p1", "amount": 455.2, "date": "2026-10-16"}, None, "error")
    assert first["what_to_do_next"].startswith("FAILED: the promise was NOT recorded")
    _, second = call.tool("create_promise", {"product_id": "p1", "amount": 455.2, "date": "2026-10-16"}, {"ok": False})
    assert second["data"]["what_to_do_next"].startswith("FAILED twice")
    assert call.close("promise") == ("no_promise", "service_error")


def test_one_failure_then_success_is_a_promise_and_one_failure_alone_is_not_a_service_error(built):
    call = verified_call(built)
    call.account([CARD])
    call.tool("create_promise", {"product_id": "p1", "amount": 455.2, "date": "2026-10-16"}, {"ok": False})
    assert "bb_failed_out__create_promise" not in call.state
    assert call.close("no_promise", "refused") == ("no_promise", "refused")      # retries left: not given up
    call.tool("create_promise", {"product_id": "p1", "amount": 455.2, "date": "2026-10-16"}, {"ok": True, "promise_id": "y"})
    assert call.close("no_promise", "refused") == ("promise", None)


def test_a_transfer_after_a_promise(built):
    call = verified_call(built)
    call.account([CARD])
    call.tool("create_promise", {"product_id": "p1", "amount": 455.2, "date": "2026-10-16"}, {"ok": True, "promise_id": "x"})
    call.tool("transfer_to_agent", {"queue": "restructuring"}, {"ok": True})
    assert call.close("promise") == ("transferred", "restructuring")


def test_a_failed_identity_check(built):
    call = Call(built)
    for left in (2, 1, 0):
        _, result = call.tool("verify_identity", {"field": "date_of_birth", "answer": "1/1/1990"},
                              {"ok": True, "verified": False, "all_verified": False, "wrong_answers_left": left})
    assert result["data"]["what_to_do_next"].startswith("Third wrong answer")
    assert call.close("not_reached", "unclear") == ("not_verified", "failed")


def test_a_callback_for_someone_else(built):
    call = Call(built)
    body, _ = call.tool("schedule_callback", {"date": "15 October", "time": "3pm"}, {"ok": True})
    assert body == {"date": "2026-10-15", "time": "15:00", "customer_id": "c1"}
    assert "2026-10-15 10:00-19:00" in call.state["bb_window__callback"]
    assert call.close("not_reached", "unclear") == ("not_reached", "callback")


def test_a_model_choice_is_kept_when_nothing_overrides_it(built):
    call = verified_call(built)
    call.account([CARD])
    assert call.close("paid") == ("paid", None)
    assert Call(built).close("not_reached", "wrong_number") == ("not_reached", "wrong_number")
