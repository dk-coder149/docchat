// Run: node --test      (Node 18+, koi install nahi chahiye)
const test = require("node:test");
const assert = require("node:assert/strict");

// ---- browser ke nakli localStorage aur fetch ----
const store = new Map();
Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
  },
});

let lastRequest = null;
function mockFetch(status, payload, { stream = false } = {}) {
  globalThis.fetch = async (url, init) => {
    lastRequest = { url, init };
    const bodyStream = stream ? payload : null;
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => payload,
      body: bodyStream,
    };
  };
}

const Api = require("../js/api.js");

function streamOf(text, chunkSize) {
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream({
    start(controller) {
      for (let i = 0; i < bytes.length; i += chunkSize) {
        controller.enqueue(bytes.slice(i, i + chunkSize));
      }
      controller.close();
    },
  });
}

test("readNdjson: lines chhote chunks aur hindi characters ke beech se bhi sahi judti hain", async () => {
  const lines = [
    { type: "sources", sources: [{ document_id: 1, filename: "notes.pdf" }] },
    { type: "token", text: "नमस्ते " },
    { type: "token", text: "Dileep" },
    { type: "done" },
  ];
  const text = lines.map((l) => JSON.stringify(l)).join("\n") + "\n";
  for (const size of [1, 3, 7, 1000]) {
    const events = [];
    await Api._readNdjson(streamOf(text, size), (e) => events.push(e));
    assert.deepEqual(events, lines, "chunk size " + size);
  }
});

test("readNdjson: aakhri line bina newline ke ho tab bhi padhi jati hai", async () => {
  const events = [];
  await Api._readNdjson(streamOf('{"type":"done"}', 4), (e) => events.push(e));
  assert.deepEqual(events, [{ type: "done" }]);
});

test("login: form data bhejta hai aur token save karta hai", async () => {
  mockFetch(200, { access_token: "abc123", token_type: "bearer" });
  await Api.login("dileep", "secret-pass");
  assert.ok(lastRequest.url.endsWith("/api/auth/login"));
  assert.ok(lastRequest.init.body instanceof URLSearchParams);
  assert.equal(lastRequest.init.body.get("username"), "dileep");
  assert.equal(Api.hasToken(), true);
  assert.equal(lastRequest.init.headers["Content-Type"], undefined); // browser khud form type lagata hai
});

test("authenticated request mein Bearer token jata hai", async () => {
  mockFetch(200, []);
  await Api.listDocuments();
  assert.equal(lastRequest.init.headers.Authorization, "Bearer abc123");
});

test("JSON body Content-Type ke saath jati hai", async () => {
  mockFetch(201, { id: 1, username: "dileep" });
  await Api.signup("dileep", "secret-pass");
  assert.equal(lastRequest.init.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(lastRequest.init.body), { username: "dileep", password: "secret-pass" });
});

test("server ka error message ApiError mein aata hai", async () => {
  mockFetch(400, { detail: "Pehle koi document upload karo" });
  await assert.rejects(Api.history(), (err) => {
    assert.equal(err.name, "ApiError");
    assert.equal(err.status, 400);
    assert.equal(err.message, "Pehle koi document upload karo");
    return true;
  });
});

test("422 validation list ek message ban jati hai", async () => {
  mockFetch(422, { detail: [{ msg: "too short" }, { msg: "bad pattern" }] });
  await assert.rejects(Api.signup("a", "b"), /too short; bad pattern/);
});

test("network band ho to saaf message milta hai", async () => {
  globalThis.fetch = async () => { throw new TypeError("failed to fetch"); };
  await assert.rejects(Api.history(), /Cannot reach the server/);
});

test("401 par token hat jata hai aur onUnauthorized chalta hai", async () => {
  let called = false;
  Api.onUnauthorized = () => { called = true; };
  mockFetch(401, { detail: "Token galat" });
  await assert.rejects(Api.me());
  assert.equal(called, true);
  assert.equal(Api.hasToken(), false);
});

test("streamChat: events callback ko milte hain", async () => {
  store.set("docchat_token", "abc123");
  const body = streamOf(
    ['{"type":"sources","sources":[]}', '{"type":"token","text":"Hi"}', '{"type":"done"}'].join("\n") + "\n",
    5
  );
  mockFetch(200, body, { stream: true });
  const events = [];
  await Api.streamChat("hello?", null, (e) => events.push(e.type));
  assert.deepEqual(events, ["sources", "token", "done"]);
  assert.deepEqual(JSON.parse(lastRequest.init.body), { question: "hello?", document_id: null });
});
