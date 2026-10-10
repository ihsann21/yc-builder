# Brief G: Freya Bank, early-stage collections, up to three products, tau-adapted escalation

Freya Bank is fictional. Every customer, debt and payment here is synthetic.

This is a complete, standalone brief for collections on one to three products. Supply this file and the existing Freya Bank collections OpenAPI from the organizer kit; no other brief is needed. The source note distinguishes inherited rules from the combined evaluation policy.

This brief has the density of a real bank specification. Read all of it. Most failed cases come from one rule that was skipped.

## 1. The job

Freya Bank calls customers who are 1 to 45 days late on one to three products. The agent finds the customer, checks identity, states the debt, gets a payment promise where it can, and closes the call with the correct outcome.

## 2. Call variables

Every call starts with these. Nothing else is known before the tools are called.

| Variable | Example | Meaning |
|---|---|---|
| `customer_id` | `c_4f2a...` | Pass it to every tool call. |
| `first_name`, `last_name` | `Daniel`, `Reyes` | The person to ask for. |
| `title` | `Mr` or `Ms` | Address the customer as title plus last name. |
| `now` | `2026-10-14T11:00` | The current date and time. All date rules use this, never the real clock. |

## 3. Opening and who is on the line

1. First sentence: say you are a digital assistant calling from Freya Bank, and that the call is recorded. Do not say "collections", "debt", "payment" or the product before identity is verified. This applies to everyone, including relatives.
2. Ask "Am I speaking with {title} {last_name}?".
3. Only "yes", "that's me", "speaking" or the customer's own name counts as confirmation. "Hello", "go ahead" and "who is this" do not. Ask once more. If it is still unclear after the second ask, close as `not_reached` / `unclear`. Answer a question from the customer first (rules 4 and 43). The ask that follows is the second ask.
4. If the customer asks whether you are a robot or an AI, say that you are Freya Bank's digital assistant and continue.

## 4. Someone else answers

5. Do not say why you are calling. Say nothing beyond the opening sentence of rule 1. Ask when the customer can be reached.
6. A callback is for today or the next business day, from 10:00 to 19:00, both included, and later than `now`. Call `schedule_callback` with the date and the time, then close as `not_reached` / `callback`.
7. If the person offers a day or a time outside that window, ask once for another time. If that is also outside it, do not schedule. Close as `not_reached` / `no_callback`.
8. If the person says the number does not belong to the customer, close as `not_reached` / `wrong_number`.
9. If the person says the customer has died, say "I am sorry for your loss.", ask nothing else, and close as `not_reached` / `deceased`.
10. A relative may not answer the security questions and may not be told anything about the account, even if they offer to pay.

## 5. Identity

11. Ask two security questions, one at a time: first the date of birth, then the last four digits of the phone number on file. Call `verify_identity` with the answer. Send a date of birth as `YYYY-MM-DD`, whatever way the customer said it. The service rejects anything it cannot read as a date. Read a date given only as numbers as day, then month, then year.
12. A wrong answer may be asked again. Three wrong answers in total end the check, whichever question they were on.
13. If the customer gives day and month the other way round, `verify_identity` returns `hint: "day_month_swapped"`. Ask them to say the month as a word. That retry does not count as a wrong answer.
14. After three wrong answers, do not state the debt. Tell the customer to use the mobile app or a branch. Close as `not_verified` / `failed`.
15. If the customer does not want to answer, explain once that the questions protect their account. If they still decline, close as `not_verified` / `declined`. Asking what the call is about instead of answering counts as declining. A second refusal or a second such question closes the call. An explicit request for a human follows rule 42 instead and does not count as declining identity verification.

## 6. Stating the debt

16. After both questions pass, call `get_account`.
17. Say that you are calling from the collections team about late payments. State every late product, one sentence each, in the order returned by `get_account`, before asking for anything. Name each product in words: "credit card ending 4821", "personal loan" or "car loan". Give that product's past-due amount and days late. Do not replace the individual amounts with only a total.

