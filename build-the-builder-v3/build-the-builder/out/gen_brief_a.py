"""Generate out/brief-a.workflow.json from briefs/brief-a.md (one late product per call)."""
import json
import pathlib

BANK = "https://freya-bank-mock.freyavoice.workers.dev/v1/"
HOLIDAYS = ["2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"]  # brief section 7

# ---------------------------------------------------------------- code snippets (no double braces)
SETUP_CODE = r'''
import datetime
HOL = HOLIDAYS_LIST
NAMES = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
def isbd(d):
    return d.weekday() < 5 and d.isoformat() not in HOL
def spoken(d):
    return NAMES[d.weekday()] + ' ' + str(d.day) + ' ' + d.strftime('%B') + ' ' + str(d.year)
try:
    now = str(vars.get('now') or '')
    today = datetime.date.fromisoformat(now[:10])
    hhmm = now[11:16] if len(now) >= 16 else '00:00'
    one = datetime.timedelta(days=1)
    def nth_bd(n):
        d = today; c = 0
        while c < n:
            d = d + one
            if isbd(d): c += 1
        return d
    def next_bd(d):
        d = d + one
        while not isbd(d): d = d + one
        return d
    early = nth_bd(12); late = nth_bd(7)
    monday = today - datetime.timedelta(days=today.weekday())
    def last_bd_of_week(mon):
        d = mon + datetime.timedelta(days=6)
        while d >= mon and not isbd(d): d = d - one
        return d if d >= mon else None
    lw = last_bd_of_week(monday)
    if lw is None or lw <= today:
        lw = last_bd_of_week(monday + datetime.timedelta(days=7))
    nbd = next_bd(today)
    lines = []
    lines.append('TODAY: ' + spoken(today) + ' (' + today.isoformat() + '), time now ' + hhmm + '. Today is ' + ('a business day.' if isbd(today) else 'NOT a business day.'))
    lines.append('NEXT BUSINESS DAY: ' + spoken(nbd) + ' (' + nbd.isoformat() + ').')
    lines.append('THIS <weekday> = that weekday in the current Monday-Sunday week. NEXT <weekday> = that weekday in the following week (so next Friday said on a Friday is 7 days later).')
    tw = []; nw = []
    for i in range(7):
        a = monday + datetime.timedelta(days=i); b = a + datetime.timedelta(days=7)
        tw.append('this ' + NAMES[i] + ' = ' + a.isoformat()); nw.append('next ' + NAMES[i] + ' = ' + b.isoformat())
    lines.append('; '.join(tw)); lines.append('; '.join(nw))
    lines.append('CALENDAR (B = business day; X = weekend or bank holiday, never a promise date):')
    for i in range(0, 40):
        d = today + datetime.timedelta(days=i)
        tag = 'B' if isbd(d) else ('X holiday' if d.isoformat() in HOL else 'X weekend')
        lines.append('  ' + d.isoformat() + ' ' + NAMES[d.weekday()] + ' ' + tag + (' (today)' if i == 0 else ''))
    vars['date_facts'] = chr(10).join(lines)
    vars['today_iso'] = today.isoformat()
    vars['deadline_early'] = early.isoformat()
    vars['deadline_late'] = late.isoformat()
    vars['spoken_early'] = spoken(early)
    vars['spoken_late'] = spoken(late)
    vars['attempt1_iso'] = lw.isoformat()
    vars['attempt1_spoken'] = spoken(lw)
    vars['callback_facts'] = ('A callback can be booked only for today (' + today.isoformat() + ') at a time later than ' + hhmm + ' and from 10:00 to 19:00, or for the next business day, ' + spoken(nbd) + ' (' + nbd.isoformat() + '), from 10:00 to 19:00. Both ends included. Anything else is outside the window. Tomorrow is ' + (today + one).isoformat() + '.')
    vars['setup_state'] = 'ok'
except Exception as e:
    vars['date_facts'] = 'Date facts unavailable: ' + str(e)
    vars['callback_facts'] = 'Callback window: today later than now, or the next business day, 10:00 to 19:00.'
    vars['setup_state'] = 'error'
'''.replace("HOLIDAYS_LIST", repr(HOLIDAYS))

