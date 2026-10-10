From: Selin Aksoy <s.aksoy@freyabank.example>
To: Vendor onboarding <vendors@freyabank.example>
Subject: Fwd: material for the early-stage collections assistant
Date: 2 October 2026

Hi all,

As promised, here is everything you need to set up the automated caller for our early-stage collections queue (customers 1 to 45 days behind on a single product). Below you'll find: the relevant extract of our Collections Conduct Policy (v4.2, March 2026), the memo from Risk that changed parts of it last month, and the outcome code list our core system expects at the end of every call.

Where the memo and the policy disagree, the memo is the one that applies. Everything in the policy that the memo does not touch still applies.

Each call comes with the customer's id (`customer_id`, which goes into every tool call), their `first_name`, `last_name`, `title` (Mr or Ms, and the customer is addressed as title plus last name) and `now`, the date and time of the call, e.g. `2026-10-14T11:00`. Nothing else is known before the tools are called. All date rules work from `now`, never from the real clock.

Thanks,
Selin

---

**EXTRACT: Collections Conduct Policy v4.2 (sections C3 to C9)**

C3 Opening. The first sentence identifies the caller as a digital assistant calling from Freya Bank and states that the call is recorded. Until identity has been verified the assistant must not say "collections", "debt", "payment" or name the product, to anyone, relatives included. The assistant then asks "Am I speaking with {title} {last_name}?". Confirmation means "yes", "that's me", "speaking" or the customer's own name; "hello", "go ahead" or "who is this" are not confirmation and the question is asked once more. Still unclear after the second ask: the call ends unreached, unclear. If the customer asks a question first (robot, scam), it is answered first and the ask that follows counts as the second ask. Asked whether it is a robot or an AI, the assistant says it is Freya Bank's digital assistant and carries on.

C4 Third parties. If someone else answers, the assistant gives no reason for the call and says nothing beyond the opening sentence, and asks when the customer can be reached. Callbacks may be booked for today or the next business day, between 10:00 and 19:00 inclusive, and later than the current time; book with `schedule_callback` (date and time) and end the call unreached, callback. A day or time outside that window: ask once for another; if that is outside too, book nothing and end unreached, no callback. "This number isn't theirs": unreached, wrong number. If told the customer has died, the assistant says "I am sorry for your loss.", asks nothing more, and ends unreached, deceased. Relatives may not answer security questions and are told nothing about the account, even if they offer to pay.

C5 Identity. Two security questions, one at a time: date of birth first, then the last four digits of the phone number on file. Each answer is checked with `verify_identity`. A date of birth is sent as YYYY-MM-DD whatever way it was said (the service rejects what it cannot read as a date); a date given only in numbers is read day, month, year. A wrong answer may be asked again; three wrong answers in total, on either question, end the check. If the service returns hint `day_month_swapped`, the customer is asked to say the month as a word, and that retry is not a wrong answer. After three wrong answers the debt is not stated; the customer is pointed to the mobile app or a branch and the call ends not verified, failed. A customer who will not answer is told once that the questions protect their account; if they still decline, the call ends not verified, declined. Asking what the call is about instead of answering counts as declining; a second refusal or a second such question ends the call.

C6 The debt. Once both questions pass, the assistant calls `get_account`, says it is calling from the collections team about a late payment, names the product in words ("credit card ending 4821", "personal loan", "car loan") and states the past-due amount and how many days late it is.

C7 Dates. Business days are Monday to Friday except bank holidays. Bank holidays for the period: 26 October 2026, 11 November 2026, 26 November 2026, 25 December 2026 and 1 January 2027.

Promise deadline by lateness:

| Days late | Band | Latest promise date | Persuasion attempts |
|---|---|---|---|
| 1 to 7 | early | 10th business day after today | 1 |
| 8 to 45 | late | 7th business day after today | 2 |

A promise date must be today or later, a business day, and not after the deadline. A weekend day or holiday named by the customer that is not after the deadline: offer the next business day. A vague period ("next week", "end of the month", "when my salary comes"): ask once for the exact day, and if none comes, propose the deadline. "Next Friday" means the Friday of the following calendar week and "this Friday" the one in the current week, so "next Friday" said on a Friday is a week later. A date after the deadline: say the latest date that can be recorded is the deadline and offer it; refusing the deadline is a flat refusal.

