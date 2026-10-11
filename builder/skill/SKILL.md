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
- Read only the brief and tool API files given to you (their copies in `WORK/inputs/`), `builder/`
  and the Freya docs in `builder/vendor/docs/`. Do not open or search anything else: not `dev/`, `tests/`, `submission/`, other
  briefs, the kit's `briefs/`, `out/`, `examples/`, `public-test-set.json`, `results/`, `traces/` or the
  repo's notes. Do not search from the repo root. (Such tool calls are refused.)
- Tool names, field names, types and enums come from the OpenAPI file through `builder.lib.tools`.
  Never hand-write tool JSON.
- Read the whole brief. Most failures come from one skipped rule. When the brief is raw bank
  material (mail, policy extract, memo, code list), the memo's change wins over the older text and
  the code list gives the outcome and reason names. Where the tool API file lists enum values, its
  spelling wins: map the code list onto the enum (close_hook with op= refuses names outside it).
  With several dated changes, the latest one in force on the calls' date (`now` in the brief's example)
  wins; a change with a later effective date or a narrower scope (one product, one band) applies only
  there. In `WORK/notes.md`, list each replaced rule with its replacement, and a table code -> enum value
  (split combined outcome/reason codes; a code with no enum match goes to the value whose "when" text
  fits, noted). A field with no enum (free text) gets the code list's name as written, not its number,
  unless the brief says the system expects the code. The closing table is the code list's "when" column
  with the memo's changes applied.

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

## A case folder (bank documents and a mock URL)

When the task gives a folder of bank documents and a mock URL instead of a brief and a tool API file:
- Read BRIEF.md first, then README.md (it says what each document is), then every document, images
  included (a flow drawing is read as an image). Rules can be spread over several documents; an
  announcement or a Q&A answer can change a rule, and the later or more specific one wins (list each
  change in `WORK/notes.md`). Example conversations show the order and the wording; never copy a
  customer's values from them.
- There is no OpenAPI file. Write `WORK/tool-api.json` (OpenAPI 3) from the service contract: one path
  per service, its method, every request field with its type, enum and required flag exactly as the
  contract writes them, the response fields in the description, and `servers[0].url` = the mock URL.
  Then call one read-only service on the mock with a test customer (`curl`) and compare the real response
  with the contract; fix the spec to the real field names. Load the spec with `tools.load_api` as usual.
  A path that is not a plain name (`/v1/items.list`) needs an `operationId` with letters, digits and `_`
  (it becomes the tool name). A request body that wraps the fields in an object goes in the spec as
  written and is built with `envelope=` (below). Write the contract's error answers (HTTP status, code)
  into each operation's `responses`.
- A list or object from a result never arrives in a `response_mapping` variable (measured: the mapped
  list stayed unset, a mapped number arrived, and the model invented an id). To put a list in
  a later prompt, add a code node right after the api_request node:
  `wf.code_node(NAME, calc.list_code(node=API_NODE, tool=TOOL, list_path="data.<list>", id_field=F,
  item_fields=[...], var=V, empty=TEXT, same_fields=[...]), NEXT)`; the prompt then reads `{{V}}` (one
  line per item) and `{{V_count}}`. same_fields: the fields a caller picks an item by (its name, its
  short number); a line whose value other items share says so, and the task message tells the model to
  ask the documents' disambiguation question for such items. Map only plain values with `mapping=`.
- HTTP errors: on a non-2xx answer the post hook does not run. The engine still sets the status and
  the failure count: for a call in an api_request node's pre_actions they are named after the NODE
  (`<node>_status_code`, `<node>_failure_count`, `<node>_response.*`), for a tool in `tools` after the
  tool (`<tool>_status_code`). The status is a number. When the documents treat two error statuses
  differently (e.g. "not found" is an ordinary answer, a 500 goes to an agent), route with
  `wf.when_status(<node or tool>, 404)` (it tests both forms) and say in the task message which
  sentence each status gets. `wf.check` refuses a transition on `<tool>_...` in an api_request node. When the documents
  say an answer can be slow, set `timeout_ms` above that (the engine allows 30 s in all) and give the
  waiting sentence they name.