ACCOUNT_CODE = r'''
import json
def money(x):
    try: return '%.2f' % float(x)
    except Exception: return str(x)
def find_products():
    for k in ('products', 'load_account_response.data.products', 'get_account_response.data.products'):
        v = vars.get(k)
        if isinstance(v, str):
            try: v = json.loads(v)
            except Exception: v = None
        if isinstance(v, list) and v: return v
    out = []
    for i in range(3):
        pre = None
        for base in ('products.', 'load_account_response.data.products.', 'get_account_response.data.products.'):
            if vars.get(base + str(i) + '.product_id') is not None: pre = base + str(i) + '.'; break
        if not pre: break
        p = dict()
        for f in ('product_id','type','card_last4','past_due','days_late','minimum_payment','instalment_amount'):
            if vars.get(pre + f) is not None: p[f] = vars.get(pre + f)
        out.append(p)
    return out
try:
    prods = find_products()
    p = prods[0]
    pid = str(p.get('product_id'))
    t = str(p.get('type'))
    if t == 'credit_card':
        name = 'credit card ending ' + str(p.get('card_last4')); floor = p.get('minimum_payment'); fname = 'minimum payment'
    elif t == 'personal_loan':
        name = 'personal loan'; floor = p.get('instalment_amount'); fname = 'instalment amount'
    else:
        name = 'car loan'; floor = p.get('instalment_amount'); fname = 'instalment amount'
    dl = int(float(p.get('days_late') or 0))
    full = money(p.get('past_due')); fl = money(floor)
    a1 = str(vars.get('attempt1_spoken')) + ' (' + str(vars.get('attempt1_iso')) + ')'
    if dl <= 7:
        band = 'early'; deadline = vars.get('deadline_early'); dspoken = vars.get('spoken_early'); n = 1
    else:
        band = 'late'; deadline = vars.get('deadline_late'); dspoken = vars.get('spoken_late'); n = 2
    L = []
    L.append('PRODUCT: ' + name + ' (product_id ' + pid + '). Say it exactly as "' + name + '".')
    L.append('PAST-DUE AMOUNT (full amount): ' + full + '. DAYS LATE: ' + str(dl) + '.')
    L.append('FLOOR (' + fname + '): ' + fl + '. Never propose or accept less than the floor.')
    L.append('BAND: ' + band + '. DEADLINE (latest promise date): ' + str(dspoken) + ' (' + str(deadline) + '). PERSUASION ATTEMPTS ALLOWED: ' + str(n) + '.')
    L.append('ATTEMPT 1 OFFER: ' + full + ' on ' + a1 + '. If the customer already said the full amount is too much, attempt 1 is the floor ' + fl + ' on ' + a1 + ' instead.')
    if n == 2:
        L.append('ATTEMPT 2 OFFER (only after attempt 1 is refused): the floor ' + fl + ' on the deadline ' + str(dspoken) + ' (' + str(deadline) + '). After it is refused: stop.')
    else:
        L.append('NO ATTEMPT 2 (early band). After attempt 1 is refused: stop.')
    vars['account_facts'] = chr(10).join(L)
    vars['product_id'] = pid
    vars['deadline_p'] = deadline
    vars['floor_p'] = floor
    vars['past_due_p'] = p.get('past_due')
    vars['account_state'] = 'ok'
except Exception as e:
    vars['account_facts'] = 'The account details could not be loaded. Do not state or invent any amount. Say you do not have the information right now.'
    vars['account_state'] = 'error'
'''

VERIFY_PRE = r'''
import re
MONTHS = dict(january=1,february=2,march=3,april=4,may=5,june=6,july=7,august=8,september=9,october=10,november=11,december=12,jan=1,feb=2,mar=3,apr=4,jun=6,jul=7,aug=8,sep=9,sept=9,oct=10,nov=11,dec=12)
try:
    b = config.get('body')
    if isinstance(b, dict):
        a = str(b.get('answer') or '').strip()
        if b.get('field') == 'phone_last4':
            dg = re.sub(r'\D', '', a)
            if len(dg) >= 4: b['answer'] = dg[-4:]
        elif not re.match(r'^\d{4}-\d{2}-\d{2}$', a):
            low = re.sub(r'(\d)(st|nd|rd|th)\b', r'\1', a.lower())
            low = re.sub(r'[,.]', ' ', low).replace(' of ', ' ')
            m = re.match(r'^\s*(\d{1,2})[/\- ]+(\d{1,2})[/\- ]+(\d{4})\s*$', low)
            if m:
                b['answer'] = '%s-%02d-%02d' % (m.group(3), int(m.group(2)), int(m.group(1)))
            else:
                toks = low.split()
                mon = None; nums = []
                for t in toks:
                    if t in MONTHS and mon is None: mon = MONTHS[t]
                    elif t.isdigit(): nums.append(int(t))
                yr = [x for x in nums if x > 31]; dy = [x for x in nums if 1 <= x <= 31]
                if mon and yr and dy:
                    b['answer'] = '%04d-%02d-%02d' % (yr[0], mon, dy[0])
except Exception:
    pass
'''

