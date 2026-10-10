"""Generate out/brief-b.workflow.json (Brief B = Brief A + up to three products)."""
import json, pathlib

BANK = "https://freya-bank-mock.freyavoice.workers.dev/v1/"
HOLIDAYS = ["2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"]  # from the brief, section 7

# ---------------------------------------------------------------- code (no double braces anywhere)
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
    lines.append('DEADLINE early band (1-7 days late, 12th business day after today): ' + spoken(early) + ' (' + early.isoformat() + ').')
    lines.append('DEADLINE late band (8-45 days late, 7th business day after today): ' + spoken(late) + ' (' + late.isoformat() + ').')
    lines.append('PERSUASION ATTEMPT 1 DATE (last business day of this week, or of next week if that is today): ' + spoken(lw) + ' (' + lw.isoformat() + ').')
    lines.append('THIS <weekday> = that weekday in the current Monday-Sunday week. NEXT <weekday> = that weekday in the following week.')
    tw = []; nw = []
    for i in range(7):
        a = monday + datetime.timedelta(days=i); b = a + datetime.timedelta(days=7)
        tw.append('this ' + NAMES[i] + ' = ' + a.isoformat()); nw.append('next ' + NAMES[i] + ' = ' + b.isoformat())
    lines.append('; '.join(tw)); lines.append('; '.join(nw))
    lines.append('CALENDAR (B = business day, X = weekend or bank holiday, cannot be a promise date):')
    for i in range(0, 50):
        d = today + datetime.timedelta(days=i)
        tag = 'B' if isbd(d) else ('X holiday' if d.isoformat() in HOL else 'X weekend')
        lines.append('  ' + d.isoformat() + ' ' + NAMES[d.weekday()] + ' ' + tag + (' (today)' if i == 0 else ''))
    vars['date_facts'] = chr(10).join(lines)
    vars['today_iso'] = today.isoformat()
    vars['deadline_early'] = early.isoformat()
    vars['deadline_late'] = late.isoformat()
    vars['next_bd_iso'] = nbd.isoformat()
    vars['attempt1_iso'] = lw.isoformat()
    vars['attempt1_spoken'] = spoken(lw)
    vars['spoken_early'] = spoken(early)
    vars['spoken_late'] = spoken(late)
    vars['callback_facts'] = ('A callback can be booked for today (' + today.isoformat() + ') at a time later than ' + hhmm + ' and from 10:00 to 19:00, or for the next business day ' + spoken(nbd) + ' (' + nbd.isoformat() + ') from 10:00 to 19:00. Both ends included. Anything else is outside the window. "Tomorrow" means ' + (today + one).isoformat() + '.')
    vars['setup_state'] = 'ok'
except Exception as e:
    vars['date_facts'] = 'Date facts unavailable: ' + str(e)
    vars['callback_facts'] = 'Callback window: today after now or next business day, 10:00 to 19:00.'
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
    for k, v in list(vars.items()):
        if isinstance(v, dict):
            d = v.get('data') if isinstance(v.get('data'), dict) else v
            if isinstance(d, dict) and isinstance(d.get('products'), list) and d.get('products'): return d.get('products')
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
    lines = []; order = []
    for p in prods:
        pid = str(p.get('product_id')); order.append(pid)
        t = str(p.get('type'))
        if t == 'credit_card':
            name = 'credit card ending ' + str(p.get('card_last4')); floor = p.get('minimum_payment'); fname = 'minimum payment'
        elif t == 'personal_loan':
            name = 'personal loan'; floor = p.get('instalment_amount'); fname = 'instalment amount'
        else:
            name = 'car loan'; floor = p.get('instalment_amount'); fname = 'instalment amount'
        dl = int(float(p.get('days_late') or 0))
        a1 = str(vars.get('attempt1_spoken')) + ' (' + str(vars.get('attempt1_iso')) + ')'
        if dl <= 7:
            band = 'early'; deadline = vars.get('deadline_early'); attempts = 1
            offers = ' Attempt 1 offer: the full ' + money(p.get('past_due')) + ' on ' + a1 + ' (only if the customer already said the full amount is too much: the floor ' + money(floor) + ' on that date instead; never name both amounts). No attempt 2 (early band): after attempt 1 is refused, stop.'
        else:
            band = 'late'; deadline = vars.get('deadline_late'); attempts = 2
            offers = ' Attempt 1 offer: the full ' + money(p.get('past_due')) + ' on ' + a1 + ' (only if the customer already said the full amount is too much: the floor ' + money(floor) + ' on that date instead; never name both amounts). Attempt 2 offer: the floor ' + money(floor) + ' on the deadline ' + str(vars.get('spoken_late')) + ' (' + str(deadline) + '). After attempt 2 is refused, stop.'
        vars['deadline_' + pid] = deadline
        vars['floor_' + pid] = floor
        vars['past_due_' + pid] = p.get('past_due')
        lines.append('- product_id ' + pid + ': ' + name + '. Past-due amount ' + money(p.get('past_due')) + ', ' + str(dl) + ' days late. Floor (' + fname + ') ' + money(floor) + '. Band ' + band + ', deadline ' + str(deadline) + ', persuasion attempts allowed: ' + str(attempts) + '.' + offers)
    if lines:
        vars['account_facts'] = 'LATE PRODUCTS, in this order (' + str(len(lines)) + '):' + chr(10) + chr(10).join(lines)
        vars['account_state'] = 'ok'
    else:
        vars['account_facts'] = 'The account details could not be loaded. Do not state or invent any amount.'
        vars['account_state'] = 'empty'
    vars['product_order'] = ','.join(order)