- Language: the phone agent speaks the language of the documents and the example conversations. Every
  fixed sentence (`wf.say`, `calc.wrap_code`, mandatory sentences in hook messages) is in that language,
  in the documents' own words where they give them. The `*_spoken` placeholders are English: in another
  language put `{date:N}`/`{deadline}` in fixed sentences only if the documents show dates that way,
  otherwise leave the date to the model with "say the date in <language>". Task messages may stay in
  English; they say which language to speak.
- Test customers: use them for the local check of the code nodes and for mock calls only; never write
  their values into prompts.
- What the phone agent's model gets wrong in a long task message (measured on the example calls), so
  write these into it as plain rules:
  - A reading or answer whose documented order ends with an offer or a question is ONE message: the
    model calls every tool that the closing offer needs (e.g. the lookup that decides which options to
    offer) right after the main lookup, before it speaks, and ends the message with the offer. Otherwise
    the caller's "thanks" comes first and the offer is never made. Only that branch: a branch the
    documents end differently (no offer, another question) keeps its own ending; write each branch's
    ending next to it (measured: the offer leaked into a branch that has none).
  - An answer the caller gives early (a choice before the options were read) does not skip the
    documented steps before it: the model still says those steps' sentences (e.g. the current state and
    the options), then uses the answer.
  - A clear yes that comes with another request in the same answer is still the yes: first call the
    confirmed action's tool and report its result, then answer the other request.
  - When the caller names something that several items of a list share, the model asks the documents'
    disambiguation question; it never picks one of them. Each answer narrows the group; while two or
    more items still fit, it asks the next question of the documents' chain (the list lines from
    `list_code(same_fields=...)` say which items still match).
  - Every sentence that ends the call (main menu, transfer, hang-up) is said once, with end_call in
    the same message.

## How the workflow is built (the default for a brief with this flow)

This is the default layout for a brief whose call goes: who is on the line, identity, the debt and the
promises, closing. Add, drop or reorder steps when the brief's flow differs. Give each step every tool
the brief allows in that step (from `WORK/notes.md`), plus end_call (except a gated `negotiate`, below);
never a tool the brief forbids there.

- `setup` (code node, initial): date facts from `now` for the whole call (`calc.dates_code`).
- `greet` (conversation): the brief's opening; who is on the line (extraction enum); what the brief
  says to do when someone else answers (e.g. a callback); tools: those the brief allows before identity.
- `identity` (conversation): ask the brief's security questions, in its order and as it says (one at a
  time when it says so); tools: the identity tool, any tool the brief allows here (e.g. a transfer
  for a human request), end_call. Leave on the identity result:
  `wf.any_of(wf.when_true("<identity tool>_response.data.<all-verified field>"), wf.when_equals("bb_identity", "verified"))`.
- `load_account` (api_request): the account lookup, mapping `data.<list field>` to a variable.
- `account_facts` (code node): product facts (`calc.products_code`).
- `negotiate` (conversation): state the debt, get promises, notes, transfers; write tools + end_call
  (no end_call when the goodbye is gated, next item).
