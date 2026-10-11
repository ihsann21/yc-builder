"""Run the kit's tools/run_cases.py with GET requests retried on a passing Freya 502/503/504 and
bank-mock connection errors retried.

During the outages of 11 October a status poll that got one 503 crashed run_cases while its simulation
kept running on Freya. Only GET is retried: a POST that failed may still have created the simulation.
Same arguments as run_cases.py; run from the kit folder.
"""
import pathlib, runpy, sys, time

KIT = pathlib.Path(__file__).resolve().parents[1] / "build-the-builder-v3" / "build-the-builder"
sys.path[:0] = [str(KIT), str(KIT / "tools")]
import freya

_api = freya.api


def api(method, path, body=None, **params):
    for wait in (15, 30, 60, 120, 0):
        try:
            return _api(method, path, body, **params)
        except RuntimeError as e:
            passing = any(f"-> {code}:" in str(e) for code in (502, 503, 504))
            if method != "GET" or not passing or not wait:
                raise
            print(f"Freya {str(e)[:80]}; retry in {wait} s", flush=True)
            time.sleep(wait)


freya.api = api

import score  # noqa: E402  (the kit's bank-mock client)
import urllib.error  # noqa: E402

_http = score.http


def http(path, body=None):
    """The bank mock's TLS connection failed now and then on 11 October (URLError, SSL); retry those."""
    for wait in (10, 20, 40, 0):
        try:
            return _http(path, body)
        except urllib.error.URLError as e:
            if isinstance(e, urllib.error.HTTPError) or not wait:
                raise
            print(f"bank mock {str(e)[:60]}; retry in {wait} s", flush=True)
            time.sleep(wait)


score.http = http
sys.argv[0] = str(KIT / "tools" / "run_cases.py")
runpy.run_path(sys.argv[0], run_name="__main__")