except Exception as e:
    vars['account_facts'] = 'The account details could not be loaded. Do not state or invent any amount.'
    vars['account_state'] = 'error'
    vars['product_order'] = ''
'''

STRIP = "        result.pop('header', None)\n"

VERIFY_PRE = r'''
import re, datetime
try:
    b = config.get('body')
    if isinstance(b, dict):
        a = str(b.get('answer') or '').strip()
        if b.get('field') == 'phone_last4':
            dg = re.sub(r'\D', '', a)
            if len(dg) >= 4: b['answer'] = dg[-4:]
        else:
            m = re.match(r'^(\d{1,2})[./\- ](\d{1,2})[./\- ](\d{4})$', a)
            if m:
                b['answer'] = '%s-%02d-%02d' % (m.group(3), int(m.group(2)), int(m.group(1)))
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
                msg = 'Both security answers are correct. The customer is verified. Thank them briefly.'
            elif d.get('hint') == 'day_month_swapped':
                msg = 'Day and month look swapped. This is NOT counted as a wrong answer. Ask the customer to say their date of birth again with the month as a word.'
            elif d.get('ok') in (False, 'false', 'False') and d.get('verified') is None:
                msg = 'The answer could not be read (' + str(d.get('error')) + '). Not counted as a wrong answer. Ask for the same answer again.'
            elif d.get('verified') in (True, 'true', 'True'):
                msg = 'Correct. Now ask the next security question: the last four digits of the phone number on file.'
            elif left is not None and int(left) <= 0:
                msg = 'Third wrong answer: the security check has FAILED. Do not state any debt, amount or product. Tell the customer to use the Freya Bank mobile app or visit a branch, thank them and say goodbye, ending with "Have a good day."'
            else:
                msg = 'That answer is wrong. Say it does not match and ask the SAME question again. Wrong answers left: ' + str(left) + '.'
            d['what_to_do_next'] = msg
except Exception:
    pass
'''

PROMISE_PRE = r'''
import datetime
HOL = HOLIDAYS_LIST
try:
    b = config.get('body')
    if isinstance(b, dict):
        pid = str(b.get('product_id') or '').strip()
        b['product_id'] = pid
        vars['cp_last_pid'] = pid
        dl = vars.get('deadline_' + pid)
        ds = str(b.get('date') or '')[:10]
        d = datetime.date.fromisoformat(ds)
        if dl:
            dld = datetime.date.fromisoformat(str(dl)[:10])
            if d > dld:
                d = dld
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
        pid = str(vars.get('cp_last_pid') or '')
        if isinstance(d, dict) and d.get('ok') in (True, 'true', 'True') and d.get('promise_id'):
            vars['promises_recorded'] = int(vars.get('promises_recorded') or 0) + 1
            d['what_to_do_next'] = 'The promise for ' + pid + ' IS recorded. If other confirmed promises remain, call create_promise for the next one. Otherwise tell the customer the promise is recorded and say: "You will receive a text message confirming this promise."'
        else:
            k = 'cp_fail_' + pid
            n = int(vars.get(k) or 0) + 1
            vars[k] = n
            if isinstance(d, dict):
                d['ok'] = False
                tgt = d
            else:
                tgt = result
            if n < 2:
                tgt['what_to_do_next'] = 'FAILED: the promise for ' + pid + ' was NOT recorded. Do not say it is recorded. Call create_promise again right now with exactly the same values, once.'
            else:
                tgt['what_to_do_next'] = 'FAILED twice: the promise for ' + pid + ' could NOT be recorded. Tell the customer honestly that you could not record it. Do not try again.'
