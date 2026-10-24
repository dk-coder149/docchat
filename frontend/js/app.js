// UI ka code: login/signup, documents ki list + upload, aur chat.
// Safety: user ka text hamesha textContent se dikhate hain (innerHTML se nahi), taaki XSS na ho.
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const MAX_UPLOAD_MB = 10; // backend ki default limit jaisi; asli check server karta hai

  let authMode = "login";
  let docs = [];
  let pollTimer = null;
  let busy = false;

  // ------------------------------------------------------------------ helpers
  let toastTimer = null;
  function toast(message) {
    const t = $("toast");
    t.textContent = message;
    t.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove("show"), 3500);
  }

  function showView(name) {
    $("auth-view").hidden = name !== "auth";
    $("app-view").hidden = name !== "app";
  }

  // ------------------------------------------------------------------ auth
  function setAuthMode(mode) {
    authMode = mode;
    $("tab-login").classList.toggle("active", mode === "login");
    $("tab-signup").classList.toggle("active", mode === "signup");
    $("auth-submit").textContent = mode === "login" ? "Login" : "Create account";
    $("password").autocomplete = mode === "login" ? "current-password" : "new-password";
    $("auth-error").textContent = "";
  }

  async function onAuthSubmit(event) {
    event.preventDefault();
    const username = $("username").value.trim();
    const password = $("password").value;
    const button = $("auth-submit");
    button.disabled = true;
    $("auth-error").textContent = "";
    try {
      if (authMode === "signup") await Api.signup(username, password);
      await Api.login(username, password);
      $("password").value = "";
      await startApp();
    } catch (err) {
      $("auth-error").textContent = err.message;
    } finally {
      button.disabled = false;
    }
  }

  function logout() {
    Api.logout();
    stopPolling();
    docs = [];
    $("messages").replaceChildren($("empty-chat"));
    $("empty-chat").hidden = false;
    showView("auth");
  }

  // ------------------------------------------------------------------ documents
  function renderDocs() {
    const list = $("doc-list");
    list.replaceChildren();
    $("doc-empty").hidden = docs.length > 0;

    for (const d of docs) {
      const li = el("li", "doc");
      const name = el("div", "doc-name", d.filename);
      name.title = d.filename;

      const meta = el("div", "doc-meta");
      const status = el("span", "st-" + d.status, d.status);
      meta.append(status);
      if (d.status === "ready") meta.append(" · " + d.chunk_count + " chunks");
      if (d.status === "failed" && d.error) meta.append(" · " + d.error);

      const del = el("button", "btn ghost small del", "Delete");
      del.type = "button";
      del.addEventListener("click", () => deleteDoc(d));

      li.append(name, meta, del);
      list.append(li);
    }

    // "Ask in" dropdown mein sirf ready documents
    const select = $("doc-filter");
    const previous = select.value;
    select.replaceChildren(new Option("All documents", ""));
    for (const d of docs.filter((x) => x.status === "ready")) {
      select.append(new Option(d.filename, String(d.id)));
    }
    if ([...select.options].some((o) => o.value === previous)) select.value = previous;
  }

  async function loadDocs() {
    try {
      docs = await Api.listDocuments();
      renderDocs();
    } catch (err) {
      toast(err.message);
    }
    schedulePoll();
  }

  // Jab tak koi document "processing" hai, har 2 second mein status dobara lo
  function schedulePoll() {
    stopPolling();
    if (docs.some((d) => d.status === "processing")) {
      pollTimer = setTimeout(loadDocs, 2000);
    }
  }
  function stopPolling() {
    clearTimeout(pollTimer);
    pollTimer = null;
  }

  async function uploadFile(file) {
    if (!file) return;
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      toast("File is larger than " + MAX_UPLOAD_MB + " MB");
      return;
    }
    try {
      await Api.uploadDocument(file);
      toast("Uploaded. Processing…");
    } catch (err) {
      toast(err.message);
    }
    await loadDocs();
  }

  async function deleteDoc(d) {
    if (!confirm('Delete "' + d.filename + '"?')) return;
    try {
      await Api.deleteDocument(d.id);
    } catch (err) {
      toast(err.message);
    }
    await loadDocs();
  }

  // ------------------------------------------------------------------ chat
  function scrollToBottom(force) {
    const box = $("messages");
    const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 120;
    if (force || nearBottom) box.scrollTop = box.scrollHeight;
  }

  // Assistant ka jawab Markdown hota hai (headings, bullets, tables...), user ka plain text.
  // Markdown.render kabhi innerHTML use nahi karta, isliye safe hai.
  function setBubbleContent(bubble, role, text) {
    if (role === "assistant") {
      bubble.classList.add("md");
      bubble.replaceChildren(Markdown.render(text));
    } else {
      bubble.textContent = text;
    }
  }

  function addMessage(role, text, sources) {
    $("empty-chat").hidden = true;
    const wrap = el("div", "msg " + role);
    const bubble = el("div", "bubble");
    setBubbleContent(bubble, role, text);
    wrap.append(bubble);
    if (sources && sources.length) wrap.append(sourcesRow(sources));
    $("messages").append(wrap);
    scrollToBottom(true);
    return { wrap, bubble };
  }

  function sourcesRow(sources) {
    const row = el("div", "sources", "Sources:");
    for (const s of sources) row.append(el("span", "chip", s.filename));
    return row;
  }

  async function loadHistory() {
    try {
      const messages = await Api.history();
      for (const m of messages) addMessage(m.role, m.content, m.sources);
    } catch (err) {
      toast(err.message);
    }
  }

  async function onChatSubmit(event) {
    event.preventDefault();
    if (busy) return;
    const input = $("question");
    const question = input.value.trim();
    if (!question) return;

    busy = true;
    $("send").disabled = true;
    input.value = "";
    autoGrow();

    addMessage("user", question);
    const reply = addMessage("assistant", "Thinking…");
    reply.bubble.classList.add("pending");

    const docValue = $("doc-filter").value;
    const documentId = docValue ? Number(docValue) : null;
    let sources = [];
    let gotToken = false;
    let failed = false;
    let answer = "";   // ab tak ka poora jawab (Markdown text)
    let frame = null;  // har token par nahi, har screen-frame par ek baar dobara draw karte hain

    const paint = () => {
      reply.bubble.replaceChildren(Markdown.render(answer));
      scrollToBottom(false);
    };
    const schedulePaint = () => {
      if (frame === null) frame = requestAnimationFrame(() => { frame = null; paint(); });
    };
    const flushPaint = () => {
      if (frame !== null) { cancelAnimationFrame(frame); frame = null; }
      if (gotToken) paint();
    };

    try {
      await Api.streamChat(question, documentId, (ev) => {
        if (ev.type === "sources") {
          sources = ev.sources || [];
        } else if (ev.type === "token") {
          if (!gotToken) {
            reply.bubble.classList.remove("pending");
            gotToken = true;
          }
          answer += ev.text;
          schedulePaint();
        } else if (ev.type === "error") {
          failed = true;
          flushPaint();
          showReplyError(reply, ev.message, gotToken);
        }
      });
    } catch (err) {
      failed = true;
      flushPaint();
      showReplyError(reply, err.message, gotToken);
    } finally {
      if (!failed) flushPaint();
      if (!failed && sources.length) reply.wrap.append(sourcesRow(sources));
      busy = false;
      $("send").disabled = false;
      input.focus();
      scrollToBottom(true);
    }
  }

  function showReplyError(reply, message, keepText) {
    reply.bubble.classList.remove("pending");
    reply.bubble.classList.add("failed");
    if (keepText) {
      reply.bubble.append(el("div", "note", "[" + message + "]"));  // adhura jawab rehne do, neeche error
    } else {
      reply.bubble.classList.remove("md");
      reply.bubble.textContent = message;
    }
  }

  async function clearChat() {
    if (!confirm("Clear the whole chat history?")) return;
    try {
      await Api.clearHistory();
      $("messages").replaceChildren($("empty-chat"));
      $("empty-chat").hidden = false;
    } catch (err) {
      toast(err.message);
    }
  }

  function autoGrow() {
    const t = $("question");
    t.style.height = "auto";
    t.style.height = Math.min(t.scrollHeight, 160) + "px";
  }

  // ------------------------------------------------------------------ start
  async function startApp() {
    const me = await Api.me();
    $("who").textContent = "Signed in as " + me.username;
    showView("app");
    $("messages").replaceChildren($("empty-chat"));
    $("empty-chat").hidden = false;
    await loadDocs();
    await loadHistory();
  }

  function wireEvents() {
    $("tab-login").addEventListener("click", () => setAuthMode("login"));
    $("tab-signup").addEventListener("click", () => setAuthMode("signup"));
    $("auth-form").addEventListener("submit", onAuthSubmit);
    $("logout").addEventListener("click", logout);

    $("file-input").addEventListener("change", (e) => {
      uploadFile(e.target.files[0]);
      e.target.value = "";
    });
    const zone = $("dropzone");
    zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("drag"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("drag"));
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.classList.remove("drag");
      uploadFile(e.dataTransfer.files[0]);
    });

    $("chat-form").addEventListener("submit", onChatSubmit);
    $("clear-chat").addEventListener("click", clearChat);
    const q = $("question");
    q.addEventListener("input", autoGrow);
    q.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        $("chat-form").requestSubmit();
      }
    });
  }

  async function boot() {
    wireEvents();
    Api.onUnauthorized = () => {
      toast("Session expired, please log in again");
      logout();
    };
    if (Api.hasToken()) {
      try {
        await startApp();
        return;
      } catch (_) {
        Api.logout();
      }
    }
    showView("auth");
  }

  boot();
})();
