// The team's mock of the bank's services, written from the case's service contract and test customers.
// Every service is a POST with a JSON body and answers JSON. State per call (identity tries, records) is
// kept in memory per customer: enough for one simulated call, which stays on one isolate.

const CUSTOMERS = {
  // FILL from the case's test customers: "<customer_id>": { ...fields the contract returns... }
};

const state = new Map();   // customer_id -> { tries, records... }

function json(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function customerState(id) {
  if (!state.has(id)) state.set(id, { tries: 0, records: [] });
  return state.get(id);
}

const SERVICES = {
  // FILL: "/<path>": (body, customer, st) => ({ ...the contract's response... }),
};

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/") return json({ ok: true, services: Object.keys(SERVICES) });
    const handler = SERVICES[url.pathname];
    if (!handler) return json({ ok: false, error: "unknown service " + url.pathname }, 404);
    let body = {};
    try { body = await request.json(); } catch { return json({ ok: false, error: "body is not JSON" }, 400); }
    const id = body.customer_id;
    const customer = id === undefined ? null : CUSTOMERS[id];
    try {
      return json(handler(body, customer, customerState(String(id))));
    } catch (error) {
      return json({ ok: false, error: String(error) }, 500);
    }
  },
};