except Exception:
    pass
'''

NOTE_PRE = r'''
try:
    b = config.get('body')
    if isinstance(b, dict):
        log = str(vars.get('notes_log') or '')
        vars['notes_log'] = (log + ',' if log else '') + str(b.get('product_id')) + ':' + str(b.get('reason'))
except Exception:
    pass
'''

GENERIC_POST = r'''
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict) and d.get('ok') in (True, 'true', 'True'):
            d['what_to_do_next'] = 'Done. Now speak to the customer.'
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
            if isinstance(o, dict): o = o.get(part)
            else: o = None
        v = o
    return v
def num(x):
    try: return int(float(x))
    except Exception: return 0
try:
    b = config.get('body')
    if isinstance(b, dict):
        out = None; rsn = None
        tq = g('transfer_to_agent_args.queue')
        if num(g('transfer_to_agent_success_count')) > 0 and tq in ('restructuring', 'general', 'support'):
            out = 'transferred'; rsn = 'human' if tq == 'general' else tq
        elif num(g('schedule_callback_success_count')) > 0:
            out = 'not_reached'; rsn = 'callback'
        elif num(vars.get('promises_recorded')) > 0:
            out = 'promise'
        else:
            left = g('verify_identity_response.data.wrong_answers_left')
            allv = str(g('verify_identity_response.data.all_verified'))
            if left is not None and num(left) <= 0 and allv.lower() != 'true':
                out = 'not_verified'; rsn = 'failed'
            else:
                notes = [x for x in str(vars.get('notes_log') or '').split(',') if ':' in x]
                if notes:
                    m = dict()
                    for x in notes:
                        p, r = x.split(':', 1)
                        if p not in m: m[p] = r
                    order = [p for p in str(vars.get('product_order') or '').split(',') if p] or list(m.keys())
                    rs = [m[p] for p in order if p in m]
                    if rs and all(r == 'paid' for r in rs) and len(rs) == len(order):
                        out = 'paid'
                    else:
                        firsts = [r for r in rs if r != 'paid']
                        if firsts:
                            out = 'no_promise'; rsn = firsts[0]
        if out:
            b['outcome'] = out
            if rsn: b['reason'] = rsn
            else: b.pop('reason', None)
        if b.get('outcome') in ('promise', 'paid'):
            b.pop('reason', None)
except Exception:
    pass