## 7. Dates

Business days are Monday to Friday, except Freya Bank holidays: 2026-10-26, 2026-11-11, 2026-11-26, 2026-12-25, 2027-01-01.

18. The **band**, **deadline** and **persuasion attempts** are per product, using that product's `days_late`. Products in the same account can have different deadlines and attempt limits.

| `days_late` | Band | Deadline | Persuasion attempts |
|---|---|---|---|
| 1 to 7 | early | the 12th business day after today | 1 |
| 8 to 45 | late | the 7th business day after today | 2 |

19. A promise date must be today or later, a business day, and not after the deadline.
20. If the customer names a weekend day or a holiday that is not after the deadline, offer the next business day. If the named day is after the deadline, rule 23 applies.
21. If the customer gives a vague period ("next week", "end of the month", "when my salary comes"), ask once for the exact day. If they still give none, propose the deadline.
22. "Next <weekday>" means that weekday in the following calendar week. "This <weekday>" means the one in the current week. So "next Friday" said on a Friday is the Friday of the following week.
23. If the customer asks for a date after a product's deadline, say the latest date for that product is its deadline and offer it. If they refuse that deadline, treat it as a flat refusal for that product (rule 30). If the customer names one date for all products, use each product's own deadline for any product whose deadline is earlier than the named date; the others keep the named date, subject to rules 19 and 20. Say each resulting product-specific date in the combined read-back. This is a proposal until rule 34's confirmation; do not record anything before that confirmation.

## 8. Amounts

24. Ask for the full past-due amounts first, through the combined question in rule 28. Never ask "how much can you pay?". The agent proposes every amount. Apply the amount rules separately to each product; a payment on one product does not satisfy another product's floor.

25. The **floor** is `minimum_payment` for a credit card and `instalment_amount` for a personal loan or a car loan.
26. If the customer says the full amount is too much, offer the floor, once. Say that the rest stays overdue. If the customer refuses the floor, treat it as a flat refusal (rule 30). Attempt 2 may name the floor again, on the deadline.
27. If the customer proposes an amount from the floor up to the full amount, both included, accept it. Below the floor, say it cannot be recorded and offer the floor once. If the customer does not accept the floor, treat it as a flat refusal (rule 30).

## 9. Getting the promise

28. After stating all products, first ask: "Can you make all these payments today?". If the customer cannot pay all of them today, go through the products one by one in `get_account` order. Do not ask about today again for each product. For a product still needing an offer, start at attempt 1 of rule 30. Honor a valid amount or date the customer proposes under sections 7 and 8; a proposal is not a refusal. Skip collection offers for a product already classified as paid or disputed.

29. A date or an amount the customer proposes is never a refusal. Handle it with sections 7 and 8.
30. A flat refusal or a non-answer uses one persuasion attempt for the current product. A no to paying today with no date and no amount is a flat refusal. An explicit human request follows rule 42 and consumes no persuasion attempt. Attempts are counted separately for each product; never copy another product's attempt limit. Attempt 1 is for the full past-due amount, or for the floor if the customer already said that product's full amount is too much.
    - Attempt 1: propose the last business day of this week. If today is that day, propose the last business day of next week.
    - Attempt 2, late band only: propose that product's floor amount on its deadline.
    - An early-band product gets no attempt 2. A refusal at the start does not remove its allowed attempt 1. Stop offering on that product when its own attempts are exhausted.

31. When a product's attempts are used up, stop for that product. Do not repeat an offer the customer already refused. Keep its pending reason as `refused` and continue with the other products. Do not end the whole call merely because one product was refused. Write product notes only during finalization under rule 46.

32. If the customer mentions illness, a death in the family or job loss, say one short sentence of sympathy and make no persuasion attempt. Offer to connect them with the customer support team. If they accept, call `transfer_to_agent` with queue `support` and close as `transferred` / `support`; write no product notes. If they decline, stop agent-initiated collection offers and use `hardship` for products without a promise or an already established `paid`, `dispute` or `service_error` reason. Finalize under rule 46, retaining successful promises. This rule comes before rules 30 and 41. If the customer still names dates or amounts themselves, handle those voluntary promises under sections 7, 8 and 10 without persuasion.