VERIFY_POST = r'''
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if not isinstance(d, dict):
            result['what_to_do_next'] = 'The check service failed. Nothing was checked. Ask the customer to repeat the same answer and call verify_identity again.'
        else:
            left = d.get('wrong_answers_left')
            if d.get('all_verified') in (True, 'true', 'True'):
                msg = 'Both security answers are correct. The customer is verified.'
            elif d.get('hint') == 'day_month_swapped':
                msg = 'Day and month look swapped. This is NOT counted as a wrong answer. Ask the customer to say their date of birth again with the month as a word.'
            elif d.get('ok') in (False, 'false', 'False') and d.get('verified') is None:
                msg = 'The answer could not be read. Not counted as a wrong answer. Ask for the same answer again.'
            elif d.get('verified') in (True, 'true', 'True'):
                msg = 'Correct. Now ask the second security question: the last four digits of the phone number on file.'
            elif left is not None and int(left) <= 0:
                msg = 'Third wrong answer: the security check has FAILED. Do not state any debt, amount or product. Tell the customer to use the Freya Bank mobile app or visit a branch, thank them and say goodbye, ending with "Have a good day."'
            else:
                msg = 'That answer does not match. Say so and ask the SAME question again. Wrong answers left: ' + str(left) + '.'
            d['what_to_do_next'] = msg
except Exception:
    pass
'''

CALLBACK_PRE = r'''
import re
try:
    b = config.get('body')
    if isinstance(b, dict):
        t = str(b.get('time') or '').strip().lower()
        m = re.match(r'^(\d{1,2})(?:[:.h ](\d{2}))?\s*(am|pm)?$', t)
        if m:
            h = int(m.group(1)); mi = int(m.group(2) or 0)
            if m.group(3) == 'pm' and h < 12: h += 12
            b['time'] = '%02d:%02d' % (h, mi)
        b['date'] = str(b.get('date') or '')[:10]
except Exception:
    pass
'''

PROMISE_PRE = r'''
import datetime
HOL = HOLIDAYS_LIST
try:
    b = config.get('body')
    if isinstance(b, dict):
        pid = vars.get('product_id')
        if pid: b['product_id'] = str(pid)
        dl = vars.get('deadline_p')
        today = str(vars.get('today_iso') or '')[:10]
        d = datetime.date.fromisoformat(str(b.get('date') or '')[:10])
        if today:
            t0 = datetime.date.fromisoformat(today)
            if d < t0: d = t0
        if dl:
            dld = datetime.date.fromisoformat(str(dl)[:10])
            if d > dld: d = dld
        while d.weekday() >= 5 or d.isoformat() in HOL:
            d = d + datetime.timedelta(days=1)
        b['date'] = d.isoformat()
except Exception:
    pass
'''.replace("HOLIDAYS_LIST", repr(HOLIDAYS))

PROMISE_POST = r'''
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict) and d.get('ok') in (True, 'true', 'True') and d.get('promise_id'):
            vars['promises_recorded'] = int(vars.get('promises_recorded') or 0) + 1
            d['what_to_do_next'] = 'The promise IS recorded. Tell the customer it is recorded and say exactly: "You will receive a text message confirming this promise." Then thank them and say goodbye, ending with "Have a good day."'
        else:
            n = int(vars.get('cp_failures') or 0) + 1
            vars['cp_failures'] = n
            tgt = d if isinstance(d, dict) else result
            tgt['ok'] = False
            if n < 2:
                tgt['what_to_do_next'] = 'FAILED: the promise was NOT recorded. Do not say it is recorded. Call create_promise again right now with exactly the same values, once.'
            else:
                tgt['what_to_do_next'] = 'FAILED twice: the promise could NOT be recorded. Tell the customer honestly that you could not record the promise. Do not try again. Thank them and say goodbye, ending with "Have a good day."'
except Exception:
    pass
'''

