"""Read the tool API file (OpenAPI) and turn its operations into Freya tools.

Nothing here knows a particular API: names, fields, types and allowed values all come from the
file, and every choice a builder makes (descriptions, baked values, hooks) comes in as a parameter.
Parsing is best effort: an unexpected shape becomes a warning, never an exception.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
from dataclasses import dataclass

HTTP_METHODS = ("get", "post", "put", "patch", "delete")
LIFECYCLES = ("start_of_call", "end_of_call")
API_CALL = "__function__:api_call"
END_CALL = "__function__:end_call"
COMPOSITIONS = ("allOf", "oneOf", "anyOf")
MAX_REF_EXPANSIONS = 5000  # per operation; bounds the work on a pathological file
_NESTING_KEYS = ("$ref", "properties", "items") + COMPOSITIONS
_TOOL_NAME = re.compile(r"[A-Za-z0-9_-]+")
_TYPED_ENUM_TYPES = ("integer", "number", "boolean")


@dataclass(frozen=True)
class Field:
    """One property of a request or response body schema."""

    name: str
    type: str = ""  # JSON-schema type, "" if absent and not implied by properties or items
    description: str = ""
    enum: tuple[str, ...] = ()
    format: str = ""
    required: bool = False
    fields: tuple["Field", ...] = ()  # object properties, or the item properties of an array of objects
    item_type: str = ""  # for arrays: the item type


@dataclass(frozen=True)
class Operation:
    """One HTTP operation of the tool API."""

    name: str  # the path without its leading slash
    method: str  # upper case
    url: str  # servers[0].url without a trailing slash, plus the path; just the path if no servers
    summary: str
    description: str
    request: tuple[Field, ...]  # top-level JSON body properties, required flags set
    response: tuple[Field, ...]  # properties of the 200 (or first 2xx) JSON response schema, nested
    other_responses: tuple[tuple[str, str], ...]  # (status code, description) for non-2xx


# ---------------------------------------------------------------- reading


def load_api(path: str | os.PathLike[str]) -> dict:
    """Read a JSON tool API file. Raises ValueError when it is not a JSON object."""
    text = pathlib.Path(path).read_text(encoding="utf-8-sig")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path}: a tool API file must hold a JSON object")
    return data


def operations(api: dict) -> tuple[dict[str, Operation], list[str]]:
    """Every get/post/put/patch/delete operation by name, and the warnings met on the way."""
    return _Reader(api).read()


def field(op: Operation, name: str) -> Field:
    """The request field `name` of `op`. Raises KeyError naming the known request fields."""
    for candidate in op.request:
        if candidate.name == name:
            return candidate
    known = ", ".join(f.name for f in op.request) or "none"
    hint = " (it is a response field: read op.response)" if any(f.name == name for f in op.response) else ""
    raise KeyError(f"{op.name} has no request field {name!r}{hint}; known request fields: {known}")


def enum(op: Operation, name: str) -> tuple[str, ...]:
    """The allowed values of request field `name`; empty when the field has no enum."""
    return field(op, name).enum


class _Reader:
    """One pass over an OpenAPI document. Collects warnings instead of raising."""

    def __init__(self, api: object) -> None:
        self.api = api
        self.warnings: list[str] = []
        self.expansions = 0

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def read(self) -> tuple[dict[str, Operation], list[str]]:
        if not isinstance(self.api, dict):
            return {}, ["the tool API is not a JSON object"]
        paths = self.api.get("paths")
        if not isinstance(paths, dict) or not paths:
            return {}, ["the tool API has no paths"]
        base = self.server_url(self.api.get("servers"), "the tool API")
        if base is None:
            self.warn("the tool API has no servers[0].url: tool urls are bare paths")
            base = ""
        ops: dict[str, Operation] = {}
        for path, item in paths.items():
            for op in self.path_operations(str(path), item, base):
                if op.name in ops:
                    self.warn(f"{op.method} {path}: the name {op.name!r} is taken by an earlier operation; skipped")
                else:
                    ops[op.name] = op
        return ops, self.warnings

    def server_url(self, servers: object, where: str) -> str | None:
        """servers[0].url with its variables filled from their defaults, or None when absent."""
        if servers is None or servers == []:
            return None
        first = servers[0] if isinstance(servers, list) else None
        if not isinstance(first, dict) or not isinstance(first.get("url"), str):
            self.warn(f"{where}: servers is not a list of objects with a url; ignored")
            return None
        url = first["url"]
        variables = first.get("variables")
        for name, spec in variables.items() if isinstance(variables, dict) else ():
            if isinstance(spec, dict) and "default" in spec:
                url = url.replace("{" + str(name) + "}", str(spec["default"]))
        if "{" in url:
            self.warn(f"{where}: server url {url!r} keeps an unresolved variable")
        if not url.lower().startswith(("http://", "https://")):
            self.warn(f"{where}: server url {url!r} is not absolute, so the tool urls are not either")
        return url.rstrip("/")

    def path_operations(self, path: str, item: object, base: str) -> list[Operation]:
        if not isinstance(item, dict):
            self.warn(f"path {path}: not an object; skipped")
            return []
        if "$ref" in item:
            self.warn(f"path {path}: a path item $ref is not followed; skipped")
            return []
        methods = [key for key in item if str(key).lower() in HTTP_METHODS]
        if not methods:
            self.warn(f"path {path}: no get, post, put, patch or delete operation; skipped")
            return []
        path_base = self.server_url(item.get("servers"), f"path {path}")
        result = []
        for key in methods:
            method = str(key).upper()
            where = f"{method} {path}"
            op = item[key]
            if not isinstance(op, dict):
                self.warn(f"{where}: not an object; skipped")
                continue
            op_base = self.server_url(op.get("servers"), where)
            chosen = next(b for b in (op_base, path_base, base) if b is not None)
            result.append(self.operation(path, method, op, chosen, where))
        return result

    def operation(self, path: str, method: str, op: dict, base: str, where: str) -> Operation:
        self.expansions = 0
        if not path.startswith("/"):
            path = "/" + path
        if "{" in path:
            self.warn(f"{where}: path parameters are not filled in; the url keeps {path}")
        name = path.strip("/")
        if not _TOOL_NAME.fullmatch(name):
            self.warn(f"{where}: {name!r} is not a plain tool name (letters, digits, _ and -); kept as is")
        response, others = self.responses(op, where)
        return Operation(
            name=name,
            method=method,
            url=base + path,
            summary=_text(op.get("summary")),
            description=_text(op.get("description")),
            request=self.request_fields(op, where),
            response=response,
            other_responses=others,
        )

    def request_fields(self, op: dict, where: str) -> tuple[Field, ...]:
        if op.get("parameters"):
            self.warn(f"{where}: parameters are not read; only a JSON request body becomes tool fields")
        if op.get("requestBody") is None:
            return ()
        body, _ = self.resolve(op["requestBody"], (), f"{where} requestBody")
        return self.body_fields(body.get("content"), f"{where} request")

    def responses(self, op: dict, where: str) -> tuple[tuple[Field, ...], tuple[tuple[str, str], ...]]:
        responses = op.get("responses")
        if responses is None:
            return (), ()
        if not isinstance(responses, dict):
            self.warn(f"{where}: responses is not an object; ignored")
            return (), ()
        codes = [str(code) for code in responses]
        success = "200" if "200" in codes else next((c for c in codes if c.startswith("2")), None)
        fields: tuple[Field, ...] = ()
        others: list[tuple[str, str]] = []
        for key, value in responses.items():
            code = str(key)
            resp, _ = self.resolve(value, (), f"{where} response {code}")
            if code == success and "content" in resp:
                fields = self.body_fields(resp["content"], f"{where} response {code}")
            elif not code.startswith("2"):
                others.append((code, _text(resp.get("description"))))
        return fields, tuple(others)

    def body_fields(self, content: object, where: str) -> tuple[Field, ...]:
        """The properties of the JSON schema in a content map."""
        schema = self.json_schema(content, where)
        if schema is None:
            return ()
        schema, chain = self.resolve(schema, (), where)
        if _schema_type(schema) != "object":
            self.warn(f"{where}: the body is not a JSON object; no fields read")
            return ()
        return self.read_fields(schema, chain, where)

    def json_schema(self, content: object, where: str) -> object | None:
        if not isinstance(content, dict) or not content:
            self.warn(f"{where}: no content; no fields read")
            return None
        json_keys = [key for key in content if _is_json(str(key))]
        for key in content:
            if key not in json_keys:
                self.warn(f"{where}: content {key!r} is not JSON; ignored")
        if not json_keys:
            return None
        key = "application/json" if "application/json" in json_keys else json_keys[0]
        media = content[key]
        if not isinstance(media, dict) or "schema" not in media:
            self.warn(f"{where}: content {key!r} has no schema; no fields read")
            return None
        return media["schema"]

    def resolve(self, schema: object, chain: tuple[str, ...], where: str) -> tuple[dict, tuple[str, ...]]:
        """Follow local $refs (stopping at a cycle) and fold allOf/oneOf/anyOf into one schema."""
        while isinstance(schema, dict) and "$ref" in schema:
            ref = schema["$ref"]
            siblings = {k: v for k, v in schema.items() if k != "$ref"}
            if not isinstance(ref, str) or not ref.startswith("#/"):
                self.warn(f"{where}: $ref {ref!r} is not a local reference; ignored")
                return siblings, chain
            target = self.pointer(ref)
            if not isinstance(target, dict):
                self.warn(f"{where}: $ref {ref} not found; ignored")
                return siblings, chain
            if ref in chain:
                self.warn(f"{where}: $ref {ref} refers back to itself; its nested fields are not read again")
                return {**_shallow(target), **siblings}, chain
            self.expansions += 1
            if self.expansions > MAX_REF_EXPANSIONS:
                if self.expansions == MAX_REF_EXPANSIONS + 1:
                    self.warn(f"{where}: more than {MAX_REF_EXPANSIONS} $ref expansions; deeper refs are not read")
                return {**_shallow(target), **siblings}, chain
            chain = chain + (ref,)
            schema = {**target, **siblings}
        if not isinstance(schema, dict):
            return {}, chain
        if any(key in schema for key in COMPOSITIONS):
            schema = self.merge(schema, chain, where)
        return schema, chain

    def pointer(self, ref: str) -> object:
        """The value a local JSON pointer such as '#/components/schemas/X' names, or None."""
        node: object = self.api
        for raw in ref[2:].split("/"):
            part = raw.replace("~1", "/").replace("~0", "~")
            if isinstance(node, dict) and part in node:
                node = node[part]
            elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
                node = node[int(part)]
            else:
                return None
        return node

    def merge(self, schema: dict, chain: tuple[str, ...], where: str) -> dict:
        """allOf: union of properties and required. oneOf/anyOf: union of properties, none required.

        A part that only allows null is skipped, so a nullable field keeps its real type; a oneOf or
        anyOf left with one part is read like allOf.
        """
        properties: dict = {}
        required: list[str] = []
        inherited: dict = {}
        for key in COMPOSITIONS:
            parts = schema.get(key)
            if parts is None:
                continue
            if not isinstance(parts, list):
                self.warn(f"{where}: {key} is not a list; ignored")
                continue
            subs = []
            for part in parts:
                sub, _ = self.resolve(part, chain, where)
                if sub.get("type") != "null":
                    subs.append(sub)
            union = key != "allOf" and len(subs) > 1
            if union:
                self.warn(f"{where}: {key} is read as the union of its alternatives, with no field required")
            for sub in subs:
                if isinstance(sub.get("properties"), dict):
                    properties.update(sub["properties"])
                if not union:
                    required.extend(_strings(sub.get("required")))
                for name, value in sub.items():
                    if name not in ("properties", "required"):
                        inherited.setdefault(name, value)
        own = {k: v for k, v in schema.items() if k not in COMPOSITIONS}
        merged = {**inherited, **own}
        raw_properties = own.get("properties")
        own_properties = raw_properties if isinstance(raw_properties, dict) else {}
        if properties or own_properties:
            merged["properties"] = {**properties, **own_properties}
        all_required = list(dict.fromkeys(required + _strings(own.get("required"))))
        if all_required:
            merged["required"] = all_required
        return merged

    def read_fields(self, schema: dict, chain: tuple[str, ...], where: str) -> tuple[Field, ...]:
        properties = schema.get("properties")
        if properties is None:
            return ()
        if not isinstance(properties, dict):
            self.warn(f"{where}: properties is not an object; no fields read")
            return ()
        required = set(_strings(schema.get("required")))
        return tuple(
            self.read_field(str(name), raw, name in required, chain, f"{where}.{name}")
            for name, raw in properties.items()
        )

    def read_field(self, name: str, raw: object, required: bool, chain: tuple[str, ...], where: str) -> Field:
        if not isinstance(raw, dict):
            self.warn(f"{where}: the schema is not an object; read as an untyped field")
            raw = {}
        schema, chain = self.resolve(raw, chain, where)
        kind = _schema_type(schema)
        nested: tuple[Field, ...] = ()
        item_type = ""
        if kind == "object":
            nested = self.read_fields(schema, chain, where)
        elif kind == "array":
            items, item_chain = self.resolve(schema.get("items", {}), chain, f"{where}[]")
            item_type = _schema_type(items)
            if item_type == "object":
                nested = self.read_fields(items, item_chain, f"{where}[]")
        return Field(
            name=name,
            type=kind,
            description=_text(schema.get("description")),
            enum=self.enum_values(schema.get("enum"), where),
            format=_text(schema.get("format")),
            required=required or raw.get("required") is True,
            fields=nested,
            item_type=item_type,
        )

    def enum_values(self, values: object, where: str) -> tuple[str, ...]:
        """Enum values as text: numbers and booleans in their JSON spelling (api_tool types them
        again); null and other values are dropped with a warning."""
        if values is None:
            return ()
        if not isinstance(values, list):
            self.warn(f"{where}: enum is not a list; ignored")
            return ()
        kept = [v if isinstance(v, str) else json.dumps(v) for v in values if isinstance(v, (str, int, float))]
        dropped = [v for v in values if not isinstance(v, (str, int, float))]
        if dropped:
            self.warn(f"{where}: enum values {dropped!r} are not text, numbers or booleans; dropped")
        return tuple(kept)


def _schema_type(schema: dict) -> str:
    """The declared type (the first non-null one of a list), else object/array implied by the shape."""
    declared = schema.get("type")
    if isinstance(declared, list):
        declared = next((t for t in declared if isinstance(t, str) and t != "null"), "")
    if isinstance(declared, str) and declared:
        return declared
    if isinstance(schema.get("properties"), dict):
        return "object"
    if "items" in schema:
        return "array"
    return ""


def _shallow(schema: dict) -> dict:
    """A schema without its nested parts, keeping its type; used where a $ref cycle stops."""
    shallow = {k: v for k, v in schema.items() if k not in _NESTING_KEYS}
    kind = _schema_type(schema)
    if kind and "type" not in shallow:
        shallow["type"] = kind
    return shallow


def _is_json(media_type: str) -> bool:
    base = media_type.split(";")[0].strip().lower()
    return base == "application/json" or base.endswith("+json")


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _strings(value: object) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


# ---------------------------------------------------------------- describing


def describe(ops: dict[str, Operation]) -> str:
    """Plain-text summary of every operation, for a trace and for a model that builds the agent."""
    return "\n\n".join(_describe_operation(op) for op in ops.values())


def _describe_operation(op: Operation) -> str:
    lines = [f"{op.name}: {op.method} {op.url}"]
    if op.summary:
        lines.append(f"  summary: {_one_line(op.summary)}")
    if op.description:
        lines.append(f"  description: {_one_line(op.description)}")
    lines.append("  request body:" if op.request else "  request body: none")
    lines.extend(_describe_fields(op.request, 2))
    lines.append("  response:" if op.response else "  response: none")
    lines.extend(_describe_fields(op.response, 2))
    if op.other_responses:
        lines.append("  other responses:")
        lines.extend(f"    {code}: {_one_line(text)}" for code, text in op.other_responses)
    return "\n".join(lines)


def _describe_fields(fields: tuple[Field, ...], depth: int) -> list[str]:
    lines = []
    for f in fields:
        lines.append("  " * depth + _describe_field(f))
        lines.extend(_describe_fields(f.fields, depth + 1))
    return lines


def _describe_field(f: Field) -> str:
    kind = f.type or "untyped"
    if f.type == "array":
        kind = f"array of {f.item_type}" if f.item_type else "array"
    parts = [kind]
    if f.format:
        parts.append(f"format {f.format}")
    if f.required:
        parts.append("required")
    if f.enum:
        parts.append("one of: " + " | ".join(f.enum))
    text = f"{f.name} ({', '.join(parts)})"
    return f"{text}: {_one_line(f.description)}" if f.description else text


def _one_line(text: str) -> str:
    return " ".join(text.split())


# ---------------------------------------------------------------- building Freya tools


def api_tool(
    op: Operation,
    *,
    description: str,
    bake: dict[str, str] | None = None,
    placeholders: dict[str, str] | None = None,
    notes: dict[str, str] | None = None,
    pre: str = "",
    post: str = "",
    retries: int = 0,
    timeout_ms: int = 12000,
    mapping: list[tuple[str, str]] | None = None,
    lifecycle: str = "",
) -> dict:
    """A Freya `__function__:api_call` tool for `op`, one body leaf per request field.

    bake: field -> fixed default (a literal or a placeholder of a variable that is always set).
        A baked field is left out of body.required.
    placeholders: field -> variable name for a model-filled field (default: the field's own name).
    notes: field -> text appended to the OpenAPI description of the field.
    pre / post: hook code, written only when not blank.
    mapping: (path, variable) pairs for a tool-level response_mapping; every path starts with 'data.'.
    lifecycle: '' for a normal tool, or start_of_call / end_of_call for a lifecycle tool.
    Raises ValueError for a key that is not a request field, a field both baked and given a
    placeholder, an unknown lifecycle, or a mapping path outside 'data.'.
    """
    bake, placeholders, notes = dict(bake or {}), dict(placeholders or {}), dict(notes or {})
    _check_field_keys(op, bake=bake, placeholders=placeholders, notes=notes)
    both = [name for name in bake if name in placeholders]
    if both:
        raise ValueError(f"{op.name}: {', '.join(both)} cannot be both baked and model-filled")
    entries = _mapping_entries(mapping or [])
    tool = {
        "type": "function",
        "config": _config(timeout_ms, retries, lifecycle, bool(entries)),
        "function": {
            "name": op.name,
            "handler": API_CALL,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "default": op.url},
                    "method": {"type": "string", "default": op.method},
                    "headers": {
                        "type": "object",
                        "properties": {"Content-Type": {"type": "string", "default": "application/json"}},
                    },
                    "body": _body(op, bake, placeholders, notes),
                },
            },
        },
    }
    if pre.strip():
        tool["pre_process_code"] = pre
    if post.strip():
        tool["post_process_code"] = post
    if entries:
        tool["response_mapping"] = entries
    return tool


def _check_field_keys(op: Operation, **maps: dict[str, str]) -> None:
    known = [f.name for f in op.request]
    for what, values in maps.items():
        unknown = [key for key in values if key not in known]
        if unknown:
            raise ValueError(
                f"{what} for {op.name} names {', '.join(map(repr, unknown))}, which is not a request field; "
                f"known request fields: {', '.join(known) or 'none'}"
            )


def _config(timeout_ms: int, retries: int, lifecycle: str, has_mapping: bool) -> dict:
    if lifecycle == "each_turn":
        raise ValueError("lifecycle 'each_turn' never fires; use start_of_call or end_of_call")
    if lifecycle and lifecycle not in LIFECYCLES:
        raise ValueError(f"unknown lifecycle {lifecycle!r}; use '', start_of_call or end_of_call")
    if lifecycle == "end_of_call" and has_mapping:
        raise ValueError("response_mapping is not applied to an end_of_call tool")
    config: dict = {"timeoutMs": timeout_ms, "maxRetries": retries}
    if lifecycle:
        config["alwaysRunsAt"] = [lifecycle]
    return config


def _body(op: Operation, bake: dict[str, str], placeholders: dict[str, str], notes: dict[str, str]) -> dict:
    return {
        "type": "object",
        "required": [f.name for f in op.request if f.required and f.name not in bake],
        "properties": {f.name: _leaf(f, bake, placeholders, notes) for f in op.request},
    }


def _leaf(f: Field, bake: dict[str, str], placeholders: dict[str, str], notes: dict[str, str]) -> dict:
    """type, description (OpenAPI text plus note), enum and default; the format is not copied."""
    leaf: dict = {"type": f.type or "string"}
    text = " ".join(part for part in (f.description.strip(), notes.get(f.name, "").strip()) if part)
    if text:
        leaf["description"] = text
    if f.enum:
        leaf["enum"] = _typed_enum(f.enum, leaf["type"])
    leaf["default"] = bake[f.name] if f.name in bake else "{{" + placeholders.get(f.name, f.name) + "}}"
    return leaf


def _typed_enum(values: tuple[str, ...], kind: str) -> list:
    """The enum in the leaf's own JSON type: for number and boolean fields the text is read back."""
    if kind not in _TYPED_ENUM_TYPES:
        return list(values)
    typed: list = []
    for value in values:
        try:
            typed.append(json.loads(value))
        except ValueError:
            typed.append(value)
    return typed


def _mapping_entries(mapping: list[tuple[str, str]]) -> list[dict]:
    entries = []
    for path, variable in mapping:
        if not isinstance(path, str) or not path.startswith("data."):
            raise ValueError(
                f"response_mapping path {path!r} must start with 'data.': the API body sits under data in the result"
            )
        if not isinstance(variable, str) or not variable:
            raise ValueError(f"response_mapping for {path} needs a variable name, not {variable!r}")
        entries.append({"path": path, "variable": variable})
    return entries


def end_call_tool(
    *,
    description: str,
    trigger_phrase: str,
    polite_replies: list[str],
    timeout_ms: int = 10000,
    trigger_timeout: int = 3,
) -> dict:
    """The conversation tool that ends the call; saying `trigger_phrase` also ends it by itself.

    trigger_pattern is the phrase without a trailing period, and its lower-case form when that
    differs. trigger_pattern_both lists the replies that do not cancel the close.
    Raises ValueError for an empty phrase, no replies, or a '|' inside a phrase or a reply.
    """
    phrase = trigger_phrase.strip()
    phrase = phrase[:-1].rstrip() if phrase.endswith(".") else phrase
    replies = list(polite_replies)
    if not phrase:
        raise ValueError("trigger_phrase is empty")
    if not replies or any(not reply.strip() for reply in replies):
        raise ValueError("polite_replies needs at least one reply and no empty one")
    if any("|" in text for text in [phrase, *replies]):
        raise ValueError("'|' separates the patterns; it cannot appear inside a phrase or a reply")
    variants = [phrase] if phrase.lower() == phrase else [phrase, phrase.lower()]
    return {
        "type": "function",
        "config": {"timeoutMs": timeout_ms},
        "function": {
            "name": "end_call",
            "handler": END_CALL,
            "parameters": {
                "type": "object",
                "properties": {
                    "message_mode": {"type": "string", "default": "none"},
                    "interruptible": {"type": "boolean", "default": True},
                    "trigger_pattern": {"type": "string", "default": "|".join(variants)},
                    "trigger_timeout": {"type": "number", "default": trigger_timeout},
                    "trigger_pattern_both": {"type": "string", "default": "|".join(replies)},
                },
            },
            "description": description,
        },
    }