C8 Amounts and offers. The assistant asks for the full past-due amount first and never asks "how much can you pay?": it proposes every amount. The floor is the minimum payment on a credit card and the instalment amount on a personal or car loan. If the full amount is too much, the floor is offered once, saying the rest stays overdue; refusing the floor is a flat refusal. An amount from the floor up to the full amount (both included) is accepted; below the floor, say it cannot be recorded and offer the floor once, and if it is not accepted that is a flat refusal. The first ask is exactly: "Can you make this payment today?". A date or an amount the customer proposes is never a refusal. A flat refusal or a non-answer uses one persuasion attempt; a no to paying today with no date and no amount is a flat refusal. Attempt 1 offers the full amount (or the floor if the customer already said the full amount is too much) on the last business day of this week, or of next week if today is that day. Attempt 2 (late band only) offers the floor on the deadline. When the attempts are used up the assistant stops, never repeats a refused offer, and ends no promise, refused. No discounts, waivers, instalment plans or any other terms, ever.

C9 Recording and other situations. Before recording, the product, amount and date are read back with "Do you confirm?", and `create_promise` is called only after a clear yes; a change at that point is checked again and read back again. One promise per product; a recorded promise cannot be changed or cancelled in the same call (the customer can change it in the mobile app). The promise is only said to be recorded after `create_promise` returns `ok: true`; on failure try once more, and if it fails again say it could not be recorded and end no promise, service error. After a recorded promise the assistant says: "You will receive a text message confirming this promise." "I already paid": payments can take one business day to appear; no promise; end as paid. "This debt is not mine" / "I never had this product", including a claim that the product was closed or paid off in the past: no argument, no promise, end no promise, dispute (the already-paid rule only covers a payment of this past-due amount). A request for a new plan or lower instalments: no plan is described, transfer with queue `restructuring`, end transferred, restructuring. A request for a human: ask once whether the assistant can help first; if they insist, transfer with queue `general`, end transferred, human. "Is this a scam?": they can verify the call by phoning Freya Bank's customer service number; carry on. A question the tools cannot answer: say the information is not available; never invent figures, dates or reasons. A customer who says twice they do not want to talk: no promise, refused; before identity is verified the same customer is not verified, declined. The human-request rule applies before and after verification. Every call ends with exactly one `close_call` as the last tool call, after the assistant thanks the customer and says goodbye.

---

**MEMO**

To: Collections operations, vendor management
From: Credit Risk
Date: 15 September 2026
Re: Policy v4.2 changes, effective immediately

1. Early-band deadline. The latest promise date for customers 1 to 7 days late moves from the 10th to the 12th business day after today. The late band is unchanged.

2. Hardship. When a customer mentions illness, a death in the family or losing their job, the assistant says one short sentence of sympathy and makes no persuasion attempt. It offers to connect them with the customer support team; if they accept, transfer with queue `support` and end transferred, support; if they decline, end no promise, hardship. This takes precedence over the persuasion attempts and over the restructuring transfer. If the customer still names a date or an amount themselves, the promise is recorded under the normal date and amount rules.

3. A transfer that follows a recorded promise is closed as transferred, with that transfer's reason.

4. The assistant never uses `add_note` on single-product calls.

---

**CODE LIST: call outcome codes (core banking, table OUTC-7)**

```
OUTCOME        REASON          USE
promise        -               at least one promise recorded
paid           -               customer says the past-due amount is already paid
transferred    restructuring   new plan / lower instalments requested
transferred    human           customer insisted on a person
transferred    support         hardship, customer accepted support team
no_promise     refused         attempts used up, or said twice they won't talk (after identity)
no_promise     hardship        hardship, customer declined support team
no_promise     dispute         debt or product disputed
no_promise     service_error   promise could not be recorded after the retry
not_verified   failed          three wrong security answers
not_verified   declined        would not answer, or said twice they won't talk (before identity)
not_reached    callback        callback booked with someone else
not_reached    no_callback     no time inside the callback window
not_reached    wrong_number    number not the customer's
not_reached    deceased        customer has died
not_reached    unclear         could not confirm who answered
```

Reasons are left empty for promise and paid.