'''

# ---------------------------------------------------------------- tool builders
def api_tool(name, desc, fields, required, pre="", post="", retries=0, mapping=None):
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
    if pre: t["pre_process_code"] = pre
    if post: t["post_process_code"] = post
    if mapping: t["response_mapping"] = mapping
    return t

def leaf(typ, desc, enum=None, var=None, name=None):
    d = {"type": typ, "description": desc, "default": "{{" + (var or name) + "}}"}
    if enum: d["enum"] = enum
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

VERIFY = api_tool("verify_identity",
    "Check ONE security answer. CALL it every time the customer gives a date of birth or phone digits, before saying anything about the answer.",
    {"field": leaf("string", "Which question this answers: date_of_birth or phone_last4.", ["date_of_birth", "phone_last4"], name="field"),
     "answer": leaf("string", "date_of_birth as YYYY-MM-DD (numbers-only dates are day, month, year; '14 March 1988' -> 1988-03-14). phone_last4 as exactly four digits.", name="answer")},
    ["field", "answer"], pre=VERIFY_PRE, post=VERIFY_POST)

CALLBACK = api_tool("schedule_callback",
    "Book a callback for the customer. CALL it only when the person gave a day and time inside the allowed callback window.",
    {"date": leaf("string", "Callback date YYYY-MM-DD.", name="date"),
     "time": leaf("string", "Callback time HH:MM, 24-hour, between 10:00 and 19:00.", name="time")},
    ["date", "time"], post=GENERIC_POST)

TRANSFER = api_tool("transfer_to_agent",
    "Hand the call to a person. CALL it with queue restructuring (customer wants a new payment plan or lower instalments), support (hardship customer accepted the support team) or general (customer insists on a human after you asked once if you can help).",
    {"queue": leaf("string", "One of: restructuring, general, support.", ["restructuring", "general", "support"], name="queue")},
    ["queue"], post=GENERIC_POST)

PROMISE = api_tool("create_promise",
    "Record ONE payment promise for ONE product. CALL it only after the customer said a clear yes to your read-back. One call per product.",
    {"product_id": leaf("string", "product_id exactly as in the late products list, for example p1.", name="product_id"),
     "amount": leaf("number", "Amount agreed for this product.", name="amount"),
     "date": leaf("string", "Promise date YYYY-MM-DD.", name="date")},
    ["product_id", "amount", "date"], pre=PROMISE_PRE, post=PROMISE_POST)

NOTE = api_tool("add_note",
    "Record why ONE product ends without a promise. CALL it once per product without a promise, at the end of the call, never when the call is transferred.",
    {"product_id": leaf("string", "product_id exactly as in the late products list.", name="product_id"),
     "reason": leaf("string", "One of: refused, hardship, dispute, paid, service_error.", ["refused", "hardship", "dispute", "paid", "service_error"], var="note_reason"),
     "text": leaf("string", "Short free text.", var="note_text")},
    ["product_id", "reason"], pre=NOTE_PRE, post=GENERIC_POST)

CLOSE = api_tool("close_call", "Record how the call ended, from the conversation.",
    {"outcome": leaf("string",
        "promise: at least one promise was recorded successfully (and no transfer). paid: customer said they already paid this past-due amount (all products). transferred: call was handed to a person. no_promise: verified customer, no promise. not_verified: identity check did not pass. not_reached: the customer was not on the line.",
        ["promise", "paid", "transferred", "no_promise", "not_verified", "not_reached"], name="outcome"),
     "reason": leaf("string",
        "Omit for promise and paid. transferred: restructuring | human | support. no_promise: refused (refused / did not want to talk) | hardship (illness, death, job loss, declined support team) | dispute (debt not theirs, product closed or paid off in the past) | service_error (promise could not be recorded). not_verified: failed (three wrong answers) | declined (would not answer the security questions or would not talk before verification). not_reached: callback | no_callback (no time inside the window) | wrong_number | deceased | unclear (could not confirm who is speaking).",
        name="reason")},
    ["outcome"], pre=CLOSE_PRE)
CLOSE["config"]["alwaysRunsAt"] = ["end_of_call"]

def cond_eq(var, vals):
    return {"logic": "or", "conditions": [{"variable": var, "operator": "equals", "operand": v} for v in vals]}

# ---------------------------------------------------------------- prompts
SYSTEM = """You are the digital assistant of Freya Bank on an outbound phone call. Speak English. One or two short sentences per turn. Address the customer as {{title}} {{last_name}}.
Hard rules for the whole call:
- Never invent figures, dates, reasons or terms. If you do not have some information, say you do not have that information.
- Never offer a discount, a waiver, an instalment plan or any term the bank did not give you. Do not name a currency.
- After every tool result, either speak to the customer or call the next tool. Never end a turn with nothing. Obey the what_to_do_next field of a tool result.
- Never say something is recorded, booked or transferred unless the tool result says ok.
- If asked whether you are a robot or an AI: say you are Freya Bank's digital assistant, then continue.
- If asked whether this is a scam: say they can verify the call by phoning Freya Bank's customer service number, then continue.
- If the customer asks for a human: first ask once whether you can help. If they insist, call transfer_to_agent with queue general, tell them you are transferring them, and say goodbye.
- Every goodbye: thank the customer, say goodbye, and end with exactly "Have a good day." That phrase ends the call, so use it only when the call is over.
Dates: {{date_facts}}"""

GREET_TASK = """You have just said the opening line and asked whether you are speaking with {{title}} {{last_name}}. Do NOT say "collections", "debt", "payment", a product, an amount or why you are calling. This applies to everyone, including relatives. No tool except the ones below.

Only "yes", "that's me", "speaking" or the customer's own name counts as confirmation. "Hello", "go ahead", "who is this" do not.
- If the answer is unclear, answer any question they asked first (who you are: Freya Bank's digital assistant), then ask "Am I speaking with {{title}} {{last_name}}?" once more. If it is still unclear after that second ask, thank them, say goodbye, end with "Have a good day."
- If they refuse to talk twice, thank them and say goodbye.
- If someone else answers (relative, colleague, etc.): do not say why you are calling and tell them nothing about any account, even if they ask or offer to pay. Ask when {{first_name}} {{last_name}} can be reached. {{callback_facts}} If the offered day/time is inside the window, call schedule_callback with date and time (HH:MM), then thank them and say goodbye. If it is outside, ask once for another time. If the second answer is also outside, do not schedule; thank them and say goodbye.
- If they say this number does not belong to {{first_name}} {{last_name}}: apologise, thank them, say goodbye.
- If they say {{first_name}} {{last_name}} has died: say exactly "I am sorry for your loss." Ask nothing else, then say goodbye ending with "Have a good day."
"""

IDENTITY_TASK = """The person confirmed they are {{title}} {{last_name}}. Verify identity before anything else. Do NOT say "collections", "debt", "payment", a product or an amount yet.
1. Ask for the date of birth. When they answer, call verify_identity with field date_of_birth and the date as YYYY-MM-DD, whatever way they said it. A date given only in numbers is day, then month, then year.
2. Then ask for the last four digits of the phone number on file and call verify_identity with field phone_last4.
Ask one question at a time. Follow what_to_do_next in every result: a wrong answer is asked again (the same question); a "day_month_swapped" hint means ask them to say the month as a word (not a wrong answer); after the third wrong answer in total, stop, tell them to use the mobile app or a branch, say goodbye.
If they do not want to answer, or ask what the call is about instead of answering: explain once that the questions protect their account and ask again. If they refuse or ask again a second time, thank them and say goodbye ending with "Have a good day."
Never mention any account detail in this step."""

NEGOTIATE_TASK = """The customer is verified. Your job: state the debt and get payment promises under the bank's rules.

{{account_facts}}

TOOLS: create_promise (one per product, only after one clear "yes" to the full read-back), add_note (Brief B notes, see below), transfer_to_agent, end_call. When a rule says to use a tool, call it.

OPENING (first turn only): say you are calling from the collections team about a late payment. State every late product in its own sentence, in the list order: name it in words exactly as listed (e.g. "credit card ending 4821", "personal loan", "car loan"), its past-due amount and how many days late. Then ask: with one product "Can you make this payment today?"; with several "Can you pay all of them today?". Never ask about today again for each product.

PER PRODUCT (if not all today, go through the products one by one in list order; each product starts at attempt 1; attempts are counted per product):
AMOUNTS: ask for the full past-due amount. Never ask how much they can pay; you propose every amount. Floor = the product's floor. If the full amount is too much: offer the floor once and say the rest stays overdue. Customer-proposed amount from floor to full (inclusive): accept. Below floor: say it cannot be recorded and offer the floor once. Refusing the floor = flat refusal.
DATES: a promise date must be today or later, a business day (B in the calendar), and not after that product's deadline. Weekend/holiday not after the deadline: offer the next business day. A date after the deadline: say the latest date you can record is the deadline and offer it; refusing the deadline = flat refusal. Vague period ("next week", "end of the month", "when my salary comes"): ask once for the exact day; if still none, propose the deadline. Use the this/next weekday lines; a date the customer proposes is never a refusal.
FLAT REFUSAL or non-answer for a product (including "no" to paying today, or "I won't pay X", with no date and no amount): make that product's persuasion offers exactly as listed under the product, one offer per turn, and wait for the answer to each:
 - Attempt 1 offer (every product). Do NOT ask again about paying that product today; go straight to the attempt 1 offer.
 - Attempt 2 offer: late band only, made after attempt 1 is refused. Never skip it for a late-band product. Never make it for an early-band product.
 - When the product's attempts are used up: stop, do not repeat a refused offer; that product has no promise (refused). Move to the next product.
If the customer already refused a product (for example "I won't pay the car loan" in answer to the today question), your FIRST message about that product is its attempt 1 offer: do not first ask whether they can pay it, the full amount, or today. Each question you ask after a refusal counts as an attempt, so a product gets exactly its listed offers and nothing more. Name one amount per offer.
Handle exactly one product at a time. Settle it (agreed amount and date, or no promise) before mentioning the next product.
HARDSHIP (illness, a death in the family, job loss): one short sentence of sympathy, no persuasion at all, offer once to connect them with the customer support team. Accept: call transfer_to_agent queue support. Decline: no promise (hardship) for the remaining products. If they still name a date or amount themselves, handle it normally.
ALREADY PAID this past-due amount: say payments can take one business day to appear; no promise for that product (paid). Continue with other products.
DISPUTE ("not mine", "never had it", "it was closed / paid off long ago"): do not argue, no promise for that product (dispute). Continue with other products.
NEW PAYMENT PLAN / LOWER INSTALMENTS: do not describe any plan. Call transfer_to_agent queue restructuring. Agreed promises not yet recorded are NOT recorded.
Does not want to talk, said twice: stop; remaining products are refused.

Never say "noted", "recorded" or "registered" about a promise before create_promise returned ok; while collecting, just say you will read everything back at the end.
CONFIRMING: when every product is settled, read all agreed promises back together (product, amount, date for each; if one product's date was moved to its deadline, say so) and ask "Do you confirm?". If they change something, check it against the rules and read back again. Only after a clear yes, call create_promise once per agreed product, one call per message, with the date as YYYY-MM-DD. If a create_promise fails, follow what_to_do_next (retry once with the same values; after a second failure say honestly you could not record it). Say a promise is recorded only after ok true. After recorded promises say: "You will receive a text message confirming this promise." A recorded promise cannot be changed or cancelled in this call; if asked, say they can change it in the mobile app.

NOTES (only if the call is NOT transferred): after the promises are handled and before the goodbye, call add_note once for each product without a recorded promise, reason refused, hardship, dispute, paid or service_error (a promise that failed twice). This also applies when no product has a promise. Never call add_note if you transferred or will transfer the call.

CLOSING: thank the customer and say goodbye, ending with exactly "Have a good day." After a transfer, say you are transferring them and say goodbye the same way."""

# ---------------------------------------------------------------- nodes
def conv(name, task, tools, transitions, on_enter, extraction=None, turns=60):
    n = {"name": name, "node_type": "conversation", "task_message": task, "tools": tools,
         "on_enter": on_enter, "on_enter_first_entry_only": True, "transitions": transitions,
         "max_node_turns": turns}
    if extraction: n["extraction_schema"] = extraction
    return n

nodes = {
    "setup": {
        "name": "setup", "node_type": "code", "passthrough": True, "passthrough_default_transition": "greet",
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
            "parameters": {"type": "object", "properties": {"code": {"type": "string", "default": SETUP_CODE}, "timeout_ms": {"type": "number", "default": 10000}}}}}],
        "transitions": [{"target_node": "greet", "description": "always", "condition": {"operator": "always"}}],
    },
    "greet": conv("greet", GREET_TASK, [CALLBACK, END_CALL], [
            {"target_node": "identity", "description": "The person clearly confirmed they are the customer",
             "condition": cond_eq("person", ["customer"])},
        ],
        {"type": "tts", "text": "Hello, this is Freya Bank's digital assistant calling. This call is recorded. Am I speaking with {{title}} {{last_name}}?"},
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
            "name": "get_account", "handler": "__function__:api_call", "description": "Get the late products.",
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string", "default": BANK + "get_account"},
                "method": {"type": "string", "default": "POST"},
                "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                "body": {"type": "object", "required": [], "properties": {"customer_id": {"type": "string", "default": "{{customer_id}}"}}}}}}}],
        "response_mapping": [{"path": "data.products", "variable": "products"}],
        "transitions": [{"target_node": "account_facts", "description": "always", "condition": {"operator": "always"}}],
    },
    "account_facts": {
        "name": "account_facts", "node_type": "code", "passthrough": True, "passthrough_default_transition": "negotiate",
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
            "parameters": {"type": "object", "properties": {"code": {"type": "string", "default": ACCOUNT_CODE}, "timeout_ms": {"type": "number", "default": 10000}}}}}],
        "transitions": [{"target_node": "negotiate", "description": "always", "condition": {"operator": "always"}}],
    },
    "negotiate": conv("negotiate", NEGOTIATE_TASK, [PROMISE, NOTE, TRANSFER, END_CALL], [],
        {"type": "llm", "prompt": "Thank the customer for confirming. Then do the OPENING: collections team, late payment, every late product in its own sentence (name in words, past-due amount, days late), then ask about paying today."},
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

for code in (SETUP_CODE, ACCOUNT_CODE, VERIFY_PRE, VERIFY_POST, PROMISE_PRE, PROMISE_POST, NOTE_PRE, GENERIC_POST, CLOSE_PRE):
    assert "{{" not in code and "}}" not in code
    compile(code, "x", "exec")
out = pathlib.Path(__file__).with_name("brief-b.workflow.json")
out.write_text(json.dumps(wf, indent=1))
print("wrote", out)
