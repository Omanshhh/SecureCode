/* SecureCode workbench - client side. Talks to the Flask API in app.py. */
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const DEFAULT_SOURCE = `int main() {
    char buffer[8];
    char input[20];

    strcpy(buffer, input);

    return 0;
}`;

  const C_KEYWORDS = new Set([
    "int", "char", "float", "void", "if", "else", "while", "for", "return", "do", "break",
    "continue", "struct", "const", "unsigned", "signed", "long", "short", "double", "sizeof",
    "static", "switch", "case", "default",
  ]);

  const state = {
    report: null,
    severity: "ALL",
    astMode: "tree",
    cfgMode: "graph",
    cfgFunction: null,
    vizPromise: null,
    marks: new Map(),      // line -> severity / "ERROR"
  };

  const els = {
    source: $("#source"),
    highlight: $("#highlight"),
    gutter: $("#gutter"),
    runBtn: $("#runBtn"),
    results: $(".results"),
  };

  // ---------------------------------------------------------------
  // Utilities
  // ---------------------------------------------------------------

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));

  function toast(message) {
    const t = $("#toast");
    t.textContent = message;
    t.classList.add("show");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => t.classList.remove("show"), 2200);
  }

  function animateNumber(el, to, duration = 700) {
    const from = Number(el.dataset.value || 0);
    el.dataset.value = to;
    const start = performance.now();
    const step = (now) => {
      const p = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(from + (to - from) * eased);
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  // ---------------------------------------------------------------
  // Editor: syntax highlight overlay + gutter + finding marks
  // ---------------------------------------------------------------

  function highlightLine(text, inComment) {
    let out = "";
    let i = 0;
    while (i < text.length) {
      if (inComment) {
        const end = text.indexOf("*/", i);
        const stop = end === -1 ? text.length : end + 2;
        out += `<span class="tk-com">${esc(text.slice(i, stop))}</span>`;
        i = stop;
        inComment = end === -1;
        continue;
      }
      const rest = text.slice(i);
      let m;
      if (rest.startsWith("//")) {
        out += `<span class="tk-com">${esc(rest)}</span>`;
        break;
      }
      if (rest.startsWith("/*")) { inComment = true; continue; }
      if ((m = rest.match(/^"(?:[^"\\]|\\.)*"?/))) {
        out += `<span class="tk-str">${esc(m[0])}</span>`;
      } else if ((m = rest.match(/^'(?:[^'\\]|\\.)*'?/))) {
        out += `<span class="tk-str">${esc(m[0])}</span>`;
      } else if ((m = rest.match(/^\d+(?:\.\d+)?/))) {
        out += `<span class="tk-num">${m[0]}</span>`;
      } else if ((m = rest.match(/^[A-Za-z_]\w*/))) {
        const word = m[0];
        if (C_KEYWORDS.has(word)) out += `<span class="tk-kw">${word}</span>`;
        else if (/^\s*\(/.test(rest.slice(word.length))) out += `<span class="tk-fn">${word}</span>`;
        else out += word;
      } else {
        m = [rest[0]];
        out += esc(rest[0]);
      }
      i += m[0].length;
    }
    return { html: out, inComment };
  }

  function renderEditor() {
    const lines = els.source.value.split("\n");
    let inComment = false;
    const html = lines.map((line, idx) => {
      const res = highlightLine(line, inComment);
      inComment = res.inComment;
      const mark = state.marks.get(idx + 1);
      return `<span class="ln${mark ? " mark-" + mark : ""}" data-line="${idx + 1}">${res.html || " "}</span>`;
    }).join("");
    els.highlight.innerHTML = html;
    els.gutter.innerHTML = lines.map((_, idx) => {
      const mark = state.marks.get(idx + 1);
      return `<div${mark ? ` class="flag-${mark}"` : ""}>${idx + 1}</div>`;
    }).join("");
    syncScroll();
  }

  function syncScroll() {
    els.highlight.scrollTop = els.source.scrollTop;
    els.highlight.scrollLeft = els.source.scrollLeft;
    els.gutter.scrollTop = els.source.scrollTop;
  }

  function setMarks(report) {
    state.marks.clear();
    if (!report) return;
    if (!report.ok && report.error) {
      const m = report.error.match(/line (\d+)/i);
      if (m) state.marks.set(Number(m[1]), "ERROR");
      return;
    }
    const rank = { HIGH: 0, MEDIUM: 1, LOW: 2 };
    for (const f of report.findings) {
      const current = state.marks.get(f.line);
      if (!current || rank[f.severity] < rank[current]) state.marks.set(f.line, f.severity);
    }
  }

  function jumpToLine(line) {
    const lh = parseFloat(getComputedStyle(els.source).lineHeight) || 22;
    const target = Math.max(0, (line - 1) * lh - els.source.clientHeight / 3);
    els.source.scrollTo({ top: target, behavior: "smooth" });
    const lines = els.source.value.split("\n");
    const start = lines.slice(0, line - 1).reduce((n, l) => n + l.length + 1, 0);
    els.source.focus({ preventScroll: true });
    els.source.setSelectionRange(start, start + (lines[line - 1] || "").length);
    $(".editor").scrollIntoView({ behavior: "smooth", block: "center" });
    const ln = $(`.ln[data-line="${line}"]`, els.highlight);
    if (ln) {
      ln.classList.remove("pulse");
      void ln.offsetWidth;
      ln.classList.add("pulse");
    }
  }

  function insertAtCursor(text) {
    const { selectionStart: s, selectionEnd: e, value } = els.source;
    els.source.value = value.slice(0, s) + text + value.slice(e);
    els.source.selectionStart = els.source.selectionEnd = s + text.length;
    onSourceEdited();
  }

  function onSourceEdited() {
    // Marks no longer match the text once it changes.
    if (state.marks.size) state.marks.clear();
    renderEditor();
  }

  els.source.addEventListener("input", onSourceEdited);
  els.source.addEventListener("scroll", syncScroll);
  els.source.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      runAnalysis();
    } else if (e.key === "Tab") {
      e.preventDefault();
      insertAtCursor("    ");
    } else if (e.key === "Enter") {
      // Keep the current indentation, add a level after "{".
      e.preventDefault();
      const before = els.source.value.slice(0, els.source.selectionStart);
      const lineStart = before.lastIndexOf("\n") + 1;
      const indent = before.slice(lineStart).match(/^\s*/)[0];
      insertAtCursor("\n" + indent + (before.trimEnd().endsWith("{") ? "    " : ""));
    }
  });

  // ---------------------------------------------------------------
  // API
  // ---------------------------------------------------------------

  async function checkHealth() {
    const badge = $("#engineStatus");
    try {
      const res = await fetch("/api/health", { cache: "no-store" });
      if (!res.ok) throw new Error();
      badge.dataset.state = "online";
      $(".engine-label", badge).textContent = "Engine online";
    } catch {
      badge.dataset.state = "offline";
      $(".engine-label", badge).textContent = "Engine offline";
    }
  }

  async function loadSamples() {
    try {
      const names = await (await fetch("/api/samples")).json();
      const select = $("#sampleSelect");
      for (const name of names) {
        const opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name;
        select.appendChild(opt);
      }
    } catch { /* samples are optional */ }
  }

  function setFileName(name) {
    $("#fileName").textContent = (name || "input.c").toUpperCase();
  }

  $("#sampleSelect").addEventListener("change", async (e) => {
    const name = e.target.value;
    if (!name) return;
    const data = await (await fetch(`/api/samples/${encodeURIComponent(name)}`)).json();
    els.source.value = data.source;
    setFileName(name);
    onSourceEdited();
    e.target.value = "";
    runAnalysis();
  });

  $("#uploadBtn").addEventListener("click", () => $("#fileInput").click());
  $("#fileInput").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    els.source.value = await file.text();
    setFileName(file.name);
    onSourceEdited();
    e.target.value = "";
  });

  $("#clearBtn").addEventListener("click", () => {
    els.source.value = "";
    setFileName("input.c");
    onSourceEdited();
    els.source.focus();
  });

  const STAGES = ["lexer", "parser", "semantic", "cfg", "rules"];

  function setStages(mode, report) {
    const items = $$("#stages li");
    items.forEach((li) => li.classList.remove("done", "fail", "run"));
    if (mode === "running") {
      items.forEach((li) => li.classList.add("run"));
      return;
    }
    if (!report) return;
    if (report.ok) {
      items.forEach((li, i) => setTimeout(() => li.classList.add("done"), i * 90));
      return;
    }
    // Failed in lexing or parsing.
    const failed = /LexerError/.test(report.error || "") ? "lexer" : "parser";
    const idx = STAGES.indexOf(failed);
    items.forEach((li, i) => {
      if (i < idx) li.classList.add("done");
      else if (i === idx) li.classList.add("fail");
    });
  }

  async function runAnalysis() {
    const source = els.source.value;
    if (!source.trim()) {
      toast("Nothing to analyze - write or load some C code first.");
      return;
    }
    els.runBtn.classList.add("loading");
    els.runBtn.disabled = true;
    setStages("running");

    let report;
    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source }),
      });
      report = await res.json();
    } catch (err) {
      report = { ok: false, error: "Could not reach the analysis engine. Is `python app.py` running?" };
      $("#engineStatus").dataset.state = "offline";
      $(".engine-label").textContent = "Engine offline";
    } finally {
      els.runBtn.classList.remove("loading");
      els.runBtn.disabled = false;
    }

    state.report = report;
    setMarks(report);
    renderEditor();
    renderAll(report);
  }

  els.runBtn.addEventListener("click", runAnalysis);

  // ---------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------

  function renderAll(report) {
    setStages("done", report);

    const banner = $("#errorBanner");
    if (!report.ok) {
      banner.hidden = false;
      banner.textContent = report.error || "Analysis failed.";
    } else {
      banner.hidden = true;
    }

    renderSummary(report);
    els.results.classList.toggle("is-empty", !report.ok);
    $("#exportBtn").disabled = !report.ok;
    if (!report.ok) return;

    renderFindings();
    renderTokens();
    renderAst();
    renderSymbols();
    renderCfgSelect();
  }

  function renderSummary(report) {
    const s = report.summary || { risk_score: 0, counts: { HIGH: 0, MEDIUM: 0, LOW: 0 }, total: 0, functions: 0 };
    if (report.ok) {
      animateNumber($("#riskScore"), s.risk_score);
    } else {
      $("#riskScore").textContent = "—";
      $("#riskScore").dataset.value = 0;
    }
    animateNumber($("#countHigh"), s.counts.HIGH);
    animateNumber($("#countMedium"), s.counts.MEDIUM);
    animateNumber($("#countLow"), s.counts.LOW);

    const fill = $("#gaugeFill");
    const circumference = 169.6;
    fill.style.strokeDashoffset = circumference * (1 - (report.ok ? s.risk_score : 0) / 100);
    const color = !report.ok ? "var(--ink-3)" : s.risk_score >= 70 ? "var(--high)" : s.risk_score >= 30 ? "var(--accent)" : s.risk_score > 0 ? "var(--medium)" : "var(--ok)";
    fill.style.stroke = color;
    $("#riskScore").style.color = color;

    let text;
    if (!report.ok) text = "Analysis stopped - the source did not parse.";
    else if (s.total === 0) text = `No findings across ${s.functions} function${s.functions === 1 ? "" : "s"}. Looks clean.`;
    else text = `${s.total} finding${s.total === 1 ? "" : "s"} across ${s.functions} function${s.functions === 1 ? "" : "s"}.`;
    $("#summaryText").textContent = text;

    $("#elapsed").textContent = report.elapsed_ms != null ? `${report.elapsed_ms} ms · ${(report.tokens || []).length} tokens` : "";
    $("#findingsBadge").textContent = report.ok ? s.total : "!";
  }

  function renderFindings() {
    const { findings, semantic_errors: semanticErrors, rule_errors: ruleErrors } = state.report;
    const rows = findings.filter((f) => state.severity === "ALL" || f.severity === state.severity);
    const body = $("#findingsBody");

    if (!findings.length) {
      body.innerHTML = `<tr><td colspan="5" class="no-findings">No vulnerabilities detected</td></tr>`;
    } else if (!rows.length) {
      body.innerHTML = `<tr><td colspan="5" class="no-findings">No ${state.severity.toLowerCase()} findings</td></tr>`;
    } else {
      body.innerHTML = rows.map((f) => `
        <tr data-line="${f.line}" title="Jump to line ${f.line}">
          <td><span class="sev ${f.severity}">${f.severity}</span></td>
          <td><span class="finding-title">${esc(f.type)}</span><span class="finding-rule">${esc(f.rule_id)}</span>${f.function ? `<span class="finding-fn">in ${esc(f.function)}()</span>` : ""}</td>
          <td><span class="line-link">${f.line}</span></td>
          <td>${esc(f.message)}</td>
          <td>${esc(f.suggested_fix)}</td>
        </tr>`).join("");
    }

    const diagnostics = [
      ...semanticErrors.map((e) => `line ${e.line ?? "?"} · ${e.type ?? "SemanticError"} · ${e.message}`),
      ...ruleErrors.map((e) => `rule ${e.rule_id} crashed · ${e.error}`),
    ];
    $("#semanticBlock").hidden = !diagnostics.length;
    $("#semanticList").innerHTML = diagnostics.map((d) => `<li>${esc(d)}</li>`).join("");
  }

  $("#findingsBody").addEventListener("click", (e) => {
    const row = e.target.closest("tr[data-line]");
    if (row) jumpToLine(Number(row.dataset.line));
  });

  $("#severityChips").addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    $$("#severityChips .chip").forEach((c) => c.classList.toggle("active", c === chip));
    state.severity = chip.dataset.sev;
    if (state.report?.ok) renderFindings();
  });

  function renderTokens() {
    const q = $("#tokenSearch").value.trim().toLowerCase();
    const tokens = state.report.tokens.filter((t) => !q || t.lexeme.toLowerCase().includes(q) || t.type.toLowerCase().includes(q));
    $("#tokenCount").textContent = `${tokens.length} / ${state.report.tokens.length} tokens`;
    $("#tokensBody").innerHTML = tokens.map((t) => `
      <tr data-line="${t.line}">
        <td>${t.index}</td>
        <td><span class="ttype ${t.type}">${t.type}</span></td>
        <td>${esc(t.lexeme)}</td>
        <td>${t.line}:${t.column}</td>
      </tr>`).join("");
  }
  $("#tokenSearch").addEventListener("input", () => state.report?.ok && renderTokens());
  $("#tokensBody").addEventListener("dblclick", (e) => {
    const row = e.target.closest("tr[data-line]");
    if (row) jumpToLine(Number(row.dataset.line));
  });

  function attrHtml(key, value) {
    let cls = "attr-v";
    let shown;
    if (typeof value === "number") { cls += " num"; shown = value; }
    else if (typeof value === "boolean" || value === null) { cls += " kw"; shown = value === null ? "None" : value ? "True" : "False"; }
    else shown = `'${esc(value)}'`;
    return `<span class="attr-k">${esc(key)}=</span><span class="${cls}">${shown}</span>`;
  }

  function astNodeHtml(node, depth) {
    if (!node) return `<div class="leaf">None</div>`;
    const attrs = Object.entries(node.attrs).map(([k, v]) => attrHtml(k, v)).join(", ");
    const head = `<span class="nname">${node.node}</span>(${attrs})`;
    const kids = node.children.filter((c) => c.nodes.length);
    if (!kids.length) return `<div class="leaf">${head}</div>`;
    const inner = kids.map((c) => `<div class="field">${c.field}:</div>${c.nodes.map((n) => astNodeHtml(n, depth + 1)).join("")}`).join("");
    return `<details ${depth < 6 ? "open" : ""}><summary>${head}</summary>${inner}</details>`;
  }

  function renderAst() {
    const { ast, ast_text: astText } = state.report;
    $("#astTree").innerHTML = astNodeHtml(ast, 0);
    $("#astText").textContent = astText;
    $("#astTree").hidden = state.astMode !== "tree";
    $("#astText").hidden = state.astMode !== "text";
  }

  $("#astMode").addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    $$("#astMode .chip").forEach((c) => c.classList.toggle("active", c === chip));
    state.astMode = chip.dataset.mode;
    $("#astTree").hidden = state.astMode !== "tree";
    $("#astText").hidden = state.astMode !== "text";
  });
  $("#astExpand").addEventListener("click", () => $$("#astTree details").forEach((d) => (d.open = true)));
  $("#astCollapse").addEventListener("click", () => $$("#astTree details").forEach((d, i) => (d.open = i === 0)));

  function renderSymbols() {
    const rows = state.report.symbols;
    $("#symbolsBody").innerHTML = rows.length ? rows.map((s) => `
      <tr data-line="${s.line}">
        <td>${esc(s.name)}</td>
        <td>${esc(s.type)}</td>
        <td>${esc(s.scope)}</td>
        <td>${s.line}</td>
        <td><span class="state ${s.initialized ? "init" : "uninit"}">${s.initialized ? "initialized" : "uninitialized"}</span></td>
      </tr>`).join("") : `<tr><td colspan="5" class="no-findings">No symbols declared</td></tr>`;
  }
  $("#symbolsBody").addEventListener("dblclick", (e) => {
    const row = e.target.closest("tr[data-line]");
    if (row) jumpToLine(Number(row.dataset.line));
  });

  // ---------- CFG ----------

  function renderCfgSelect() {
    const names = Object.keys(state.report.cfgs);
    const select = $("#cfgSelect");
    if (!names.includes(state.cfgFunction)) state.cfgFunction = names[0] || null;
    select.innerHTML = names.map((n) => `<option value="${esc(n)}" ${n === state.cfgFunction ? "selected" : ""}>${esc(n)}</option>`).join("");
    select.disabled = names.length < 2;
    renderCfg();
  }

  $("#cfgSelect").addEventListener("change", (e) => {
    state.cfgFunction = e.target.value;
    renderCfg();
  });

  $("#cfgMode").addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    $$("#cfgMode .chip").forEach((c) => c.classList.toggle("active", c === chip));
    state.cfgMode = chip.dataset.mode;
    $("#cfgGraph").hidden = state.cfgMode !== "graph";
    $("#cfgBlocks").hidden = state.cfgMode !== "blocks";
  });

  function getViz() {
    if (!state.vizPromise) {
      state.vizPromise = window.Viz ? window.Viz.instance() : Promise.reject(new Error("viz.js not loaded"));
    }
    return state.vizPromise;
  }

  async function renderCfg() {
    const cfg = state.report.cfgs[state.cfgFunction];
    const graphEl = $("#cfgGraph");
    const blocksEl = $("#cfgBlocks");

    if (!cfg) {
      $("#edgeLine").textContent = "No functions defined - nothing to draw.";
      graphEl.innerHTML = "";
      blocksEl.innerHTML = "";
      $("#dotSource").textContent = "";
      return;
    }

    $("#edgeLine").innerHTML = cfg.edges
      .map((e) => `n${e.source} → n${e.target} <em>${e.type}</em>`)
      .join("&nbsp;&nbsp;·&nbsp;&nbsp;");
    $("#dotSource").textContent = cfg.dot;

    const outgoing = new Map();
    cfg.edges.forEach((e) => {
      if (!outgoing.has(e.source)) outgoing.set(e.source, []);
      outgoing.get(e.source).push(`n${e.target} (${e.type})`);
    });
    blocksEl.innerHTML = cfg.nodes.map((n) => `
      <div class="block" data-lines="${n.lines.join(",")}">
        <div class="block-head">n${n.id} · ${esc(n.label)}</div>
        <div class="block-detail">${esc(n.detail) || "—"}</div>
        <div class="block-out">→ ${(outgoing.get(n.id) || ["(none)"]).join(", ")}</div>
      </div>`).join("");

    graphEl.innerHTML = `<p class="cfg-fallback">Rendering graph…</p>`;
    try {
      const viz = await getViz();
      const svg = viz.renderSVGElement(cfg.dot);
      const types = new Map(cfg.edges.map((e) => [`n${e.source}->n${e.target}`, e.type]));
      const nodeInfo = new Map(cfg.nodes.map((n) => [`n${n.id}`, n]));
      $$("g.edge", svg).forEach((g) => g.classList.add(types.get($("title", g)?.textContent) || "normal"));
      $$("g.node", svg).forEach((g) => {
        const info = nodeInfo.get($("title", g)?.textContent);
        if (!info) return;
        if (info.label === "ENTRY") g.classList.add("entry");
        if (info.label === "EXIT") g.classList.add("exit");
        g.dataset.lines = info.lines.join(",");
      });
      graphEl.innerHTML = "";
      graphEl.appendChild(svg);
    } catch {
      graphEl.innerHTML = `<p class="cfg-fallback">Graph renderer unavailable offline - switch to Blocks or copy the DOT source.</p>`;
    }
  }

  function jumpFromLines(el) {
    const lines = (el?.dataset.lines || "").split(",").filter(Boolean).map(Number);
    if (lines.length) jumpToLine(lines[0]);
  }
  $("#cfgGraph").addEventListener("click", (e) => jumpFromLines(e.target.closest("g.node")));
  $("#cfgBlocks").addEventListener("click", (e) => jumpFromLines(e.target.closest(".block")));

  $("#copyDot").addEventListener("click", async (e) => {
    e.preventDefault();
    try {
      await navigator.clipboard.writeText($("#dotSource").textContent);
      toast("DOT source copied");
    } catch {
      toast("Clipboard unavailable");
    }
  });

  // ---------- Export ----------

  $("#exportBtn").addEventListener("click", () => {
    if (!state.report) return;
    const blob = new Blob([JSON.stringify({ source: els.source.value, ...state.report }, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = ($("#fileName").textContent.toLowerCase().replace(/\.c$/, "") || "report") + ".securecode.json";
    a.click();
    URL.revokeObjectURL(a.href);
  });

  // ---------------------------------------------------------------
  // Tabs
  // ---------------------------------------------------------------

  function moveIndicator() {
    const active = $(".tab.active");
    const ind = $("#tabIndicator");
    if (!active) return;
    ind.style.left = `${active.offsetLeft}px`;
    ind.style.width = `${active.offsetWidth}px`;
  }

  $("#tabs").addEventListener("click", (e) => {
    const tab = e.target.closest(".tab");
    if (!tab) return;
    $$(".tab").forEach((t) => {
      t.classList.toggle("active", t === tab);
      t.setAttribute("aria-selected", t === tab);
    });
    $$(".panel").forEach((p) => p.classList.toggle("active", p.dataset.panel === tab.dataset.tab));
    moveIndicator();
  });
  window.addEventListener("resize", moveIndicator);

  // ---------------------------------------------------------------
  // Theme
  // ---------------------------------------------------------------

  function applyTheme(theme) {
    if (theme) document.documentElement.dataset.theme = theme;
  }
  try { applyTheme(localStorage.getItem("securecode-theme")); } catch { /* storage blocked */ }
  $("#themeToggle").addEventListener("click", () => {
    const current = document.documentElement.dataset.theme
      || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = current === "dark" ? "light" : "dark";
    applyTheme(next);
    try { localStorage.setItem("securecode-theme", next); } catch { /* ignore */ }
  });

  // ---------------------------------------------------------------
  // Boot
  // ---------------------------------------------------------------

  els.source.value = DEFAULT_SOURCE;
  els.results.classList.add("is-empty");
  renderEditor();
  document.fonts?.ready.then(moveIndicator);
  moveIndicator();
  checkHealth().then(() => {
    if ($("#engineStatus").dataset.state === "online") runAnalysis();
  });
  loadSamples();
  setInterval(checkHealth, 30000);
})();
