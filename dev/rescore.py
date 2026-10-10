"""Score a finished or stuck simulation from Freya's calls and the bank's ledger (read only).

    python -m dev.rescore <simulation id or prefix> [--cases <file>]

A simulation can stay "running" after all its calls ended (seen when the judge returned
"inconclusive"); run_cases.py then waits forever. This reads the calls of the simulation, the ledger of
each call's customer and the judge's verdict, and scores them like run_cases.py. Dev only: it reads the
test set. Needs FREYA_API_KEY and FREYA_BANK_TEAM_KEY in the environment.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

KIT = pathlib.Path(__file__).resolve().parent.parent / "build-the-builder-v3" / "build-the-builder"
sys.path.insert(0, str(KIT))
sys.path.insert(0, str(KIT / "tools"))
import freya  # noqa: E402
from score import http, score_ledger  # noqa: E402


def customer_of(call: dict) -> str:
    """The customer_id of a call, from the variable table of its last route event."""
    found = ""
    for message in call.get("messages", []):
        if message.get("role") == "system" and "route_evaluated" in str(message.get("message", "")):
            table = json.loads(message["message"]).get("variable_table") or {}
            found = table.get("customer_id") or found
    return found


def rescore(sim_prefix: str, cases_file: str) -> tuple[int, int]:
    """Print one line per call and return (passed, total)."""
    listing = freya.api("GET", "/api/v2/simulations", workspaceId=freya.workspace_id(), limit=30)
    sims = [s for s in (listing.get("simulations") or listing.get("items") or listing) if s["id"].startswith(sim_prefix)]
    if not sims:
        raise SystemExit("no simulation " + sim_prefix)
    sim = sims[0]
    iterations = freya.api("GET", f"/api/v2/simulations/{sim['id']}/iterations")
    iterations = iterations.get("iterations") or iterations.get("items") or iterations
    runs = freya.get_iteration(sim["id"], iterations[0]["id"])["runs"]
    cases = {c["id"]: c for c in json.load(open(cases_file))}
    personas = json.load(open(KIT / ".personas.json"))
    case_of = {persona: key.split(":")[0] for key, persona in personas.items()}
    passed = 0
    print(f"simulation {sim['id']} ({sim.get('status')}, {sim.get('name')})")
    for run in sorted(runs, key=lambda r: case_of.get(r.get("personaId"), "")):
        case_id = case_of.get(run.get("personaId"), "?")
        if case_id not in cases or not run.get("callId"):
            print("SKIP", case_id, run.get("outcome"))
            continue
        ledger = http("/v1/practice/ledger/" + customer_of(freya.get_call(run["callId"])))
        result = score_ledger(cases[case_id], ledger)
        if run.get("outcome") != "pass":
            reason = " ".join(str(run.get("reason") or "no verdict").split())
            result["failed"].append(f"conversation ({run.get('outcome')}): " + reason[:330])
        ok = not result["failed"]
        passed += ok
        tools = " > ".join(x["tool"].replace("verify_identity", "verify").replace("create_promise", "promise")
                           for x in ledger["calls"])
        print("PASS" if ok else "FAIL", case_id, "|", tools)
        for line in result["failed"]:
            print("       -", line[:330])
    print(f"{passed} / {len(runs)} passed")
    return passed, len(runs)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("simulation")
    parser.add_argument("--cases", default=str(KIT / "public-test-set.json"))
    args = parser.parse_args()
    rescore(args.simulation, args.cases)
    return 0


if __name__ == "__main__":
    sys.exit(main())
