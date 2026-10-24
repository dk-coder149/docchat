// Run: node --test      (koi install nahi chahiye)
const test = require("node:test");
const assert = require("node:assert/strict");
const Markdown = require("../js/markdown.js");

// ---- bahut chhota nakli DOM: sirf itna ki render() ka output HTML string mein badal sake ----
class FakeNode {
  constructor(tag) { this.tag = tag; this.children = []; this.attrs = {}; }
  appendChild(child) {
    if (child.tag === "#fragment") this.children.push(...child.children);
    else this.children.push(child);
    return child;
  }
  setAttribute(k, v) { this.attrs[k] = v; }
  set textContent(v) { this.children = [{ tag: "#text", text: String(v) }]; }
}
const fakeDoc = {
  createDocumentFragment: () => new FakeNode("#fragment"),
  createElement: (tag) => new FakeNode(tag),
  createTextNode: (text) => ({ tag: "#text", text }),
};
const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
function html(node) {
  if (node.tag === "#text") return esc(node.text);
  const inner = node.children.map(html).join("");
  if (node.tag === "#fragment") return inner;
  if (node.tag === "br" || node.tag === "hr") return `<${node.tag}>`;
  const attrs = Object.entries(node.attrs).map(([k, v]) => ` ${k}="${esc(v)}"`).join("");
  return `<${node.tag}${attrs}>${inner}</${node.tag}>`;
}
const md = (text) => html(Markdown.render(text, fakeDoc));

test("headings, paragraph, bold, italic, code", () => {
  assert.equal(
    md("## Key points\nThis is **important** and *nice* with `code`."),
    "<h3>Key points</h3><p>This is <strong>important</strong> and <em>nice</em> with <code>code</code>.</p>"
  );
  assert.equal(md("# A"), "<h3>A</h3>");
  assert.equal(md("### B"), "<h4>B</h4>");
  assert.equal(md("#### C"), "<h5>C</h5>");
});

test("bullet aur numbered lists", () => {
  assert.equal(md("- one\n- **two**\n- three"), "<ul><li>one</li><li><strong>two</strong></li><li>three</li></ul>");
  assert.equal(md("1. first\n2. second"), "<ol><li>first</li><li>second</li></ol>");
  assert.equal(md("* a\n* b"), "<ul><li>a</li><li>b</li></ul>");
});

test("nested list", () => {
  assert.equal(
    md("- a\n  - a1\n  - a2\n- b"),
    "<ul><li>a<ul><li>a1</li><li>a2</li></ul></li><li>b</li></ul>"
  );
});

test("list items ke beech khali line se list tutti nahi", () => {
  assert.equal(md("- a\n\n- b"), "<ul><li>a</li><li>b</li></ul>");
});

test("**bold** se shuru hone wali line list nahi banti", () => {
  assert.equal(md("**Note**: kuch bhi"), "<p><strong>Note</strong>: kuch bhi</p>");
});

test("table (header, separator, rows) aur cell ke andar <br>", () => {
  const out = md("| Step | What |\n|------|------|\n| 1. Prep | Run it<br>and check |\n| 2. Git | `git init` |");
  assert.equal(
    out,
    '<div class="table-wrap"><table><thead><tr><th>Step</th><th>What</th></tr></thead><tbody>' +
      "<tr><td>1. Prep</td><td>Run it<br>and check</td></tr>" +
      "<tr><td>2. Git</td><td><code>git init</code></td></tr></tbody></table></div>"
  );
});

test("code block (band aur bina band, dono)", () => {
  assert.equal(md("```bash\ngit init\ngit add .\n```"), "<pre><code>git init\ngit add .</code></pre>");
  assert.equal(md("```\nunclosed <b>x</b>"), "<pre><code>unclosed &lt;b&gt;x&lt;/b&gt;</code></pre>");
});

test("horizontal rule aur alag-alag paragraphs", () => {
  assert.equal(md("one\n\ntwo\n\n---\n\nthree"), "<p>one</p><p>two</p><hr><p>three</p>");
});

test("paragraph ke andar ek newline <br> ban jati hai", () => {
  assert.equal(md("line1\nline2"), "<p>line1<br>line2</p>");
});

test("SECURITY: HTML sirf text banta hai, tag nahi", () => {
  const out = md('<script>alert(1)</script> <img src=x onerror=alert(1)> **ok**');
  assert.ok(!out.includes("<script>") && !out.includes("<img"), out);
  assert.ok(out.includes("&lt;script&gt;"), out);
  assert.ok(out.includes("<strong>ok</strong>"));
});

test("SECURITY: sirf http/https links, javascript: sirf text rehta hai", () => {
  assert.equal(
    md("[site](https://example.com/a?b=1)"),
    '<p><a href="https://example.com/a?b=1" target="_blank" rel="noopener noreferrer">site</a></p>'
  );
  const bad = md("[x](javascript:alert(1))");
  assert.ok(!bad.includes("<a "), bad);
});

test("SECURITY: code ke andar ka HTML text hi rehta hai", () => {
  assert.equal(md("`<b>x</b>`"), "<p><code>&lt;b&gt;x&lt;/b&gt;</code></p>");
});

test("adhura (streaming ke beech ka) markdown crash nahi karta", () => {
  const partials = ["", "#", "## ", "**bol", "- ", "| a |", "| a |\n|--", "| a |\n|---|\n| b", "```", "[x](http", "*", "1."];
  for (const p of partials) assert.doesNotThrow(() => md(p), JSON.stringify(p));
});

test("khali ya null input", () => {
  assert.equal(md(""), "");
  assert.equal(html(Markdown.render(null, fakeDoc)), "");
});

test("lambe text par bhi tez (infinite loop nahi)", () => {
  const big = ("- item **x** `y`\n").repeat(3000) + ("| a | b |\n|---|---|\n| 1 | 2 |\n").repeat(200);
  const t = Date.now();
  md(big);
  assert.ok(Date.now() - t < 3000);
});

test("asli jaisa jawab: heading + bullets + table ek saath", () => {
  const answer = [
    "Ye document Streamlit app ko TiDB Cloud par deploy karne ke baare mein hai.",
    "",
    "## Key points",
    "- **Prepare**: app local par chalao",
    "- **Deploy**: Streamlit Community Cloud par",
    "",
    "## Steps",
    "| Step | Kaam |",
    "|---|---|",
    "| 1 | requirements.txt banao |",
  ].join("\n");
  const out = md(answer);
  assert.ok(out.startsWith("<p>Ye document"));
  assert.ok(out.includes("<h3>Key points</h3><ul><li><strong>Prepare</strong>: app local par chalao</li>"));
  assert.ok(out.includes("<h3>Steps</h3>") && out.includes("<th>Step</th>") && out.includes("<td>requirements.txt banao</td>"));
});
