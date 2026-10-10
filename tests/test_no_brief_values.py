"""Hard rule: no value, rule or name from a brief or its tool API file is written into builder/.

The tokens are read from the practice briefs and tool API file at test time, so the check grows
with them. Exceptions: the seven tool names (fixed by the organisers) and our own vocabulary.
"""
import ast
import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILDER = ROOT / "builder"
TOOL_NAMES = {"verify_identity", "get_account", "create_promise", "add_note", "schedule_callback",
              "transfer_to_agent", "close_call"}
# Words that are also our own vocabulary (normalize kinds, message keys, JSON-schema and workflow keys,
# the closing rule language, the runtime module "products") or event-level knowledge: the challenge
# page gives every agent `now`, and the kit README says final customers have "up to three products".
OUR_WORDS = {"date", "time", "text", "amount", "ok", "error", "type", "outcome", "reason", "now", "field",
             "answer", "products", "YYYY-MM-DD", "true", "false"}
EXTRA_PHRASES = ["Freya Bank", "Have a good day"]       # the bank's name; the kit builder's closing phrase


def openapi_tokens(node, out):
    """Every property name and enum value in a JSON schema tree."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                out.update(value)
            if key == "enum" and isinstance(value, list):
                out.update(str(v) for v in value)
            openapi_tokens(value, out)
    elif isinstance(node, list):
        for value in node:
            openapi_tokens(value, out)


@pytest.fixture
def brief_tokens(kit):
    texts = [(kit / "briefs" / name).read_text(encoding="utf-8") for name in ("brief-a.md", "brief-b.md")]
    words = set()
    for text in texts:
        for chunk in re.findall(r"`([^`]+)`", text):
            words.update(re.findall(r"[A-Za-z0-9_.]+", chunk))
    openapi_tokens(json.loads((kit / "tools" / "openapi.json").read_text(encoding="utf-8")), words)
    words -= TOOL_NAMES | OUR_WORDS
    dates = set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", "\n".join(texts)))
    phrases = {q for text in texts for q in re.findall(r"\"([^\"]+)\"", text) if len(q.split()) >= 4}
    distinctive = {w for w in words if ("_" in w or re.search(r"\d", w)) and len(w) >= 4}
    single = {w for w in words - distinctive if w.isalpha()}
    return distinctive | dates, phrases | set(EXTRA_PHRASES), single


def builder_files():
    """Code, prompts and skills under builder/ (the generated work folder is not ours)."""
    files = list(BUILDER.rglob("*.py")) + list(BUILDER.rglob("*.md"))
    return sorted(f for f in files if "work" not in f.relative_to(BUILDER).parts)


def test_there_are_builder_files_to_check():
    assert len(builder_files()) >= 8


def test_no_identifier_date_or_sentence_from_a_brief(brief_tokens):
    distinctive, phrases, single = brief_tokens
    assert {"date_of_birth", "not_reached", "2026-10-26"} <= distinctive          # the extraction works
    assert any("text message" in p for p in phrases) and "paid" in single
    hits = []
    for path in builder_files():
        text = path.read_text(encoding="utf-8")
        for token in distinctive:
            if re.search(r"(?<![A-Za-z0-9_])" + re.escape(token) + r"(?![A-Za-z0-9_])", text):
                hits.append((path.relative_to(ROOT).as_posix(), token))
        for phrase in phrases:
            if phrase.lower() in text.lower():
                hits.append((path.relative_to(ROOT).as_posix(), phrase))
    assert hits == []


def test_no_single_word_value_from_a_brief_as_a_string_constant(brief_tokens):
    single = brief_tokens[2]
    hits = []
    for path in [f for f in builder_files() if f.suffix == ".py"]:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in single:
                hits.append((path.relative_to(ROOT).as_posix(), node.lineno, node.value))
    assert hits == []


def test_no_brief_date_in_words(kit):
    """A brief's dates also as spoken in prompts: '26 October', 'October 26'."""
    import datetime
    texts = "\n".join((kit / "briefs" / name).read_text(encoding="utf-8") for name in ("brief-a.md", "brief-b.md"))
    forms = set()
    for iso in set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", texts)):
        day = datetime.date.fromisoformat(iso)
        month = day.strftime("%B")
        forms.update({str(day.day) + " " + month, month + " " + str(day.day)})
    assert "26 October" in forms                                                      # the extraction works
    hits = []
    for path in builder_files():
        text = path.read_text(encoding="utf-8")
        for form in forms:
            if re.search(r"(?<![0-9])" + re.escape(form) + r"(?![0-9])", text):
                hits.append((path.relative_to(ROOT).as_posix(), form))
    assert hits == []