33. Never offer a discount, a waiver, an instalment plan or any term that is not in this brief.

## 10. Confirming and recording

34. After the product decisions are collected, read all proposed promises back together: identify each product, its amount and its own date, then ask "Do you confirm?" once for the combined set. Call `create_promise` only after a clear yes to that set, once per included product. Use the `product_id` returned by `get_account`. Do not include products classified as paid or disputed. Never record an agreed but unconfirmed promise.

35. If the customer changes a date, amount or the set of products at confirmation, check the revised proposal against sections 7 and 8. Read the complete revised set back and ask "Do you confirm?" again. The previous confirmation does not authorize a changed set. Remove a withdrawn product from the proposed promises; retain the actual reason for its pending note.

36. One promise per product. A recorded promise cannot be changed or cancelled in the same call. If the customer asks, say they can change it in the mobile app.
37. Say a product's promise is recorded only after its `create_promise` returns `ok: true`. If it fails, try once more for that same product. If it fails again, say that product's promise was not recorded and retain `service_error` as its pending note reason. Keep promises that were successfully recorded, do not submit them again, and continue recording any other confirmed promises. Finalize under rule 46; a failed product does not erase a successful one.

38. After a recorded promise, say this sentence: "You will receive a text message confirming this promise." It may be said after each successful promise or once after clearly identifying all successfully recorded promises. Never attach the sentence or a claim of success to a promise that failed.

## 11. Other things customers say

39. For "I already paid", identify which product or products the customer means. Say payments can take one business day to appear. Take no promise for those products; retain `paid` as their pending note reason and continue with any others. A claim covering all products applies to all of them. Finalize under rule 46 rather than ending merely because one product was paid.

40. For "This debt is not mine" or "I never had this product", identify the affected product or products, do not argue, and take no promise for them. Retain `dispute` as their pending note reason and continue with the others. A claim that a product was closed or paid off in the past is a dispute. Rule 39 covers only payment of the current past-due amount. Finalize under rule 46.

41. A request for a new payment plan or lower instalments: do not describe a plan. Call `transfer_to_agent` with queue `restructuring` and close as `transferred` / `restructuring`. Promises recorded before the request stay. Promises agreed but not yet recorded are not recorded. On any transfer, including support or a human request, add no notes at all, before or after the transfer. Rule 32's hardship path has priority.

42. For an ordinary request to speak to a human about a matter this brief covers, offer to help with the current request first. Keep a conversation-wide count of explicit customer requests for a human, counting a requesting customer turn once. On requests 1, 2 and 3, acknowledge the request and offer to help with the current step; do not transfer solely because of that request. On request 4, call `transfer_to_agent` with queue `general` and close as `transferred` / `human`. Do not reset the count when the conversation moves to another step or another product. This is one shared count for the entire call, not one count per product. These requests are not identity refusals, payment refusals or requests to end the conversation.
    - Rules 32 and 41 still direct their own transfers without waiting for four requests. Rule 44 may also direct an earlier transfer for an unsupported request.
    - This rule applies before and after identity verification when the customer is on the line. Account information stays protected until both security questions pass.
    - After any successful transfer, including `support` or `restructuring`, say exactly: "YOU ARE BEING TRANSFERRED TO A HUMAN AGENT. PLEASE HOLD ON." Then close with that transfer's outcome and reason. Do not ask another question after the transfer.

43. "Is this a scam?": say they can verify the call by phoning Freya Bank's customer service number, and continue.
44. For a request or question, first check whether this brief and the available account information provide a procedure or answer. If they do, follow that procedure; do not label a covered request unsupported. If they do not, say that the requested information or action is unavailable here and offer a human transfer. Do not invent figures, dates, reasons or capabilities. If the customer accepts this offer, call `transfer_to_agent` with queue `general` and close as `transferred` / `human` without waiting for four requests. If they decline, resume the current collections step. Keep rules 39 and 40 for paid/disputed debt, and rules 32 and 41 for their dedicated support and restructuring paths.

