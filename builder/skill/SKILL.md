# Build a Freya phone agent from a bank's brief with builder/lib

You are the builder. You get one or more brief files and a tool API file (OpenAPI). You produce one
Freya workflow (the phone agent) that follows the brief exactly. Nobody fixes it after you.

The plumbing is written and tested in `builder/lib`: date and product code nodes, tool hooks, the
close hook, tool JSON from the OpenAPI file, node helpers and a static check. You do not write code
that runs inside Freya. You read the brief, turn every rule into configuration for these functions,
write the prompts, and assemble the workflow.

## Hard rules

- Never read `env.sh`, print environment variables or keys. (Such tool calls are refused.)
- Every value comes from the brief or the tool API file given to you: holidays, workdays, deadlines,
  bands, limits, attempt counts, identity questions, outcome and reason names, queues, sentences the
  customer must hear, the closing phrase. Do not reuse values from any other brief or example.
- Do not open `dev/`, `tests/`, the kit's `out/`, `public-test-set.json`, `results/` or `traces/`.
- Tool names, field names, types and enums come from the OpenAPI file through `builder.lib.tools`.
  Never hand-write tool JSON.
- Read the whole brief. Most failures come from one skipped rule. When the brief is raw bank
  material (mail, policy extract, memo, code list), the memo's change wins over the older text and
  the code list gives the outcome and reason names.

## Steps

1. Read the brief file(s) completely. Print the tool API:
   `python3 -c "from builder.lib import tools; o,w=tools.operations(tools.load_api('API')); print(tools.describe(o)); print(w)"`
2. Write down, in a short list in `WORK/notes.md`, every rule of the brief and where it goes:
   a config value, a hook message, a route, or a sentence in a node's task message.
3. Copy the template below to `WORK/gen.py` and fill every `FILL` from the brief. Keep a comment with
   the brief's rule number next to each value.
4. Run `python3 WORK/gen.py`. It checks the workflow and runs the code nodes locally on a sample call;
   read its output (date facts, product facts) and fix wrong values.
5. Save: `python3 -m builder.save SLOT WORK/workflow.json CALL,VARIABLES,FROM,THE,BRIEF`.
   It runs the static check, a dry run on Freya, saves and publishes, and reads the result back.
   Save a first complete version early.
6. Test. If the task says practice customers exist, run the given `run_cases.py` command in the
   foreground and wait for it (3 to 11 minutes). Read each FAIL and its reason, fix the generator,
   save again. At most two fix rounds. Without practice customers, re-read the brief rule by rule
   against `WORK/notes.md` and the prompts once, and fix what is missing.
7. Finish with one line: workflow_id, agent_id, and the last test result.

## How the workflow is built (proven on the practice briefs)

- `setup` (code node, initial): date facts from `now` for the whole call (`calc.dates_code`).
- `greet` (conversation): fixed opening line; who is on the line (extraction enum); callback for
  someone else; tools: the callback tool and the end_call tool only.
- `identity` (conversation): ask the security questions one at a time; tools: the identity tool,
  the transfer tool (a customer insisting on a human), end_call. Leave on the identity result:
  `wf.any_of(wf.when_true("<identity tool>_response.data.<all-verified field>"), wf.when_equals("bb_identity", "verified"))`.
- `load_account` (api_request): the account lookup, mapping `data.<list field>` to a variable.
- `account_facts` (code node): product facts (`calc.products_code`).
- `negotiate` (conversation): state the debt, get promises, notes, transfers; write tools + end_call.
- The close tool is a workflow-level `end_of_call` lifecycle tool whose pre hook is `closing.close_hook`.
- Prompts: the system prompt holds the identity, tone, hard rules that hold in every step, and
  `{{date_facts}}`. It must say: obey the `what_to_do_next` field of every tool result; after every
  tool result speak or call the next tool; never say something is recorded unless the tool result
  says it worked. Each node's task message covers only that step: its rules from the brief, with
  every sentence the brief makes mandatory quoted exactly, and which tool to call when. Never name
  other nodes or describe routing in a task message.
- End the call with the end_call tool: the assistant says the closing phrase, which triggers it.
- Route on tool results and code flags, never on what the customer says, except who answered the phone.

## builder/lib in one page