GENERIC_POST = r'''
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict) and d.get('ok') in (True, 'true', 'True'):
            d['what_to_do_next'] = 'Done. Tell the customer, thank them and say goodbye, ending with "Have a good day."'
        else:
            result['what_to_do_next'] = 'This action FAILED and was not carried out. Tell the customer honestly; do not claim it was done.'
except Exception:
    pass
'''

CLOSE_PRE = r'''
def g(k):
    v = vars.get(k)
    if v is None and '.' in k:
        head, rest = k.split('.', 1)
        o = vars.get(head)
        for part in rest.split('.'):
            o = o.get(part) if isinstance(o, dict) else None
        v = o
    return v
def num(x):
    try: return int(float(x))
    except Exception: return 0
try:
    b = config.get('body')
    if isinstance(b, dict):
        out = b.get('outcome'); rsn = b.get('reason')
        verified = str(g('verify_identity_response.data.all_verified')).lower() == 'true'
        tq = g('transfer_to_agent_args.queue')
        left = g('verify_identity_response.data.wrong_answers_left')
        if num(g('transfer_to_agent_success_count')) > 0 and tq in ('restructuring', 'general', 'support'):
            out = 'transferred'; rsn = 'human' if tq == 'general' else tq
        elif num(vars.get('promises_recorded')) > 0:
            out = 'promise'; rsn = None
        elif num(g('schedule_callback_success_count')) > 0:
            out = 'not_reached'; rsn = 'callback'
        elif left is not None and num(left) <= 0 and not verified:
            out = 'not_verified'; rsn = 'failed'
        elif num(vars.get('cp_failures')) >= 2:
            out = 'no_promise'; rsn = 'service_error'
        elif verified and out in ('not_verified', 'not_reached', 'promise', None, ''):
            out = 'no_promise'; rsn = 'refused'
        elif (not verified) and out in ('no_promise', 'promise', 'paid'):
            out = 'not_verified'; rsn = 'declined'
        if out: b['outcome'] = out
        if out in ('promise', 'paid') or not rsn:
            b.pop('reason', None)
        else:
            b['reason'] = rsn
except Exception:
    pass
'''


# ---------------------------------------------------------------- tool builders
def api_tool(name, desc, fields, required, pre="", post="", retries=0):
    props = {"customer_id": {"type": "string", "default": "{{customer_id}}"}}
    props.update(fields)
    t = {
        "type": "function",
        "config": {"timeoutMs": 12000, "maxRetries": retries},
        "function": {
            "name": name, "handler": "__function__:api_call", "description": desc,
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string", "default": BANK + name},
                "method": {"type": "string", "default": "POST"},
                "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                "body": {"type": "object", "required": required, "properties": props},
            }},
        },
    }
    if pre:
        t["pre_process_code"] = pre
    if post:
        t["post_process_code"] = post
    return t


def leaf(typ, desc, var, enum=None):
    d = {"type": typ, "description": desc, "default": "{{" + var + "}}"}
    if enum:
        d["enum"] = enum
    return d


END_CALL = {
    "type": "function", "config": {"timeoutMs": 10000},
    "function": {
        "name": "end_call", "handler": "__function__:end_call",
        "parameters": {"type": "object", "properties": {
            "message_mode": {"type": "string", "default": "none"},
            "interruptible": {"type": "boolean", "default": True},
            "trigger_pattern": {"type": "string", "default": "Have a good day|have a good day"},
            "trigger_timeout": {"type": "number", "default": 3},
            "trigger_pattern_both": {"type": "string", "default": "goodbye|bye|have a good day|you too|thank you|thanks|take care"},
        }},
        "description": "Ends the call. You normally do NOT call this: the phrase \"Have a good day.\" ends the call by itself. Call it without any text only if the customer speaks again after your goodbye.",
    },
}

VERIFY = api_tool(
    "verify_identity",
    "Check ONE security answer. CALL it every time the customer gives a date of birth or phone digits, before saying anything about the answer.",
    {"field": leaf("string", "Which question this answers: date_of_birth or phone_last4.", "field", ["date_of_birth", "phone_last4"]),
     "answer": leaf("string", "date_of_birth as YYYY-MM-DD ('14 March 1988' -> 1988-03-14; a numbers-only date is day, month, year). phone_last4 as exactly four digits.", "answer")},
    ["field", "answer"], pre=VERIFY_PRE, post=VERIFY_POST)

