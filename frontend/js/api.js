// Backend se baat karne ka saara code yahan hai (fetch calls). UI ka code app.js mein.
(function (root) {
  "use strict";

  const TOKEN_KEY = "docchat_token";
  const BASE = ((root.APP_CONFIG && root.APP_CONFIG.API_BASE_URL) || "http://localhost:8000")
    .replace(/\/+$/, "");

  // ---- token (localStorage; seekhne ke liye theek hai) ----
  function getToken() {
    try { return localStorage.getItem(TOKEN_KEY); } catch (_) { return null; }
  }
  function setToken(t) {
    try { localStorage.setItem(TOKEN_KEY, t); } catch (_) { /* ignore */ }
  }
  function clearToken() {
    try { localStorage.removeItem(TOKEN_KEY); } catch (_) { /* ignore */ }
  }

  class ApiError extends Error {
    constructor(status, message) {
      super(message);
      this.name = "ApiError";
      this.status = status;
    }
  }

  async function readError(res) {
    try {
      const data = await res.json();
      if (typeof data.detail === "string") return data.detail;
      if (Array.isArray(data.detail)) return data.detail.map((d) => d.msg).join("; ");
    } catch (_) { /* body JSON nahi tha */ }
    if (res.status === 429) return "Too many requests, please wait a bit.";
    return "Request failed (" + res.status + ")";
  }

  const Api = { onUnauthorized: null };

  async function send(path, options) {
    const opts = options || {};
    const headers = Object.assign({}, opts.headers);
    const token = getToken();
    if (token) headers.Authorization = "Bearer " + token;

    let body = opts.body;
    const isForm = body instanceof FormData || body instanceof URLSearchParams;
    if (body !== undefined && !isForm && typeof body !== "string") {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(body);
    }

    let res;
    try {
      res = await fetch(BASE + path, { method: opts.method || "GET", headers: headers, body: body });
    } catch (_) {
      throw new ApiError(0, "Cannot reach the server. Is the backend running?");
    }

    if (res.status === 401 && token && Api.onUnauthorized) {
      clearToken();
      Api.onUnauthorized();  // token expire ho gaya -> login screen
    }
    if (!res.ok) throw new ApiError(res.status, await readError(res));
    return res;
  }

  async function json(path, options) {
    const res = await send(path, options);
    return res.status === 204 ? null : res.json();
  }

  // ---- NDJSON stream padhna: har line ek JSON event hai ----
  async function readNdjson(stream, onEvent) {
    const reader = stream.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const chunk = await reader.read();
      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, idx).trim();
        buffer = buffer.slice(idx + 1);
        if (line) onEvent(JSON.parse(line));
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) onEvent(JSON.parse(buffer.trim()));
  }

  // ---- public functions ----
  Api.hasToken = function () { return !!getToken(); };
  Api.logout = clearToken;

  Api.signup = function (username, password) {
    return json("/api/auth/signup", { method: "POST", body: { username: username, password: password } });
  };

  Api.login = async function (username, password) {
    // Backend login ko FORM data chahiye (JSON nahi)
    const form = new URLSearchParams({ username: username, password: password });
    const data = await json("/api/auth/login", { method: "POST", body: form });
    setToken(data.access_token);
  };

  Api.me = function () { return json("/api/auth/me"); };
  Api.listDocuments = function () { return json("/api/documents"); };
  Api.deleteDocument = function (id) { return json("/api/documents/" + id, { method: "DELETE" }); };

  Api.uploadDocument = function (file) {
    const form = new FormData();
    form.append("file", file);
    return json("/api/documents", { method: "POST", body: form });
  };

  Api.history = function () { return json("/api/chat/history"); };
  Api.clearHistory = function () { return json("/api/chat/history", { method: "DELETE" }); };

  Api.streamChat = async function (question, documentId, onEvent) {
    const res = await send("/api/chat/stream", {
      method: "POST",
      body: { question: question, document_id: documentId },
    });
    await readNdjson(res.body, onEvent);
  };

  Api.ApiError = ApiError;
  Api._readNdjson = readNdjson;  // test ke liye

  root.Api = Api;
  if (typeof module !== "undefined" && module.exports) module.exports = Api;
})(typeof window !== "undefined" ? window : globalThis);
