"""Open a practice-bank session for one case and print the call variables to paste into a dashboard test call.

    source build-the-builder-v3/build-the-builder/env.sh
    python scripts/new_session.py PUB-01

Each session is single use: open a new one for every manual test call.
"""
import json
import pathlib
import sys

KIT = pathlib.Path(__file__).resolve().parent.parent / "build-the-builder-v3" / "build-the-builder"
sys.path.insert(0, str(KIT / "tools"))
from score import http  # noqa: E402


def main(case_id: str) -> None:
    cases = {c["id"]: c for c in json.loads((KIT / "public-test-set.json").read_text(encoding="utf-8"))}
    if case_id not in cases:
        sys.exit(f"unknown case {case_id}; one of: {', '.join(cases)}")
    session = http("/v1/practice/sessions", {"case": case_id})
    if "variables" not in session:
        sys.exit(f"bank refused the session: {session}")
    print("Call variables:")
    print(json.dumps(session["variables"], indent=1))
    print("\nSecurity answers for this customer:")
    for field, value in cases[case_id]["identity"].items():
        print(f"  {field}: {value}")
    print("\nCustomer script:", cases[case_id]["script"])


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