```python
from builder.lib import calc, closing, hooks, tools, workflow as wf
ops, warnings = tools.operations(tools.load_api(API)); op = ops["<tool>"]
tools.api_tool(op, description=TEXT, bake={"<field>": "{{<call variable>}}"}, notes={"<field>": TEXT},
               pre=CODE, post=CODE, retries=0, mapping=[("data.<field>", "<var>")], lifecycle="end_of_call")
tools.end_call_tool(description=TEXT, trigger_phrase=PHRASE, polite_replies=[...])
calc.dates_code(calendar={"workdays": [0, 1, 2, 3, 4], "holidays": ["YYYY-MM-DD", ...]},
                dates=[{"name": N, "rule": R, ...params, "label": TEXT}],   # bb_date__N, bb_date__N__spoken
                windows=[{"name": N, "days": [rules], "from": "HH:MM", "to": "HH:MM", "after_now": True,
                          "var": "<var for the prompt>", "label": TEXT}],
                weekday_mode="following_week" | "first_after_today" | "", calendar_days=40)
#   rules: today | next_business_day | business_days_after n | calendar_days_after n (+roll)
#          | end_of_month months_ahead (+roll) | last_business_day_of_week (weeks_ahead, after_today)
calc.products_code(sources=calc.product_sources(NODE, LOOKUP_TOOL, LIST_FIELD, MAPPED_VAR),
                   list_field=..., id_field=..., type_field=..., amount_field=..., days_field=...,
                   item_fields=[every item field], types={TYPE: {"name": "...{field:F}...",
                   "floor_field": F, "floor_label": TEXT}}, bands=[{"name", "min", "max", "deadline": DATE_NAME,
                   "attempts": N, "offers": TEMPLATE}], line=TEMPLATE, header="...{count}...",
                   known_dates=(...DATE_NAMEs))
#   placeholders: {id} {name} {full} {floor} {floor_label} {days} {band} {deadline} {deadline_spoken}
#   {attempts} {offers} {field:F} {date:N} {date_spoken:N}; writes bb_products, bb_deadline__<id>, ...
hooks.pre_hook(TOOL, normalize={FIELD: {"kind": "date", "order": "DMY"} | {"kind": "digits", "last": 4}
               | {"kind": "time"} | {"kind": "amount"} | {"by": OTHER_FIELD, "cases": {VALUE: SPEC}}},
               refs=[ID_FIELD], key_field=ID_FIELD,
               guard={DATE_FIELD: {"min": "today", "max_var": "bb_deadline__{key}", "calendar": CAL, "roll": "forward"}})
hooks.post_hook(TOOL, rules=[{"when": [[F, "true"|"false"|"missing"|"present"|"equals"|"lte"|..., V]],
                "say": TEXT, "set": {"bb_identity": "verified"}}], messages={"ok", "retry", "give_up",
                "error", "default": TEXT}, ok_when=[[F, "true"], ...], key_field=F, retries=N,
                fail_mark=[F, False], log_fields=[F])
closing.close_hook(outcome_field=F, reason_field=F, outcomes={OUTCOME: [REASONS] or []},
                   rules=[{"if": [[FACT, OP, V]], "outcome": O, "reason": R | {"fact": FACT, "map": {...}}
                          | {"first_logged": "TOOL.FIELD", "skip": [...]} | {"model": True}}, {"keep_model": True}],
                   default={"outcome": O, "reason": R})
#   facts: count:TOOL  gave_up:TOOL  last:TOOL.FIELD  logged:TOOL.FIELD  all_logged:TOOL.FIELD
#          var:NAME (e.g. var:bb_identity)  model:outcome  model:reason
wf.code_node(NAME, CODE, NEXT); wf.api_request_node(NAME, TOOL, NEXT, mapping=[...])
wf.conversation_node(NAME, task=TEXT, tools=[...], transitions=[...], on_enter=wf.say(TEXT) | wf.llm(TEXT),
                     extraction=[wf.extract(NAME, "string", TEXT, enum=[...], min_confidence=0.7)], max_turns=60)
wf.transition(TARGET, TEXT, wf.when_equals(VAR, V) | wf.when_true(VAR) | wf.any_of(...))
wf.workflow(initial=..., nodes={...}, system_prompt=TEXT, tools=[close tool], test_variables={...})
wf.check(workflow, CALL_VARIABLES)    # [] or problems; builder.save runs it too
```

Track every write tool with a post hook (`ok_when` from the tool's success field), give it a pre hook
too (the pre hook records the request the post hook and the close hook read). Retries: what the
brief allows after a failed write. The hook messages are the next step the brief prescribes after
that result, including any sentence the customer must hear.

## Template: WORK/gen.py

```python
"""Generator for SLOT. Every value below comes from the brief (rule numbers in comments)."""
import json, pathlib, sys
sys.path.insert(0, "REPO")                      # FILL: the repo root
from builder.lib import calc, closing, embed, hooks, tools, workflow as wf

WORK = pathlib.Path(__file__).resolve().parent
API = "API"                                     # FILL: the tool API file
CALL_VARIABLES = ("FILL",)                      # the call variables the brief lists
SAMPLE_CALL = {"FILL": "FILL"}                  # a sample of those variables (now from the brief's example)
CAL = {"workdays": [FILL], "holidays": [FILL]}
DATES = [FILL]                                  # named dates: deadlines, offer dates
WINDOWS = [FILL]                                # e.g. the callback window, or []
BANDS = [FILL]
TYPES = {FILL}
OUTCOMES = {FILL}                               # outcome enum from the API, reasons from the brief
CLOSE_RULES = [FILL]                            # brief's closing table, in priority order, then {"keep_model": True}
DEFAULT = {FILL}

ops, warnings = tools.operations(tools.load_api(API))
assert not warnings, warnings

SYSTEM = """FILL"""
GREET = """FILL"""
IDENTITY = """FILL"""
NEGOTIATE = """FILL"""

# FILL: tools (tools.api_tool with hooks), the end_call tool, the code snippets, the nodes, then:
workflow = wf.workflow(initial="setup", nodes=NODES, system_prompt=SYSTEM, tools=[CLOSE_TOOL],
                       test_variables=SAMPLE_CALL)
problems = wf.check(workflow, CALL_VARIABLES)
print("check:", problems or "ok")
(WORK / "workflow.json").write_text(json.dumps(workflow, indent=1), encoding="utf-8")

# Local test of the code nodes on the sample call (shown in the trace):
state = embed.run(DATES_CODE, state=dict(SAMPLE_CALL))
print(state["date_facts"][:1500])
state[MAPPED_VAR] = [FILL]                      # one or two sample products with the API's fields
embed.run(PRODUCTS_CODE, state=state)
print(state["account_facts"])
```
