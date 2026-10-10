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
  the code list gives the outcome and reason names. Where the tool API file lists enum values, its
  spelling wins: map the code list onto the enum (close_hook with op= refuses names outside it).

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
  says it worked. The judge reads the word the brief uses for a successful write (its "saved" word)
  literally: it must not appear in any turn before the write succeeds, the opening included. Where the
  brief does not dictate the exact words, say other things with another form (if the saved word were
  "logged", the opening would say "we log this call", not "this call is logged"; a failure, "I could not
  log it"). Each node's task message covers only that step: its rules from the brief, with
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
                dates=[{"name": N, "rule": R, ...params, "label": TEXT,
                        "shifts": "forward" | "backward"}],   # bb_date__N, bb_date__N__spoken, bb_shifts__N
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
#   {deadline_shifts} {attempts} {offers} {field:F} {date:N} {date_spoken:N} {shifts:N};
#   writes bb_products, bb_deadline__<id>, ...
hooks.pre_hook(TOOL, normalize={FIELD: {"kind": "date", "order": "DMY"} | {"kind": "digits", "last": 4}
               | {"kind": "time"} | {"kind": "amount"} | {"by": OTHER_FIELD, "cases": {VALUE: SPEC}}},
               refs=[ID_FIELD], key_field=ID_FIELD,
               guard={DATE_FIELD: {"min": "today", "max_var": "bb_deadline__{key}", "calendar": CAL, "roll": "forward"}},
               op=ops[TOOL])
hooks.post_hook(TOOL, rules=[{"when": [[F, "true"|"false"|"missing"|"present"|"equals"|"lte"|..., V]],
                "say": TEXT, "set": {"bb_identity": "verified"}}], messages={"ok", "retry", "give_up",
                "error", "default": TEXT}, ok_when=[[F, "true"], ...], key_field=F, retries=N,
                fail_mark=[F, False], log_fields=[F], op=ops[TOOL])
#   message placeholders: {key} {tries} {retries_left} {adjusted} {open:TOOL:TOOL} (products not yet
#   written by any of those tools, or "none") and any response field or variable
closing.close_hook(outcome_field=F, reason_field=F, outcomes={OUTCOME: [REASONS] or []},
                   rules=[{"if": [[FACT, OP, V]], "outcome": O, "reason": R | {"fact": FACT, "map": {...}}
                          | {"first_logged": "TOOL.FIELD", "skip": [...]} | {"model": True}}, {"keep_model": True}],
                   default={"outcome": O, "reason": R}, op=ops[CLOSE_TOOL])
#   always pass op=: every field and outcome/reason name is then checked against the tool API file
#   facts: count:TOOL  gave_up:TOOL  last:TOOL.FIELD  logged:TOOL.FIELD  all_logged:TOOL.FIELD
#          var:NAME (e.g. var:bb_identity)  model:outcome  model:reason
wf.code_node(NAME, CODE, NEXT); wf.api_request_node(NAME, TOOL, NEXT, mapping=[...])
wf.conversation_node(NAME, task=TEXT, tools=[...], transitions=[...], on_enter=wf.say(TEXT) | wf.llm(TEXT),
                     extraction=[wf.extract(NAME, "string", TEXT, enum=[...], min_confidence=0.7)], max_turns=60)
wf.transition(TARGET, TEXT, wf.when_equals(VAR, V) | wf.when_true(VAR) | wf.any_of(...))
wf.workflow(initial=..., nodes={...}, system_prompt=TEXT, tools=[close tool], test_variables={...})
wf.check(workflow, CALL_VARIABLES)    # [] or problems; builder.save runs it too
```

The model must read every date decision, never work it out. When the brief says what to do with a
day that is not a business day (offer the next one, or the previous one), give each deadline date
`"shifts"` in that direction and put `{deadline_shifts}` at the end of the product line: a day guide,
one line per day up to a week past that product's deadline ("the 7th = Monday 7 January ...: holiday,
not a business day -> use ... instead", "... AFTER the latest date"). In the task message, write the date
rule as separate if-then lines keyed on the guide's own words, not as one paragraph (one paragraph was
measured to fail: the model offered the deadline for a holiday before it):
"Whenever the customer names a day, first find that day in the product's day guide, then:
 - the guide says "can be used": accept it.
 - the guide says weekend or holiday "-> use X instead": say it is not a business day and offer X. Do NOT offer the deadline.
 - the guide says "AFTER the latest date": <the brief's rule for a day after the deadline>.
 Use <the brief's sentence for a day after the deadline> only for a day the guide marks AFTER."
Fill in the brief's own rules; when the brief gives other handling for one of these cases, its rule wins.

Persuasion attempts are miscounted when there are several products: the model copies one product's
attempts to the next, or ends a product the customer refused up front without any attempt (both
measured). So: end every band's `offers` text with an explicit stop ("This product has ONE attempt
only: after attempt 1 is refused, stop for this product." / "After attempt N is refused, stop for this
product."), and add to the task message's refusal rule: "Every offer or question you make about a
product after the customer refused it counts as one attempt. Before each offer, check that product's
own line: make exactly its listed attempts, never the number another product has. A product the
customer refused before you reached it (for example in answer to the first question) still gets its
attempts: your first message about it is its attempt 1 offer. Never end a product as refused before its
listed attempts are used." Adapt the words to the brief's own counting rules; when the brief counts
attempts differently, its rule wins.

The close tool is filled by a model after the call ends; it sees only the tool and the transcript.
Its description must carry the brief's whole closing table: every outcome and reason with when it
applies, in the brief's words. Say that the outcome field takes the outcome name only and the reason
field the reason name only. The close rules decide everything the tool results can decide; after
`{"keep_model": True}` add rules keyed on the identity state (`var:bb_identity`), so that a call
with a verified customer never ends in an outcome meant for calls where the customer was not
reached or not verified, whatever the model sent. The `default` is the outcome for a call where
nothing at all happened.

Track every write tool with a post hook (`ok_when` from the tool's success field), give it a pre hook
too (the pre hook records the request the post hook and the close hook read). Retries: what the
brief allows after a failed write. The hook messages are the next step the brief prescribes after
that result, including any sentence the customer must hear.

The end of a call with several steps left (record the agreed promises, then write per-product
records such as notes, then the goodbye) is where the model drops tool calls: it says goodbye and
the remaining calls never happen (measured). So in every message that can come before the end, put
the tool calls still due first and the words to the customer last, never the other way round, and
name the products still due with `{open:<tool>:<tool>...}` (products none of those tools has
written yet, or "none"), e.g. "Products with neither a promise nor a <record>: {open:<promise tool>:<record tool>}.
If that is not none, call <record tool> for each of them now, before you say anything. Then ...".
Respect the brief's exceptions (a call that ends in a transfer may forbid such records).
Give the end_call tool a description that it is only for after the closing phrase, never while an
agreed promise is not yet read back and recorded or a required record is missing, and never in the same
turn as another tool call (measured: a transfer and end_call called together closed the call before the
sentence the brief requires after a transfer was said).

A sentence the brief makes mandatory goes into a hook message without quotes, as the last thing in the
message: "... Ask nothing else. Then say exactly this sentence and nothing after it: <sentence>". Inside a
tool result a quoted sentence reaches the model as \" and was copied with the escape (measured: the
required sentence came out with a stray <"> after it).

A step's first words come from `on_enter=wf.say(TEXT)` with the fixed sentence the brief allows
(variables in `{{...}}`), e.g. the security step: "To protect your account I need to ask you two security
questions. First, <the brief's first question>?". Use `wf.llm` only when the words cannot be fixed: the
model that writes them does not see the brief (measured: it invented a security question about a pet).

Customers give answers in pieces over several turns ("14 March", then "1988"; "4 4", then "7 1") and
correct themselves. Every task message that collects an answer for a tool says: "If the answer comes in
pieces over several turns, put the pieces together and call the tool once with the complete answer; if a
part is missing, ask only for that part. If the customer corrects a part, use the corrected part. Never
ask for the whole answer again because it came in pieces." (measured: an agent asked six times for the
full date in one sentence and ended the call unverified). The same for amounts: a number that may be
the start of a larger one ("twelve", "5") is a piece; ask for the rest before you judge it.

A ban alone does not hold; give the model the sentence to say instead. When the brief says the agent
proposes every amount and never asks the customer for one, the negotiation task message must say what
comes right after a date is agreed: "Can you pay the full past-due amount of <amount> on <date>?" (or the
brief's own next offer), and that the agent never asks the customer how much they will pay (measured:
with the ban only, the agent asked "how much of the 540.00 will you be paying?", the customer said
"five hundred", and 500.00 was recorded instead of 540.00).

The same holds for every "retry" message: a turn that ends in words waits for the customer, and the
retry is then forgotten (measured: a brief that asks to tell the customer before retrying produced
"tell the customer ..., then call the tool again", and the call closed without the retry). Write it as
"Call <tool> again now with the same values, in this same turn, without waiting for the customer. While
you call it you may say one short sentence: <what the brief wants said>."

When a brief's style rule (give a next step, keep the conversation moving, one action per turn) meets
a rule that forbids an action in a situation (no persuasion after hardship, nothing about the account
before identity), the forbidding rule wins: say so in that step's task message, next to the
forbidding rule (measured: a style rule made the model offer a payment after the customer lost their job).

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
