from builder.lib.runtime import common


def test_lookup_flat_nested_mixed_and_json_strings():
    state = {
        "a.b.c": 1,
        "tool_response": {"data": {"items": [{"id": "x"}]}},
        "flat.data": '{"k": [10, 20]}',
    }
    assert common.lookup(state, "a.b.c") == 1
    assert common.lookup(state, "tool_response.data.items.0.id") == "x"
    assert common.lookup(state, "flat.data.k.1") == 20
    assert common.lookup(state, "missing.key") is None
    assert common.lookup("not a dict", "a") is None


def test_lookup_prefers_longest_flat_prefix():
    state = {"r.data": {"v": "deep"}, "r": {"data": {"v": "shallow"}}}
    assert common.lookup(state, "r.data.v") == "deep"


def test_truthiness_accepts_both_spellings():
    assert common.is_true("True") and common.is_true("true") and common.is_true(True)
    assert not common.is_true("yes") and not common.is_true(1)
    assert common.is_false("False") and common.is_false(False)
    assert common.is_missing(None) and common.is_missing("  ") and not common.is_missing(0)


def test_numbers_and_text():
    assert common.to_float("2.5") == 2.5 and common.to_float(True) is None
    assert common.to_int("3.9") == 3 and common.to_int("x", default=-1) == -1
    assert common.money("45") == "45.00" and common.money("n/a") == "n/a"
    assert common.as_text(3.0) == "3" and common.as_text(None) == "" and common.as_text(False) == "false"


def test_check_operators():
    c = common.check
    assert c("True", "true") and c("false", "false") and c("", "missing") and c("x", "present")
    assert c("2", "equals", 2) and c("a", "not_equals", "b") and not c(None, "equals", "")
    assert c("b", "in", ["a", "b"]) and c("c", "not_in", ["a", "b"]) and c("Hello", "contains", "ELL")
    assert c("0", "lte", 0) and c(1, "gt", "0") and not c("x", "lt", 1) and c(5, "gte", 5) and c(1, "lt", 2)
    assert not c("x", "unknown-op")


def test_holds_fill_and_csv():
    data = {"left": "1", "ok": "true"}
    assert common.holds([["ok", "true"], ["left", "lte", 1]], data.get)
    assert not common.holds([["ok", "false"]], data.get)
    assert common.fill("left {left}, {nothing}!", data.get) == "left 1, !"
    assert common.split_csv(" a, ,b ") == ["a", "b"]
    assert common.add_csv("a,b", "b") == "a,b" and common.add_csv("", "c") == "c"
    assert common.var_key("p-1 x") == "p_1_x"
