"""Code that runs inside Freya (code nodes and api_call hooks).

Rules for every module here, checked by tests/test_runtime_rules.py:
- imports: json, re, datetime, and sibling runtime modules marked "# embed: drop";
- no double braces anywhere, no f-strings, no names that start with an underscore;
- top level holds only imports, constants and function definitions;
- entry functions catch every exception and write a fallback state.
"""
