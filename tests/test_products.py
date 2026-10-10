import json
import random

import pytest

from builder.lib import calc, embed
from builder.lib.runtime import products
from dev.practice import (KIT_A_BANDS, KIT_A_LINE, KIT_B_BANDS, KIT_B_HEADER, KIT_B_LINE, PRACTICE_CAL,
                          PRACTICE_DATES, PRACTICE_SHAPE, PRACTICE_TYPES, PRACTICE_WINDOW, kit_code, run_kit)

# A made-up account shape: field names deliberately unlike any brief.
SHAPE = dict(list_field="accounts", id_field="ref", type_field="kind", amount_field="owed", days_field="overdue",
             item_fields=["ref", "kind", "owed", "overdue", "least", "last_digits"])
TYPES = {"store_card": {"name": "store card ending {field:last_digits}", "floor_field": "least", "floor_label": "least payment"},
         "loan": {"name": "loan", "floor_field": "least", "floor_label": "least payment"}}
BANDS = [{"name": "soft", "min": 1, "max": 10, "deadline": "limit_soft", "attempts": 1, "offers": "one offer"},
         {"name": "hard", "min": 11, "max": 60, "deadline": "limit_hard", "attempts": 2, "offers": "two offers up to {deadline}"}]
LINE = "{id}: {name}, owes {full} ({days} days, band {band}, floor {floor} {floor_label}, by {deadline_spoken} = {deadline}). {offers}"
ITEMS = [{"ref": "a1", "kind": "store_card", "owed": 120.5, "overdue": 3, "least": 20, "last_digits": "9911"},
         {"ref": "a2", "kind": "loan", "owed": "300", "overdue": 40, "least": "75.5"}]
DATES = {"bb_date__limit_soft": "2030-01-20", "bb_date__limit_soft__spoken": "Sunday 20 January 2030",
         "bb_date__limit_hard": "2030-01-10", "bb_date__limit_hard__spoken": "Thursday 10 January 2030"}


def code(**overrides) -> str:
    cfg = dict(SHAPE, sources=["accounts", "fetch_response.data.accounts"], types=TYPES, bands=BANDS,
               header="ACCOUNTS ({count}):", line=LINE)
    cfg.update(overrides)
    return calc.products_code(**cfg)


def run(state: dict, **overrides) -> dict:
    return embed.run(code(**overrides), state=dict(DATES, **state))


EXPECTED = ("ACCOUNTS (2):\n"
            "a1: store card ending 9911, owes 120.50 (3 days, band soft, floor 20.00 least payment, by Sunday 20 January 2030 = 2030-01-20). one offer\n"
            "a2: loan, owes 300.00 (40 days, band hard, floor 75.50 least payment, by Thursday 10 January 2030 = 2030-01-10). two offers up to 2030-01-10")


@pytest.mark.parametrize("state", [
    {"accounts": ITEMS},                                                  # mapped variable holding a list
    {"accounts": json.dumps(ITEMS)},                                      # ... or a JSON string
    {"fetch_response": {"data": {"accounts": ITEMS}}},                    # nested response object
    {"fetch_response.data.accounts": json.dumps(ITEMS)},                  # flattened key holding JSON
    {"fetch_response.data.accounts.0.ref": "a1", "fetch_response.data.accounts.0.kind": "store_card",
     "fetch_response.data.accounts.0.owed": 120.5, "fetch_response.data.accounts.0.overdue": 3,
     "fetch_response.data.accounts.0.least": 20, "fetch_response.data.accounts.0.last_digits": "9911",
     "fetch_response.data.accounts.1.ref": "a2", "fetch_response.data.accounts.1.kind": "loan",
     "fetch_response.data.accounts.1.owed": "300", "fetch_response.data.accounts.1.overdue": 40,
     "fetch_response.data.accounts.1.least": "75.5"},                   # one flattened key per field
    {"other_node_response": {"data": {"accounts": ITEMS}}},               # not in sources: found by the scan
    {"x.accounts.0.ref": "a1", "x.accounts.0.kind": "store_card", "x.accounts.0.owed": 120.5,
     "x.accounts.0.overdue": 3, "x.accounts.0.least": 20, "x.accounts.0.last_digits": "9911",
     "x.accounts.1.ref": "a2", "x.accounts.1.kind": "loan", "x.accounts.1.owed": "300",
     "x.accounts.1.overdue": 40, "x.accounts.1.least": "75.5"},          # flattened under an unknown name
])
def test_finds_the_list_wherever_the_engine_put_it(state):
    out = run(state)
    assert out["bb_account_state"] == "ok"
    assert out["account_facts"] == EXPECTED
    assert out["bb_products"] == "a1,a2" and out["bb_product_count"] == 2 and out["bb_single_product"] == ""


