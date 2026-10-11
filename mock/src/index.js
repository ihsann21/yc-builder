// The team's mock of Freya Bank's statement/debt services (case service contract 2026-10-01).
// Answers come unchanged from data/test-customers.json (status `http`, body `response`, optional `delaySeconds`).
// Lookup rules: test-environment/test-customers.md. Only `data` fields decide the answer.

import DATA from "../data/test-customers.json";

const BY_NO = new Map(DATA.customers.map((c) => [c.customerNo, c]));
const BY_CARD = {}; // service -> masked card number -> entry (card keys are unique across customers)
for (const c of DATA.customers) {
  for (const [svc, entry] of Object.entries(c.services)) {
    if (entry.http !== undefined) continue; // per-customer service, not keyed by card
    BY_CARD[svc] ??= {};
    for (const [card, v] of Object.entries(entry)) BY_CARD[svc][card] ??= v;
  }
}

// Panel "Test API Request" sends unfilled variables: answer with the first test customer's record.
const DEFAULT = { customerNo: "90000001", cardNumber: "540000******1234", newStatementWeek: "2" };

const CORS = { "Access-Control-Allow-Origin": "*" };

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...CORS, "Content-Type": "application/json; charset=utf-8" },
  });
}

function isTemplateVariable(value) {
  return typeof value === "string" && (value.startsWith("{{") || value.startsWith("%7B%7B"));
}

function text(value) {
  return value === undefined || value === null ? "" : String(value).trim();
}

// Contract section 4 error envelope: result only, no data.
function error(status, code, message, type, rootCause) {
  const guid = crypto.randomUUID().replace(/-/g, "");
  return json({
    result: {
      guid, returnCode: code, messageText: message, code, message, type,
      details: { guid, rootCause, errorOrigin: "ivr-gateway-test:ivr-channel-v0" },
    },
  }, status);
}

const invalid = (message) => error(400, "INVALID_ARGUMENTS_ERROR", message, "ERROR", "InvalidArgumentsException");
const notFound = (code, message) => error(404, code, message, "WARNING",
  "com.freyabank.ivrgateway.ivrchannel.rest.exception.NotFoundException");

// Per service: required fields, how to find the entry, and the answer when there is none.
const BY_CUSTOMER = (svc) => (d) => BY_NO.get(d.customerNo)?.services[svc];
const BY_CARD_NO = (svc) => (d) => BY_CARD[svc]?.[d.cardNumber];
const BY_WEEK = (svc) => (d) => BY_CARD_NO(svc)(d)?.[d.newStatementWeek];

const SERVICES = {
  "cards.list": { required: ["customerNo"], find: BY_CUSTOMER("cards.list"),
    missing: () => notFound("FB_IVR_CHANNEL_102", "Müşteriye ait geçerli kart bilgisi bulunamadı.") },
  "cards.balance": { required: ["cardNumber"], find: BY_CARD_NO("cards.balance"),
    missing: () => notFound("FB_IVR_CHANNEL_120", "Kart bakiye servisi hatası: kart bulunamadı") },
  "statement.week.get": { required: ["cardNumber"], find: BY_CARD_NO("statement.week.get"),
    missing: () => notFound("FB_IVR_CHANNEL_121", "Ekstre hafta servisi hatası: kart bulunamadı") },
  "statement.week.decide": { required: ["cardNumber", "newStatementWeek"], find: BY_WEEK("statement.week.decide"),
    missing: () => invalid("no statement week preview for this card and newStatementWeek") },
  "statement.week.change": { required: ["cardNumber", "newStatementWeek"], find: BY_WEEK("statement.week.change"),
    missing: () => invalid("no statement week change for this card and newStatementWeek") },
  "contact.email.get": { required: ["customerNo"], find: BY_CUSTOMER("contact.email.get"),
    missing: () => invalid("customer not found") },
  "statement.pdf.send": { required: ["customerNo"], find: BY_CUSTOMER("statement.pdf.send"),
    missing: () => notFound("FB_IVR_CHANNEL_107", "Pdf dokümanı bulunamadı") },
};

const FIELD_NAMES = { customerNo: "customer number", cardNumber: "card number", newStatementWeek: "newStatementWeek" };

async function serve(service, request) {
  let body;
  try { body = await request.json(); } catch { return invalid("request body is not valid JSON"); }
  // The contract's envelope is {"data": {...}, "call": {...}}; a flat body is read as the data too.
  const raw = body && typeof body.data === "object" && body.data !== null ? body.data
    : body && typeof body === "object" ? body : {};
  // contact.email.get: an empty intAddressInfoType is a 400; an absent one is accepted.
  if (service.name === "contact.email.get" && "intAddressInfoType" in raw && text(raw.intAddressInfoType) === "") {
    return invalid("intAddressInfoType cannot be empty");
  }
  const d = {};
  for (const field of service.required) {
    d[field] = text(raw[field]);
    if (d[field] === "") return invalid(`${FIELD_NAMES[field]} cannot be empty`);
  }
  if (service.required.some((f) => isTemplateVariable(d[f]))) Object.assign(d, DEFAULT);
  const entry = service.find(d);
  if (!entry || entry.http === undefined) return service.missing();
  if (entry.delaySeconds) await new Promise((resolve) => setTimeout(resolve, entry.delaySeconds * 1000));
  return json(entry.response, entry.http);
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: {
        ...CORS,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
      } });
    }
    if (request.method === "GET" && url.pathname === "/health") return json({ status: "ok" });
    const name = url.pathname.startsWith("/voice/v1/") ? url.pathname.slice("/voice/v1/".length) : null;
    if (request.method === "POST" && name && SERVICES[name]) return serve({ name, ...SERVICES[name] }, request);
    return json({ error: "not found", paths: ["GET /health", ...Object.keys(SERVICES).map((s) => "POST /voice/v1/" + s)] }, 404);
  },
};