CALLBACK = api_tool(
    "schedule_callback",
    "Book a callback. CALL it only when the person gave a day and a time inside the allowed callback window.",
    {"date": leaf("string", "Callback date YYYY-MM-DD.", "date"),
     "time": leaf("string", "Callback time HH:MM, 24-hour, from 10:00 to 19:00.", "time")},
    ["date", "time"], pre=CALLBACK_PRE, post=GENERIC_POST)

TRANSFER = api_tool(
    "transfer_to_agent",
    "Hand the call to a person. CALL it with queue restructuring (customer asks for a new payment plan or lower instalments), support (hardship customer accepted the support team) or general (customer insists on a human after you asked once whether you can help).",
    {"queue": leaf("string", "One of: restructuring, general, support.", "queue", ["restructuring", "general", "support"])},
    ["queue"], post=GENERIC_POST)

PROMISE = api_tool(
    "create_promise",
    "Record the payment promise. CALL it only after the customer said a clear yes to your read-back of product, amount and date.",
    {"product_id": leaf("string", "product_id of the late product.", "product_id"),
     "amount": leaf("number", "The agreed amount, a number.", "amount"),
     "date": leaf("string", "The agreed date, YYYY-MM-DD.", "date")},
    ["product_id", "amount", "date"], pre=PROMISE_PRE, post=PROMISE_POST)

CLOSE = api_tool(
    "close_call", "Record how the call ended, judging from the whole conversation.",
    {"outcome": leaf("string",
        "promise: a promise was recorded. paid: customer said they already paid this past-due amount. transferred: handed to a person. no_promise: verified customer, no promise. not_verified: identity check did not pass. not_reached: the customer was not on the line or did not confirm who they are.",
        "outcome", ["promise", "paid", "transferred", "no_promise", "not_verified", "not_reached"]),
     "reason": leaf("string",
        "Omit for promise and paid. transferred: restructuring | human | support. no_promise: refused (refused after the offers, or said twice they do not want to talk) | hardship (illness, death in the family or job loss, declined the support team) | dispute (debt not theirs, never had the product, product closed or paid off in the past) | service_error (promise could not be recorded). not_verified: failed (three wrong answers) | declined (would not answer the security questions, or did not want to talk before verification). not_reached: callback | no_callback (no time inside the window) | wrong_number | deceased | unclear (could not confirm who is speaking).",
        "reason")},
    ["outcome"], pre=CLOSE_PRE)
CLOSE["config"]["alwaysRunsAt"] = ["end_of_call"]


def cond_eq(var, vals):
    return {"logic": "or", "conditions": [{"variable": var, "operator": "equals", "operand": v} for v in vals]}


# ---------------------------------------------------------------- prompts
SYSTEM = """You are Freya Bank's digital assistant on an outbound phone call. Speak English. One or two short sentences per turn. Address the customer as {{title}} {{last_name}}.
Hard rules for the whole call:
- Never invent figures, dates, reasons or terms. If you cannot answer a question from what you were given, say you do not have that information.
- Never offer a discount, a waiver, an instalment plan or any term not given to you. Do not name a currency.
- After every tool result, either speak to the customer or call the next tool. Never end a turn with nothing. Obey the what_to_do_next field of a tool result.
- Never say something is recorded, booked or transferred unless the tool result says it worked.
- If asked whether you are a robot or an AI: say you are Freya Bank's digital assistant, then continue.
- If asked whether this is a scam: say they can verify the call by phoning Freya Bank's customer service number, then continue.
- If the customer asks for a human: first ask once whether you can help. If they insist, call transfer_to_agent with queue general, say you are transferring them, and say goodbye.
- Every goodbye: thank the customer, say goodbye, and end with exactly "Have a good day." That phrase ends the call, so use it only when the call is over.
Dates: {{date_facts}}"""

GREET_TASK = """You have said the opening line and asked whether you are speaking with {{title}} {{last_name}}. Do NOT say "collections", "debt", "payment", a product, an amount or why you are calling. This applies to everyone, including relatives. No tool call except schedule_callback and end_call.

Only "yes", "that's me", "speaking" or the customer's own name counts as confirmation. "Hello", "go ahead", "who is this" do not.
- If the answer is unclear: answer any question they asked first (who you are: Freya Bank's digital assistant; scam: they can verify by phoning Freya Bank's customer service number), then ask "Am I speaking with {{title}} {{last_name}}?" once more. If it is still unclear after that second ask, thank them, say goodbye, end with "Have a good day."
- If they say twice that they do not want to talk, thank them and say goodbye.
- If someone else answers (a relative or anyone else): say nothing about why you are calling or about any account, even if they ask or offer to pay; say only that you cannot discuss it. Ask when {{first_name}} {{last_name}} can be reached. {{callback_facts}} If the day and time they give are inside the window, call schedule_callback with the date (YYYY-MM-DD) and time (HH:MM), then thank them and say goodbye. If outside, ask once for another time. If the second answer is also outside, do not schedule; thank them and say goodbye.
- If they say this number does not belong to {{first_name}} {{last_name}}: apologise, thank them, say goodbye.
- If they say {{first_name}} {{last_name}} has died: say exactly "I am sorry for your loss." Ask nothing else, then say goodbye ending with "Have a good day."
"""

