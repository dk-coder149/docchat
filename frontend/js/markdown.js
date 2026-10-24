// Chhota, safe Markdown renderer (koi library nahi, innerHTML kabhi nahi).
//
// Do hisse:
//   parse(text)        -> blocks ki list (sirf data; DOM nahi chahiye, isliye Node mein test hota hai)
//   render(text, doc)  -> DocumentFragment (sirf createElement / createTextNode se bana)
//
// Safety: model ka text kabhi HTML ki tarah nahi padha jata. "<script>" jaisi cheez
// sirf text node banti hai. Links sirf http/https ke chalte hain.
//
// Support: # headings, **bold**, *italic*, `code`, ``` code blocks ```, - / 1. lists
// (nested bhi), | tables |, --- line, [text](https://link), aur <br>.
(function (root) {
  "use strict";

  const RE = {
    fence: /^\s*```/,
    heading: /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/,
    hr: /^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/,
    listItem: /^(\s*)([-*+]|\d+[.)])\s+(.*)$/,
    tableSep: /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/,
  };

  // <br> | `code` | **bold** | __bold__ | [text](https://url) | *italic*
  const INLINE_SOURCE =
    "(<br\\s*\\/?>)|(`[^`\\n]+`)|(\\*\\*[^\\n]+?\\*\\*)|(__[^\\n]+?__)|" +
    "(\\[[^\\]\\n]+\\]\\(https?:\\/\\/[^\\s)]+\\))|(\\*[^\\s*](?:[^*\\n]*[^\\s*])?\\*)";

  // ------------------------------------------------------------------ inline
  function parseInline(text, depth) {
    depth = depth || 0;
    const out = [];
    const pushText = (s) => {
      if (!s) return;
      s.split("\n").forEach((part, idx) => {
        if (idx) out.push({ t: "br" });
        if (part) out.push({ t: "text", v: part });
      });
    };

    const re = new RegExp(INLINE_SOURCE, "gi");
    let last = 0;
    let m;
    while ((m = re.exec(text)) !== null) {
      pushText(text.slice(last, m.index));
      const raw = m[0];
      if (m[1]) {
        out.push({ t: "br" });
      } else if (m[2]) {
        out.push({ t: "code", v: raw.slice(1, -1) });
      } else if (m[3] || m[4]) {
        const inner = raw.slice(2, -2);
        out.push({ t: "strong", c: depth < 4 ? parseInline(inner, depth + 1) : [{ t: "text", v: inner }] });
      } else if (m[5]) {
        const lm = /^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/i.exec(raw);
        out.push({ t: "link", href: lm[2], c: parseInline(lm[1], depth + 1) });
      } else if (m[6]) {
        out.push({ t: "em", c: depth < 4 ? parseInline(raw.slice(1, -1), depth + 1) : [{ t: "text", v: raw.slice(1, -1) }] });
      }
      last = re.lastIndex;
    }
    pushText(text.slice(last));
    return out;
  }

  // ------------------------------------------------------------------ blocks
  function splitRow(line) {
    let s = line.trim();
    if (s.startsWith("|")) s = s.slice(1);
    if (s.endsWith("|")) s = s.slice(0, -1);
    return s.split("|").map((cell) => cell.trim());
  }

  // Indent ke hisaab se nested list banata hai
  function buildList(items, pos, indent) {
    const list = { type: "list", ordered: items[pos].ordered, items: [] };
    while (pos < items.length) {
      const it = items[pos];
      if (it.indent < indent) break;
      if (it.indent > indent) {
        if (list.items.length === 0) {
          indent = it.indent; // list gehri indent se shuru hui
          continue;
        }
        const nested = buildList(items, pos, it.indent);
        list.items[list.items.length - 1].children.push(nested.list);
        pos = nested.pos;
        continue;
      }
      list.items.push({ inline: parseInline(it.text), children: [] });
      pos++;
    }
    return { list: list, pos: pos };
  }

  function parse(input) {
    const lines = String(input == null ? "" : input).replace(/\r\n?/g, "\n").split("\n");
    const blocks = [];
    let i = 0;

    const isTableStart = (idx) =>
      idx + 1 < lines.length && lines[idx].includes("|") && RE.tableSep.test(lines[idx + 1]);
    const isBlockStart = (idx) => {
      const l = lines[idx];
      return RE.fence.test(l) || RE.heading.test(l) || RE.hr.test(l) || RE.listItem.test(l) || isTableStart(idx);
    };

    while (i < lines.length) {
      const line = lines[i];
      if (!line.trim()) { i++; continue; }

      if (RE.fence.test(line)) {
        const code = [];
        i++;
        while (i < lines.length && !RE.fence.test(lines[i])) { code.push(lines[i]); i++; }
        i++; // band hone wali ``` (stream beech mein ho to bina band kiye bhi theek)
        blocks.push({ type: "code", text: code.join("\n") });
        continue;
      }

      const h = RE.heading.exec(line);
      if (h) {
        blocks.push({ type: "heading", level: h[1].length, inline: parseInline(h[2]) });
        i++;
        continue;
      }

      if (RE.hr.test(line)) { blocks.push({ type: "hr" }); i++; continue; }

      if (isTableStart(i)) {
        const header = splitRow(line).map((c) => parseInline(c));
        i += 2;
        const rows = [];
        while (i < lines.length && lines[i].trim() && lines[i].includes("|")) {
          rows.push(splitRow(lines[i]).map((c) => parseInline(c)));
          i++;
        }
        blocks.push({ type: "table", header: header, rows: rows });
        continue;
      }

      if (RE.listItem.test(line)) {
        const items = [];
        while (i < lines.length) {
          const lm = RE.listItem.exec(lines[i]);
          if (lm) {
            items.push({
              indent: lm[1].replace(/\t/g, "    ").length,
              ordered: /\d/.test(lm[2]),
              text: lm[3],
            });
            i++;
          } else if (!lines[i].trim() && i + 1 < lines.length && RE.listItem.test(lines[i + 1])) {
            i++; // items ke beech ek khali line
          } else if (items.length && /^\s{2,}\S/.test(lines[i]) && !isBlockStart(i)) {
            items[items.length - 1].text += " " + lines[i].trim(); // item ki agli line
            i++;
          } else {
            break;
          }
        }
        let pos = 0;
        while (pos < items.length) {
          const res = buildList(items, pos, items[pos].indent);
          blocks.push(res.list);
          pos = res.pos;
        }
        continue;
      }

      const para = [line.trim()];
      i++;
      while (i < lines.length && lines[i].trim() && !isBlockStart(i)) {
        para.push(lines[i].trim());
        i++;
      }
      blocks.push({ type: "paragraph", inline: parseInline(para.join("\n")) });
    }
    return blocks;
  }

  // ------------------------------------------------------------------ DOM
  function inlineToDom(nodes, doc) {
    const frag = doc.createDocumentFragment();
    for (const n of nodes) {
      if (n.t === "text") {
        frag.appendChild(doc.createTextNode(n.v));
      } else if (n.t === "br") {
        frag.appendChild(doc.createElement("br"));
      } else if (n.t === "code") {
        const el = doc.createElement("code");
        el.textContent = n.v;
        frag.appendChild(el);
      } else if (n.t === "strong" || n.t === "em") {
        const el = doc.createElement(n.t);
        el.appendChild(inlineToDom(n.c, doc));
        frag.appendChild(el);
      } else if (n.t === "link") {
        const el = doc.createElement("a");
        el.setAttribute("href", n.href);
        el.setAttribute("target", "_blank");
        el.setAttribute("rel", "noopener noreferrer");
        el.appendChild(inlineToDom(n.c, doc));
        frag.appendChild(el);
      }
    }
    return frag;
  }

  function listToDom(list, doc) {
    const el = doc.createElement(list.ordered ? "ol" : "ul");
    for (const item of list.items) {
      const li = doc.createElement("li");
      li.appendChild(inlineToDom(item.inline, doc));
      for (const child of item.children) li.appendChild(listToDom(child, doc));
      el.appendChild(li);
    }
    return el;
  }

  function blockToDom(block, doc) {
    if (block.type === "paragraph") {
      const p = doc.createElement("p");
      p.appendChild(inlineToDom(block.inline, doc));
      return p;
    }
    if (block.type === "heading") {
      const tag = block.level <= 2 ? "h3" : block.level === 3 ? "h4" : "h5";
      const h = doc.createElement(tag);
      h.appendChild(inlineToDom(block.inline, doc));
      return h;
    }
    if (block.type === "list") return listToDom(block, doc);
    if (block.type === "hr") return doc.createElement("hr");
    if (block.type === "code") {
      const pre = doc.createElement("pre");
      const code = doc.createElement("code");
      code.textContent = block.text;
      pre.appendChild(code);
      return pre;
    }
    // table (chhoti screen par side-scroll ke liye wrapper mein)
    const wrap = doc.createElement("div");
    wrap.setAttribute("class", "table-wrap");
    const table = doc.createElement("table");
    const thead = doc.createElement("thead");
    const headRow = doc.createElement("tr");
    for (const cell of block.header) {
      const th = doc.createElement("th");
      th.appendChild(inlineToDom(cell, doc));
      headRow.appendChild(th);
    }
    thead.appendChild(headRow);
    table.appendChild(thead);
    const tbody = doc.createElement("tbody");
    for (const row of block.rows) {
      const tr = doc.createElement("tr");
      for (const cell of row) {
        const td = doc.createElement("td");
        td.appendChild(inlineToDom(cell, doc));
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  }

  function render(text, doc) {
    doc = doc || root.document;
    const frag = doc.createDocumentFragment();
    for (const block of parse(text)) frag.appendChild(blockToDom(block, doc));
    return frag;
  }

  const Markdown = { parse: parse, parseInline: parseInline, render: render };
  root.Markdown = Markdown;
  if (typeof module !== "undefined" && module.exports) module.exports = Markdown;
})(typeof window !== "undefined" ? window : globalThis);