def test_per_product_state():
    out = run({"accounts": ITEMS})
    assert out["bb_deadline__a2"] == "2030-01-10" and out["bb_band__a1"] == "soft"
    assert out["bb_floor__a2"] == "75.5" and out["bb_full__a1"] == 120.5 and out["bb_days__a2"] == 40
    assert out["bb_type__a1"] == "store_card" and out["bb_name__a1"] == "store card ending 9911"


def test_single_product_unknown_type_and_a_value_outside_every_band():
    item = {"ref": "z9", "kind": "lease", "owed": 10, "overdue": 99}
    out = run({"accounts": [item]}, default_type={"name": "{type_words} account"})
    assert out["bb_single_product"] == "z9" and out["bb_name__z9"] == "lease account"
    assert out["bb_band__z9"] == "hard" and out["bb_deadline__z9"] == "2030-01-10"   # nearest band, never blank
    assert out["bb_floor__z9"] == ""
    assert run({"accounts": [dict(item, overdue=0)]})["bb_band__z9"] == "soft"


def test_empty_and_broken_inputs():
    assert run({}, empty="NONE")["account_facts"] == "NONE"
    assert run({}, empty="NONE")["bb_account_state"] == "empty"
    out = run({"accounts": "not json"}, empty="NONE")
    assert out["bb_account_state"] == "empty" and out["bb_products"] == ""


def test_fallback_when_the_runtime_fails():
    state = {"accounts": ITEMS}
    products.run_products(state, {"sources": ["accounts"], "fallback": "BROKEN"})   # cfg lacks the field names
    assert state["bb_account_state"] == "error" and state["account_facts"] == "BROKEN"
    assert "bb_account_error" in state


def test_odd_values_do_not_break_the_facts():
    out = run({"accounts": [{"ref": "a1", "kind": "loan", "owed": "n/a", "overdue": {"x": 1}}]})
    assert out["bb_account_state"] == "ok" and out["bb_band__a1"] == ""
    assert "a1: loan, owes n/a" in out["account_facts"]


@pytest.mark.parametrize("bad", [
    dict(sources=[]),
    dict(id_field=""),
    dict(bands=[{"name": "a", "min": 5, "max": 1}]),
    dict(bands=[{"name": "a", "min": 1, "max": 10}, {"name": "b", "min": 10, "max": 20}]),
    dict(line="{nonsense}"),
    dict(line="{field:not_an_item_field}"),
    dict(header="{{count}}"),
    dict(types={"loan": {"name": "loan", "floor_field": "missing_field"}}),
])
def test_rejects_bad_config(bad):
    with pytest.raises(ValueError):
        code(**bad)


def test_date_names_are_checked_when_known():
    with pytest.raises(ValueError):
        code(known_dates=("limit_soft",))           # band "hard" names limit_hard
    assert code(known_dates=("limit_soft", "limit_hard"))


def test_product_sources():
    assert calc.product_sources("load", "fetch", "accounts", "accounts") == [
        "accounts", "load_response.data.accounts", "fetch_response.data.accounts"]
    assert calc.product_sources("load", "fetch", "accounts") == [
        "load_response.data.accounts", "fetch_response.data.accounts"]


# --- the kit's working builder wrote this by hand for Brief A and Brief B; ours must say the same ---