- When the brief requires a record for EVERY product (a promise or a note with a reason, even when no
  promise is made), the goodbye is gated in code, not left to the prompt (measured four times: the
  model said goodbye with no record, the brief's rule written correctly in its task message):
  give each post hook of the tools that complete a product `open_var="bb_open", open_tools=[those
  tools]`; `negotiate` gets NO end_call; its transitions go to a `wrap_text` code node, then `wrap_up`, when
  `wf.when_equals("bb_open", "none")`, and when the brief's call-ending event happened without records
  (e.g. a transfer: let that tool's post hook `set` a flag such as `{"bb_transferred": "yes"}` and route
  on it). Set such a flag only in a rule on the tool's success field (`[["ok", "true"]]`), never on a
  field that is present either way (`ok: false` is present too). Give `negotiate` `max_turns` and
  `max_turn_transition="wrap_text"` as a last exit. Every way a product can end in `negotiate` must either
  write a record or set a flag that routes on; if the brief has an ending with no record and no tool
  call, do not gate. The words of the end are chosen in code, not by the model (measured: a model asked
  to pick them skipped the brief's sentence after a recorded promise in 3 of 3 runs):
  `wrap_text` = `wf.code_node("wrap_text", calc.wrap_code(parts=[{"when": [["bb_count__<promise tool>",
  "gte", 1]], "say": <the brief's sentence after a recorded promise>}, {"when": [["bb_failed_out__<promise
  tool>", "present"]], "say": <what the brief says for a failed one>}, {"when": [["bb_transferred",
  "equals", "yes"]], "say": <the brief's transfer sentence>}, {"say": <the closing phrase>}]), "wrap_up")`,
  only the parts the brief has, in the brief's order. `wrap_up`: `on_enter=wf.say("{{bb_wrap}}")`,
  tools=[end_call] only, no transitions, task message "The call is over. Say nothing more."; end_call's
  `trigger_phrase` lists the closing phrase (and the transfer sentence if a call can end on it). Under the
  gate the closing phrase and "call end_call" appear ONLY in `wrap_text`: not in the system prompt, not in
  `negotiate`, not in hook messages (measured: a model that knew the goodbye said it in `negotiate` and
  called end_call there, although that step did not list it; the engine runs end_call from any step).
  The negotiate task message says the call ends by itself once every product has its record; hook
  messages say which product is next and nothing about goodbye. A brief that never records per product
  (e.g. only a promise or nothing) keeps end_call in `negotiate`.
- The close tool is a workflow-level `end_of_call` lifecycle tool whose pre hook is `closing.close_hook`.
- Prompts: the system prompt holds the identity, tone, hard rules that hold in every step, and
  `{{date_facts}}`. It must say: obey the `what_to_do_next` field of every tool result; after every
  tool result speak or call the next tool; call one tool per message and wait for its result before
  the next call, even when several products need the same tool (calls sent together run side by side,
  and a result can then be read as another product's); never say something is recorded unless the tool result
  says it worked. The judge reads the word the brief uses for a successful write (its "saved" word)
  literally: it must not appear in any turn before the write succeeds, the opening included. Where the
  brief does not dictate the exact words, say other things with another form (if the saved word were
  "logged", the opening would say "we log this call", not "this call is logged"; a failure, "I could not
  log it"). Where a product is agreed before the read-back (several products and the brief has one
  read-back for all), the task
  message gives the words for that moment, an acknowledgement in the agreed-not-yet-saved sense ("Thank
  you, that is agreed: <amount> on <date> for <product>. I will read everything back at the end."):
  measured, the model otherwise acknowledged an agreement with the saved word. Each node's task message covers only that step: its rules from the brief, with
  every sentence the brief makes mandatory quoted exactly, and which tool to call when. Never name
  other nodes or describe routing in a task message.
- End the call with the end_call tool: the assistant says the closing phrase, which triggers it, in the
  step that has end_call (`wrap_up` when the goodbye is gated).
- Route on tool results and code flags, never on what the customer says, except who answered the phone.

## builder/lib in one page

```python
from builder.lib import calc, closing, hooks, tools, workflow as wf
ops, warnings = tools.operations(tools.load_api(API)); op = ops["<tool>"]
tools.api_tool(op, description=TEXT, bake={"<field>": "{{<call variable>}}"}, notes={"<field>": TEXT},
               pre=CODE, post=CODE, mapping=[("data.<field>", "<var>")], lifecycle="end_of_call",
               timeout_ms=12000, envelope="", envelope_parts={})
#   envelope: when the API wants its fields inside one body object ({"data": {...}, "meta": {...}}),
#   envelope="data": the tool's fields are then the inner ones (bake/notes name them) and a pre hook step
#   wraps them; envelope_parts gives fixed values for the other top-level objects (no placeholders)
tools.end_call_tool(description=TEXT, trigger_phrase=[PHRASE, ...], polite_replies=[...])
#   trigger_phrase: EVERY sentence the brief makes the last words of a call (the goodbye, an announcement
#   after a transfer, ...): a call that ends on a sentence that is not listed stays open until the time
#   limit (measured: a transfer announcement left the call open and the case failed)
calc.dates_code(calendar={"workdays": [WORKDAYS, Monday = 0], "holidays": ["YYYY-MM-DD", ...]},
                dates=[{"name": N, "rule": R, ...params, "label": TEXT,
                        "shifts": SHIFT}],   # bb_date__N, bb_date__N__spoken, bb_shifts__N; SHIFT forward|backward
                windows=[{"name": N, "days": [rules], "from": "HH:MM", "to": "HH:MM", "after_now": BOOL,
                          "inclusive": BOOL, "var": "<var for the prompt>", "label": TEXT}],
#   one window per time range the brief allows; every value from the brief
                weekday_mode="following_week" | "first_after_today" | "", calendar_days=40)
#   rules: today | next_business_day | business_days_after n | calendar_days_after n (+roll)
#          | end_of_month months_ahead (+roll) | last_business_day_of_week (weeks_ahead, after_today)
calc.products_code(sources=calc.product_sources(NODE, LOOKUP_TOOL, LIST_FIELD, MAPPED_VAR),
                   list_field=..., id_field=..., type_field=..., amount_field=..., days_field=...,
                   item_fields=[every item field], types={TYPE: {"name": "...{field:F}...",
                   "floor_field": F, "floor_label": TEXT}}   # or, with no floor field:
                   #   "floor_percent": P (of the full amount), "floor_min": N (computed floor never above full), bands=[{"name", "min", "max", "deadline": DATE_NAME,
                   "attempts": N, "offers": TEMPLATE}], line=TEMPLATE, header="...{count}...",
                   known_dates=(...DATE_NAMEs), band_field=F, default_type={...},
                   say_line=TEMPLATE)   # say_line: what is said about one product -> {{debt_statement}}
calc.wrap_code(parts=[{"when": [[VAR, OP, V]], "say": TEXT}, ..., {"say": CLOSING_PHRASE}])
#   the words that end a gated call, chosen in code -> {{bb_wrap}}; the last part holds always
#   band_field: the item field the brief's band table is keyed on (days_field by default);
#   default_type: the spec for a product type the brief names that the API enum does not list
#   placeholders: {id} {name} {full} {floor} {floor_label} {days} {band} {deadline} {deadline_spoken}
#   {deadline_shifts} {attempts} {offers} {field:F} {date:N} {date_spoken:N} {shifts:N};
#   writes bb_products, bb_deadline__<id>, ...
# normalize kinds: "digits" only for answers that are digits alone; "text" (optionally "upper": True)
#   for codes with letters (postcodes, company numbers); a value that cannot be read for sure is sent as given
hooks.pre_hook(TOOL, normalize={FIELD: {"kind": "date", "order": ORDER} | {"kind": "digits", "last": N}
               | {"kind": "time"} | {"kind": "amount"} | {"by": OTHER_FIELD, "cases": {VALUE: SPEC}}},
               refs=[ID_FIELD], key_field=ID_FIELD,
               guard={DATE_FIELD: {"min": "today", "max_var": "bb_deadline__{key}", "calendar": CAL, "roll": SHIFT}},
               op=ops[TOOL])
hooks.post_hook(TOOL, rules=[{"when": [[F, "true"|"false"|"missing"|"present"|"equals"|"lte"|..., V]],
                "say": TEXT, "set": {"bb_identity": "verified"}}], messages={"ok", "retry", "give_up",
                "error", "default": TEXT}, ok_when=[[F, "true"], ...], key_field=F, retries=N,
                fail_mark=[F, False], log_fields=[F], open_var="bb_open", open_tools=[TOOL, TOOL],
                op=ops[TOOL])
#   message placeholders: {key} {tries} {retries_left} {adjusted} {open:TOOL:TOOL} (products not yet
#   written by any of those tools, or "none") and any response field or variable
#   open_var: after every result the variable holds the same list as {open:...}; route on it
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

When the brief limits persuasion attempts, the model miscounts them with several products: it copies one
product's count to the next, or ends a product refused early without the attempts the brief gives it
(both measured). So end every band's `offers` text with an explicit stop ("This product has ONE attempt
only: after attempt 1 is refused, stop for this product." / "After attempt N is refused, stop for this
product."), and tell the model to check that product's own line before each offer, never another
product's count. Then write the brief's own counting rule in if-then form: what uses an attempt (an
offer, a question, the opening question or not), whether a refusal given before the agent reached a
product uses one, and what happens when they are used up. Do not assume another brief's answer. One
case the model gets wrong unless told (measured): when the brief says each product starts at its first
attempt (or does not say that a refusal before the agent reached the product uses one), a product the
customer refused up front still gets all its attempts; write: "A product the customer refused before
you reached it still gets its attempts: your first message about it is its attempt 1 offer. Never end a
product as refused before its listed attempts are used."

The close tool is filled by a model after the call ends; it sees only the tool and the transcript.
Its description must carry the brief's whole closing table: every outcome and reason with when it
applies, in the brief's words. Say that the outcome field takes the outcome name only and the reason
field the reason name only. The close rules decide everything the tool results can decide. Rules are
tried in order and the first that applies wins, so every guard goes BEFORE `{"keep_model": True}` (a
rule after it only runs when the model sent nothing usable):
- rules keyed on the identity state (`var:bb_identity`), so that a call with a verified customer never
  ends in an outcome the brief's table reserves for calls where the customer was not reached or not
  verified, whatever the model sent; build these rules from the table's own conditions;
- an outcome for refusing the identity check (e.g. "declined") only when the person confirmed who they
  are (the greet step's extraction, e.g. `var:who_answered` equals the customer value); a call where that
  never happened ends in the table's outcome for "not reached / unclear who answered" (measured: an
  unconfirmed caller closed as declined);
- an outcome or a reason whose fact did not happen is replaced (e.g. the outcome for "a promise was
  recorded" with `count:<promise tool>` 0, or "paid" with no paid record). Go through every outcome
  AND every reason of the table: each one that a write proves (a promise recorded, a callback booked, a
  transfer made) gets such a guard, placed before any rule that takes the reason from the model
  (`{"model": True}`), since that rule passes the model's reason through too (measured: the model sent
  the "callback booked" reason with no callback booked, and a `{"model": True}` rule kept it).
The `default` is the outcome for a call where nothing at all happened.

Track every write tool with a post hook (`ok_when` from the tool's success field), give it a pre hook
too (the pre hook records the request the post hook and the close hook read). Retries: what the
brief allows after a failed write. The hook messages are the next step the brief prescribes after
that result, including any sentence the customer must hear (when the goodbye is gated, the sentences
of the call's end are in `wrap_text` instead).

The end of a call with several steps left (the writes the brief requires per product, in its order,
then the goodbye) is where the model drops tool calls: it says goodbye and the remaining calls never
happen (measured). So in every message that can come before the end, put the tool calls still due
first and the words to the customer last, never the other way round, and name the products still due
with `{open:<tool>:<tool>...}` (products none of those tools has written yet, or "none"): list the tools
whose successful write completes a product under the brief, e.g. "Products not yet completed:
{open:<tool A>:<tool B>}. If that is not none, call <the tool the brief requires for them> now for the
first of them only, before you say anything; the result names the next. Then ..." (gated: "If that is
none, say nothing more: the call goes on by itself."). Respect the brief's exceptions (e.g. a transfer
that forbids them).
Those hook messages only come after a write. When the brief requires a record per product even with no
promise at all (a dispute, "already paid", refusals), nothing has been written yet when the call ends and
no hook reminds the model (measured twice: goodbye with no record at all). So the task message's
end-of-call rule names that case on its own: "If no promise was agreed, first call <the record tool> for
every product, in order, with its reason, one call per message; only then the goodbye." (gated: "...
one call per message; the call ends by itself after the last one.")
Without the gate, give the end_call tool a description that it is only for after the closing phrase, never while an
agreed promise is not yet read back and recorded or a required record is missing, and never in the same
turn as another tool call (measured: a transfer and end_call called together closed the call before the
sentence the brief requires after a transfer was said).

A sentence the brief makes mandatory goes into a hook message without quotes, as the last thing in the
message: "... Ask nothing else. Then say exactly this sentence and nothing after it: <sentence>". Inside a
tool result a quoted sentence reaches the model as \" and was copied with the escape (measured: the
required sentence came out with a stray <"> after it).

A step's first words come from `on_enter=wf.say(TEXT)` with the fixed words the brief allows
(variables in `{{...}}`), e.g. the security step: "<the brief's lead-in, if it gives one> <its first
question>?" (state a number of questions or an order only if the brief does). The step that states the
debt says `{{debt_statement}}` from `products_code(say_line=...)`: one sentence per product with what
the brief says must be stated (e.g. "Your {name} is {full} past due and {days} days late."), so no
product is skipped. Use `wf.llm` only when the words cannot be fixed: the model that writes them does not
see the brief (measured: it invented a security question; it stated three products without amounts).
(The end of a gated call is not such a case: `calc.wrap_code` picks its words.)

Customers give answers in pieces over several turns (the day and month, then the year; two digits, then
two more) and correct themselves. Every task message that collects an answer for a tool says: "If the answer comes in
pieces over several turns, put the pieces together and call the tool once with the complete answer; if a
part is missing, ask only for that part. If the customer corrects a part, use the corrected part. Never
ask for the whole answer again because it came in pieces." (measured: an agent asked six times for the
full date in one sentence and ended the call unverified). The same for amounts: a number that may be
the first part of a larger one is a piece; ask for the rest before you judge it.

A ban alone does not hold; give the model the sentence to say instead. When the brief says the agent
proposes the amounts (and never asks the customer for one), the negotiation task message gives the
brief's next offer for each state as a fixed sentence, in the brief's order: e.g. date agreed, no amount
yet -> "<the brief's first amount> on <date>?"; that amount refused as too much -> the brief's fallback
amount; never an amount the customer already refused (measured: with the ban only, the agent asked
"how much ... will you be paying?" and a lower figure was recorded). Also say: "A customer who says
they will pay a product on a day and names no lower amount agrees to the amount on offer: go to the
read-back." An offer the brief allows once is made once: if the day is still open, name the amount and
ask for the day in the same sentence; after that only the day is discussed and the amount is not offered
again (the read-back does not count) (measured: the floor offered "today", then again "on Friday", was
judged as offered twice). And, in the system prompt: "Never ask the same question a third time, unless
the brief allows more tries (e.g. security answers: send every answer to the identity tool until the
brief's limit); if the customer's answer has not changed, act on what they said. A question whose answer
changed is not the same question." (measured: a fixed offer sentence asked 70 times in a row while the
customer kept saying "I will pay the card tomorrow").

A failed HTTP call (e.g. a 500 from the bank) reaches the model as a plain error, and the post hook
does not run on it (measured: "API request failed: {...}" with no what_to_do_next; the model said
goodbye and the brief's retry never happened). So the system prompt must also say: "If a tool call
returns an error and no what_to_do_next, that call failed and nothing was saved; never say it worked."
followed by the brief's rule for a failed call of each tool that has one, named (e.g. "<tool>: <the
brief's rule>"). Add no retry the brief does not give.

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