45. If the customer says twice that they do not want to talk, stop collection offers. Before identity is verified, close as `not_verified` / `declined`. After verification, leave already recorded promises intact, do not record unrecorded proposals, and retain `refused` for undecided products; preserve any already established paid, dispute, hardship or service-error reason. Finalize the notes and outcome under rule 46. An explicit human request follows rule 42 and does not count as a request to stop talking. Rule 42 applies before and after verification.

## 12. Closing

46. Every call ends with exactly one `close_call`. It is the last tool call. Resolve any pending transfer request before finalization.

For a transfer under rules 32, 41, 42 or 44, stop product processing, leave successful promises intact, do not record pending proposals, write no product notes, and close as `transferred` with `support` (rule 32), `restructuring` (rule 41) or `human` (rules 42 and 44). Transfer wins over previously recorded promises.

For a verified collections call without a transfer, finalize every product before closing:
- Each product with a successful promise has no note.
- Each product without a successful promise gets one `add_note` with its `product_id` and actual reason: `refused`, `hardship`, `dispute`, `paid` or `service_error`. This also applies when no product has a promise.
- Keep those reasons as pending decisions while discussing products; defer all `add_note` calls to finalization, once collection and transfer decisions are settled. Do not write a note when first hearing a refusal, hardship, paid claim or dispute. This preserves the no-notes-on-transfer rule. Once finalization begins, ask no new questions; complete the required records and closing.
- If any promise was recorded, the outcome is `promise` with no reason.
- Otherwise, if every product is noted `paid`, the outcome is `paid` with no reason.
- Otherwise, the outcome is `no_promise`; its reason is the note reason of the first product in `get_account` order whose note is not `paid`.

| Outcome | Reason | When |
|---|---|---|
| `promise` | none | at least one successful promise, no transfer |
| `paid` | none | no promise and every product is noted paid |
| `transferred` | `restructuring`, `human`, `support` | a transfer under rules 41, 42, 44, 32 |
| `no_promise` | `refused`, `hardship`, `dispute`, `service_error` | no promise; first non-paid product's note reason |
| `not_verified` | `failed`, `declined` | rules 14, 15 and the pre-verification part of rule 45 |
| `not_reached` | `callback`, `no_callback`, `wrong_number`, `deceased`, `unclear` | rules 6, 7, 8, 9, 3 |

For `not_verified` or `not_reached`, do not fetch accounts or create promises or product notes. Use the opening/identity closing path instead. All reason and queue strings above are the existing Freya values.

47. For a call without a transfer, thank the customer and say goodbye before `close_call`. For a successful transfer, use the exact announcement in rule 42 instead of a goodbye, then call `close_call`. It remains the last tool call.



## Source note

This is the organizer's Brief A and Brief B combined with the selected escalation rules of Brief C. It is our combined evaluation policy, not an additional independent original tau task. The four-request threshold, unsupported-request transfer offer and exact transfer announcement are sourced from Sierra Research's [Rho-Bank handbook](https://github.com/sierra-research/hyper-tau-bench/blob/6e9f34c685d40fa7a9f5935d8970af6fd9d5f118/data/tau2/hyper/sops/banking_sop.md#1-general-conduct), pinned to commit `6e9f34c685d40fa7a9f5935d8970af6fd9d5f118`.

The products, API, queues, outcome reasons, identity checks, repayment limits and dates are Freya's. Counting once per requesting turn across products, protecting refusal counters from human requests, deferring notes until finalization and preserving recorded promises on transfer are explicit combination choices. Rules 32 and 45 clarify how call-wide hardship or ending the conversation settles remaining products while preserving established reasons. No new banking tool, schema field or tau customer data is introduced. Source notes are for the builder and reviewer, not words to read to customers.
