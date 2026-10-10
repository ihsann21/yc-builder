"""Tested plumbing for building a Freya phone agent from a brief.

Nothing in this package knows a brief. Every holiday, band, outcome name, field name and
sentence comes in as a parameter that the builder reads from the brief and the tool API file.

Builder side (runs in the builder process):
    tools      read the tool API file (OpenAPI) and turn an operation into a Freya tool
    workflow   node, transition and condition helpers, and a static check of a workflow
    calc       code nodes: date facts and product facts
    hooks      pre and post hooks for api_call tools
    closing    the pre hook that sets the close tool's outcome from the call state
    embed      assembles runtime code + config into one snippet, and runs it locally

Runtime side (runtime/): the code that runs inside Freya's code nodes and hooks.
It imports only json, re and datetime, contains no double braces and never raises.
"""