IDENTITY_TASK = """The person confirmed they are {{title}} {{last_name}}. Verify identity before anything else. Do NOT say "collections", "debt", "payment", a product or an amount in this step.
1. Ask for the date of birth. When they answer, call verify_identity with field date_of_birth and the date as YYYY-MM-DD, whatever way they said it. A date given only in numbers is day, then month, then year.
2. Then ask for the last four digits of the phone number on file and call verify_identity with field phone_last4.
Ask one question at a time. Follow what_to_do_next in every result: a wrong answer is asked again; a day_month_swapped hint means ask them to say the month as a word (not a wrong answer); after the third wrong answer in total, stop: tell them to use the mobile app or a branch and say goodbye. Never state any amount, even if they ask.
If they do not want to answer, or ask what the call is about instead of answering: explain once that the questions protect their account and ask again. If they refuse or ask that again a second time, thank them and say goodbye ending with "Have a good day."
Only tools: verify_identity, transfer_to_agent (insisting on a human), end_call."""

NEGOTIATE_TASK = """The customer is verified. Your job: state the debt and get a payment promise under the bank's rules.

{{account_facts}}

TOOLS: create_promise, transfer_to_agent, end_call. When a rule says to use a tool, call it.

OPENING (first turn): say you are calling from the collections team about a late payment, name the product exactly as above, state the past-due amount and how many days late it is. Then ask exactly: "Can you make this payment today?" Never ask about today again after that.

AMOUNTS: always ask for the full past-due amount first. NEVER ask "how much can you pay?" or any question asking the customer to name an amount; you propose every amount. If they ask you what to pay, propose the amount yourself.
- Customer says the full amount is too much: offer the floor once and say the rest stays overdue.
- Customer proposes an amount from the floor up to the full amount (both included): accept it.
- Below the floor: say it cannot be recorded and offer the floor once.
- Refusing the floor = flat refusal.

DATES: a promise date must be today or later, a business day (B in the calendar), and not after the deadline.
- Weekend or holiday not after the deadline: say it is not a business day and offer the next business day.
- A date after the deadline: say the latest date you can record is the deadline and offer it. Refusing the deadline = flat refusal.
- A vague period ("next week", "the week after next", "end of the month", "when my salary comes"): ask once for the exact day. If they still give none, propose the deadline.
- Use the this/next weekday lines for "this Friday" / "next Friday".
A date or an amount the customer proposes is never a refusal.

FLAT REFUSAL or non-answer (including a plain "no" to paying today, with no date and no amount): use ONE persuasion attempt per refusal, in this order, one offer per turn:
- Attempt 1 offer as listed above. After a "no" to today, go straight to the attempt 1 offer.
- Attempt 2 offer as listed above (late band only).
When the allowed attempts are used up: stop. Do not repeat an offer already refused. Thank them and say goodbye (no promise).

HARDSHIP (illness, a death in the family, job loss): say one short sentence of sympathy, make NO persuasion attempt, and offer once to connect them with the customer support team. If they accept: call transfer_to_agent with queue support. If they decline: thank them and say goodbye. A request for a discount gets: you cannot offer that. If they still name a date or amount themselves, handle it normally.
ALREADY PAID this past-due amount: say payments can take one business day to appear. Take no promise. Thank them and say goodbye.
DISPUTE ("not mine", "I never had this product", it was closed or paid off in the past): do not argue, take no promise, thank them and say goodbye.
NEW PAYMENT PLAN or LOWER INSTALMENTS requested: do not describe any plan and do not offer the floor; call transfer_to_agent with queue restructuring.
Says twice they do not want to talk: thank them and say goodbye.

CONFIRMING: when amount and date are agreed, read back the product, the amount and the date (weekday and date) and ask "Do you confirm?". If they change the date or the amount, check it against the rules and read back again. Only after a clear yes, call create_promise with the amount and the date as YYYY-MM-DD. Before that, never say "noted" or "recorded". Follow what_to_do_next of the result: on failure call create_promise once more with the same values; if it fails again say honestly that you could not record it. Only after success say it is recorded and then: "You will receive a text message confirming this promise." A recorded promise cannot be changed or cancelled in this call; if asked, say they can change it in the mobile app.

CLOSING: thank the customer and say goodbye, ending with exactly "Have a good day." After a transfer, say you are transferring them and say goodbye the same way."""