def random_items(rng: random.Random, count: int) -> list[dict]:
    items = []
    for index in range(count):
        kind = rng.choice(list(PRACTICE_TYPES))
        item = {"product_id": "p" + str(index + 1), "type": kind, "past_due": round(rng.uniform(50, 3000), 2),
                "days_late": rng.randint(1, 45)}
        if kind == "credit_card":
            item.update(card_last4=str(rng.randint(1000, 9999)), minimum_payment=round(rng.uniform(10, 200), 2))
        else:
            item["instalment_amount"] = round(rng.uniform(50, 900), 2)
        items.append(item)
    return items


@pytest.mark.parametrize("brief,line,bands,header,max_items", [
    ("a", KIT_A_LINE, KIT_A_BANDS, "", 1),
    ("b", KIT_B_LINE, KIT_B_BANDS, KIT_B_HEADER, 3),
])
def test_same_facts_as_the_kit_account_code(kit, brief, line, bands, header, max_items):
    kit_setup, kit_account = kit_code(kit, brief, "setup"), kit_code(kit, brief, "account_facts")
    our_setup = calc.dates_code(calendar=PRACTICE_CAL, dates=PRACTICE_DATES, windows=[PRACTICE_WINDOW])
    our_account = calc.products_code(sources=calc.product_sources("load_account", "get_account", "products", "products"),
                                     types=PRACTICE_TYPES, bands=bands, header=header, line=line, **PRACTICE_SHAPE)
    rng = random.Random(7)
    for now in ("2026-10-14T11:00", "2026-10-16T09:00", "2026-12-23T15:30", "2027-01-02T10:00"):
        for trial in range(40):
            items = random_items(rng, rng.randint(1, max_items))
            k = run_kit(kit_account, state=run_kit(kit_setup, state={"now": now, "products": items}))
            o = embed.run(our_account, state=embed.run(our_setup, state={"now": now, "products": items}))
            assert o["account_facts"] == k["account_facts"], (now, items)
            for item in items:
                pid = item["product_id"]
                kit_deadline = k.get("deadline_" + pid, k.get("deadline_p"))
                assert o["bb_deadline__" + pid] == kit_deadline


def test_deadline_shifts_placeholder():
    shifts = {"bb_shifts__limit_soft": "SOFT SHIFTS", "bb_shifts__limit_hard": "HARD SHIFTS"}
    state = run(dict(shifts, accounts=ITEMS), line="{id} {deadline_shifts} {shifts:limit_soft}")
    assert state["account_facts"].splitlines()[1:] == ["a1 SOFT SHIFTS SOFT SHIFTS", "a2 HARD SHIFTS SOFT SHIFTS"]


def test_computed_floor_percent_min_and_cap():
    types = {"store_card": {"name": "card", "floor_percent": 10, "floor_min": 15, "floor_label": "ten percent"},
             "loan": {"name": "loan", "floor_percent": 12.5, "floor_label": "an eighth"}}
    items = [{"ref": "a1", "kind": "store_card", "owed": 120.5, "overdue": 3},     # 12.05 -> raised to 15
             {"ref": "a2", "kind": "loan", "owed": "300.04", "overdue": 40},     # 37.505 -> 37.51 (half up)
             {"ref": "a3", "kind": "store_card", "owed": 9, "overdue": 3}]       # min 15 > owed -> 9
    state = run({"accounts": items}, types=types, line="{id} {floor} {floor_label}")
    assert state["account_facts"].splitlines()[1:] == ["a1 15.00 ten percent", "a2 37.51 an eighth", "a3 9.00 ten percent"]
    assert state["bb_floor__a2"] == 37.51


@pytest.mark.parametrize("bad", [{"floor_percent": 0}, {"floor_percent": 150}, {"floor_percent": "10"},
                                 {"floor_min": -1}, {"floor_min": True}])
def test_computed_floor_options_are_checked(bad):
    with pytest.raises(ValueError):
        code(types={"loan": dict({"name": "loan"}, **bad)})