# ---------------------------------------------------------------- nodes
def conv(name, task, tools, transitions, on_enter, extraction=None, turns=60):
    n = {"name": name, "node_type": "conversation", "task_message": task, "tools": tools,
         "on_enter": on_enter, "on_enter_first_entry_only": True, "transitions": transitions,
         "max_node_turns": turns}
    if extraction:
        n["extraction_schema"] = extraction
    return n


def code_node(name, code, nxt):
    return {
        "name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": nxt,
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
            "parameters": {"type": "object", "properties": {"code": {"type": "string", "default": code}, "timeout_ms": {"type": "number", "default": 10000}}}}}],
        "transitions": [{"target_node": nxt, "description": "always", "condition": {"operator": "always"}}],
    }


nodes = {
    "setup": code_node("setup", SETUP_CODE, "greet"),
    "greet": conv("greet", GREET_TASK, [CALLBACK, END_CALL], [
            {"target_node": "identity", "description": "The person clearly confirmed they are the customer",
             "condition": cond_eq("person", ["customer"])},
        ],
        {"type": "tts", "text": "Hello, this is the digital assistant calling from Freya Bank. Please note that we record this call. Am I speaking with {{title}} {{last_name}}?"},
        extraction=[{"name": "person", "type": "string", "enum_values": ["customer", "someone_else", "unclear"],
                     "description": "Who answered. customer ONLY if, in reply to 'Am I speaking with {{title}} {{last_name}}?', they said yes / that's me / speaking / their own name. someone_else if they say they are another person or the customer is not there. unclear for hello, go ahead, who is this, or anything else.",
                     "min_confidence": 0.7}]),
    "identity": conv("identity", IDENTITY_TASK, [VERIFY, TRANSFER, END_CALL], [
            {"target_node": "load_account", "description": "Both security answers verified",
             "condition": cond_eq("verify_identity_response.data.all_verified", ["true", "True"])},
        ],
        {"type": "llm", "prompt": "Thank them and ask for their date of birth. Say nothing about why you are calling."}),
    "load_account": {
        "name": "load_account", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "account_facts",
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [{"type": "function", "config": {"timeoutMs": 12000, "maxRetries": 2}, "function": {
            "name": "get_account", "handler": "__function__:api_call", "description": "Get the late product.",
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string", "default": BANK + "get_account"},
                "method": {"type": "string", "default": "POST"},
                "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                "body": {"type": "object", "required": [], "properties": {"customer_id": {"type": "string", "default": "{{customer_id}}"}}}}}}}],
        "response_mapping": [{"path": "data.products", "variable": "products"}],
        "transitions": [{"target_node": "account_facts", "description": "always", "condition": {"operator": "always"}}],
    },
    "account_facts": code_node("account_facts", ACCOUNT_CODE, "negotiate"),
    "negotiate": conv("negotiate", NEGOTIATE_TASK, [PROMISE, TRANSFER, END_CALL], [],
        {"type": "llm", "prompt": "Thank the customer for confirming. Then do the OPENING: collections team, late payment, the product named in words, the past-due amount and the days late, then ask \"Can you make this payment today?\""},
        turns=80),
}

wf = {
    "initial_node": "setup",
    "system_prompt": SYSTEM,
    "nodes": nodes,
    "global_nodes": {},
    "tools": [CLOSE],
    "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"},
}

for code in (SETUP_CODE, ACCOUNT_CODE, VERIFY_PRE, VERIFY_POST, CALLBACK_PRE, PROMISE_PRE, PROMISE_POST, GENERIC_POST, CLOSE_PRE):
    assert "{{" not in code and "}}" not in code
    compile(code, "x", "exec")
out = pathlib.Path(__file__).with_name("brief-a.workflow.json")
out.write_text(json.dumps(wf, indent=1))
print("wrote", out)
