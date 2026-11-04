"use strict";
// 원문 확인 화면. 외부 라이브러리 없이 DOM을 직접 만든다(본문 글자는 모두 textContent로 넣어 HTML로 해석되지 않게).

const RED = new Set(["불일치", "시각 누락", "요약에 없음", "칸엔 없음·본문엔 있음"]);
const ROLE_LABEL = { top: "요약 위쪽 칸", body: "요약 본문", original: "원문" };
const WEEK = "일월화수목금토";
let current = null;

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    e.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return e;
}

function short(s, n = 70) {
  s = s || "";
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function verdictBadge(v) {
  const cls = RED.has(v) ? "red" : (v === "확인 필요" || v === "원문 미입력") ? "check" : "ok";
  const box = el("div", {}, el("span", { class: `v ${cls}`, text: v }));
  if (v === "다른 점을 찾지 못함") box.append(el("span", { class: "v-sub", text: "원문 확인 권장" }));
  if (v === "원문 미입력") box.append(el("span", { class: "v-sub", text: "원문을 넣으면 대조합니다" }));
  if (v === "원문에도 없음") box.append(el("span", { class: "v-sub", text: "요약·원문 모두 해당 내용 없음" }));
  return box;
}

function evidence(v) {
  if (!v || !v.quotes || !v.quotes.length) return null;
  const q = v.quotes[0];
  const more = v.quotes.length > 1 ? ` 외 ${v.quotes.length - 1}개` : "";
  return el("span", { class: "ai-ev" }, el("span", { class: "tag", text: "AI가 찾은 근거" }),
    `“${short(q.text, 60)}” (${q.sid})${more}`);
}

function valueBlock(v, cls) {
  if (!v || v.status === "not_given") return el("span", { class: "val-none", text: "—" });
  if (v.status === "absent") return el("span", { class: "val-none", text: "없음" });
  if (v.status === "unverified") {
    return el("div", {}, el("span", { class: "val-none", text: "확인 필요" }),
      el("span", { class: "ai-ev", text: v.note || "AI 근거를 출처에서 확인하지 못해 값을 버렸습니다." }));
  }
  const by = v.value_by === "코드" ? "코드가 다시 읽음" : v.value_by;
  return el("div", {}, el("span", { class: cls, text: v.value || "(값 없음)" }),
    by ? el("span", { class: "by", text: by }) : null, evidence(v));
}

function summaryCell(item, isRed) {
  const td = el("td", { "data-label": "요약 값", class: isRed ? "diff" : null });
  const top = item.values.top, body = item.values.body;
  td.append(valueBlock(top, "val-sum"));
  if (body && body.status !== "not_given") {
    const line = el("div", { class: "val-body" }, "같은 페이지 본문: ");
    if (body.status === "found") {
      line.append(body.value || "");
      const ev = evidence(body);
      if (ev) line.append(ev);
    } else line.append(body.status === "absent" ? "없음" : "확인 필요");
    td.append(line);
  }
  return td;
}

function segIndex(src) {
  const m = new Map();
  (src.segments || []).forEach((s, i) => m.set(s.sid, i));
  return m;
}

function renderSegment(seg, marks) {
  // marks: [[start, end], ...] (문단 안 글자 위치)
  const span = el("span", { class: "seg" }, el("span", { class: "sid", text: seg.sid }));
  const text = seg.text;
  marks.sort((a, b) => a[0] - b[0]);
  let pos = 0;
  for (const [s, e] of marks) {
    if (s > pos) span.append(text.slice(pos, s));
    span.append(el("mark", { text: text.slice(Math.max(s, pos), e) }));
    pos = Math.max(pos, e);
  }
  if (pos < text.length) span.append(text.slice(pos));
  return span;
}

function contextView(src, quotes, isSummary) {
  const idx = segIndex(src);
  const marks = new Map(); // seg index -> [[s,e]]
  const show = new Set();
  for (const q of quotes) {
    const ids = q.sids && q.sids.length ? q.sids : [q.sid];
    ids.forEach((sid, k) => {
      const i = idx.get(sid);
      if (i === undefined) return;
      const segLen = src.segments[i].text.length;
      const s = k === 0 ? q.start : 0;
      const e = k === ids.length - 1 ? q.end : segLen;
      if (!marks.has(i)) marks.set(i, []);
      marks.get(i).push([s, Math.min(e, segLen)]);
      for (let j = Math.max(0, i - 2); j <= Math.min(src.segments.length - 1, i + 2); j++) show.add(j);
    });
  }
  const box = el("div", { class: `ctx ${isSummary ? "sum" : ""}` });
  let last = -1;
  [...show].sort((a, b) => a - b).forEach((i) => {
    if (last >= 0 && i > last + 1) box.append(el("span", { class: "gap", text: "⋯" }));
    box.append(renderSegment(src.segments[i], marks.get(i) || []));
    last = i;
  });
  return box;
}

function detailRow(item, result) {
  const td = el("td", { colspan: "4" });
  const isRed = RED.has(item.verdict);
  td.append(el("p", { class: `reason ${isRed ? "red" : ""}`, text: item.reason }));
  if (item.stage1 && item.stage2) {
    td.append(el("p", { class: "hint", text: `같은 페이지 칸↔본문 대조: ${item.stage1.verdict} — ${item.stage1.reason}` }));
  }
  for (const role of ["top", "body", "original"]) {
    const v = item.values[role];
    const src = result.sources[role];
    if (!v || !src || v.status === "not_given") continue;
    const g = el("div", { class: "ctx-group" });
    const label = role === "top" ? (src.label || ROLE_LABEL.top) : ROLE_LABEL[role];
    g.append(el("div", { class: `ctx-title ${role === "original" ? "" : "sum"}`, text: label }));
    if (v.status === "found") {
      g.append(contextView(src, v.quotes, role !== "original"));
      g.append(el("div", { class: "ok-check", text: `AI가 찾은 근거 ${v.quotes.length}개 — 출처에 글자 그대로 있는지 코드가 확인함` }));
    } else if (v.status === "absent") {
      g.append(el("div", { class: "hint", text: "AI가 이 출처에서 해당 문장을 찾지 못했습니다." }));
    } else {
      g.append(el("div", { class: "hint", text: v.note || "확인 필요" }));
    }
    if (v.rejected_quotes && v.rejected_quotes.length) {
      const r = el("div", { class: "rejected" }, "출처에 글자 그대로 없어 버린 AI 인용: ");
      v.rejected_quotes.slice(0, 3).forEach((q) => r.append(el("s", { text: short(q, 80) }), " "));
      g.append(r);
    }
    if (v.note && v.status === "found") g.append(el("div", { class: "hint", text: v.note }));
    td.append(g);
  }
  return el("tr", { class: "detail" }, td);
}

function fmtDate(iso, time) {
  const d = new Date(iso + "T00:00:00");
  let s = `${iso}(${WEEK[d.getDay()]})`;
  if (time === "24:00") s += " 24:00(그날 끝)";
  else s += time ? ` ${time}` : " 시각 없음";
  return s;
}

function reportText(result) {
  const title = (result.example && result.example.title) || (result.meta && result.meta.title) || "공고";
  const lines = [`[정정 요청] 「${title}」 공고 정보가 주최 측 원문과 다릅니다.`];
  for (const it of result.items) {
    if (!RED.has(it.verdict)) continue;
    const top = it.values.top, orig = it.values.original;
    const shown = top && top.status === "found" ? top.value : "표시 없음";
    const oq = orig && orig.status === "found" && orig.quotes.length ? `“${orig.quotes[0].text}”` : "";
    lines.push(`- ${it.name}: 포털 표시 ${shown}${oq ? ` / 원문 ${oq}` : ""} (${it.verdict})`);
  }
  const o = result.sources.original;
  if (o && o.origin) lines.push(`원문: ${o.origin}`);
  lines.push("원문을 다시 확인하시고 고쳐 주시면 감사하겠습니다.");
  return lines.join("\n");
}

function render(result, opts = {}) {
  current = result;
  const box = document.getElementById("result");
  box.replaceChildren();
  box.classList.remove("hidden");
  const title = (result.example && result.example.title) || (result.meta && result.meta.title) || "직접 확인 결과";
  const head = el("div", { class: "res-head" }, el("h2", { text: title }));
  if (opts.saved) head.append(el("span", { class: "saved-badge", text: result.example.label || "저장 결과" }));
  box.append(head);

  const links = el("div", { class: "res-links" });
  for (const role of ["top", "original"]) {
    const src = result.sources[role];
    if (!src) continue;
    const name = role === "top" ? "요약" : "원문";
    const line = el("div", {}, `${name}: `);
    if (/^https?:/.test(src.origin)) line.append(el("a", { href: src.origin, target: "_blank", rel: "noopener noreferrer", text: short(src.origin, 70) }));
    else line.append(src.origin);
    links.append(line);
  }
  if (!result.sources.original) links.append(el("div", { text: "원문 없음 — 포털 페이지 안 위쪽 칸과 본문만 대조" }));
  const home = result.meta && result.meta.homepage_url;
  if (!result.sources.original && home && /^https?:/.test(home)) {
    links.append(el("div", {}, "포털에 적힌 홈페이지(원문 후보): ", el("a", { href: home, target: "_blank", rel: "noopener noreferrer", text: short(home, 70) })));
  }
  box.append(links);

  const s = result.summary;
  const sum = el("div", { class: "res-sum" });
  if (s.red_items.length) sum.append(el("span", { class: "red-text", text: `빨간 항목 ${s.red_items.length}개: ${s.red_items.join(", ")}` }));
  else sum.append("빨간 항목 없음 — 다른 점을 찾지 못했지만, 원문 확인을 권장합니다.");
  if (s.needs_check.length) sum.append(el("br"), `확인 필요 ${s.needs_check.length}개: ${s.needs_check.join(", ")}`);
  const rejected = s.quotes_total - s.quotes_verified;
  sum.append(el("br"), `화면에 나온 근거 ${s.quotes_verified}개는 모두 출처에 글자 그대로 있는 문장입니다(코드 확인).`);
  if (rejected > 0) sum.append(` AI가 낸 인용 중 ${rejected}개는 출처에 없어 버렸습니다.`);
  const dd = result.deadline_dday;
  if (dd) {
    const basis = { original: "원문", body: "같은 페이지 본문", top: "요약 칸" }[dd.basis];
    const dtext = dd.days_left > 0 ? `D-${dd.days_left}` : dd.days_left === 0 ? "D-day" : `마감 지남(${-dd.days_left}일 전)`;
    sum.append(el("br"), el("span", { class: "dday" }, `${basis} 기준 마감: `, el("b", { text: fmtDate(dd.date, dd.time) }),
      ` · ${result.today} 기준 ${dtext}`));
  }
  box.append(sum);

  const notes = [];
  for (const role of ["top", "body", "original"]) {
    const src = result.sources[role];
    if (src && src.notes) src.notes.forEach((n) => notes.push(`${ROLE_LABEL[role]}: ${n}`));
  }
  if (notes.length) box.append(el("ul", { class: "notes" }, notes.map((n) => el("li", { text: n }))));

  const table = el("table", { class: "items" },
    el("colgroup", {}, el("col", { class: "c-item" }), el("col", { class: "c-sum" }), el("col", { class: "c-orig" }), el("col", { class: "c-v" })),
    el("thead", {}, el("tr", {}, el("th", { text: "항목" }), el("th", { text: "요약 값" }), el("th", { text: "원문 값" }), el("th", { text: "판정" }))));
  const tbody = el("tbody");
  for (const it of result.items) {
    const isRed = RED.has(it.verdict);
    const row = el("tr", { class: "item-row", tabindex: "0", "aria-expanded": "false" },
      el("td", { "data-label": "항목" }, el("span", { class: "item-name", text: it.name })),
      summaryCell(it, isRed),
      el("td", { "data-label": "원문 값" }, valueBlock(it.values.original, "val-orig")),
      el("td", { "data-label": "판정" }, verdictBadge(it.verdict)));
    const toggle = () => {
      const next = row.nextElementSibling;
      if (next && next.classList.contains("detail")) {
        next.remove(); row.classList.remove("open"); row.setAttribute("aria-expanded", "false");
      } else {
        row.after(detailRow(it, result)); row.classList.add("open"); row.setAttribute("aria-expanded", "true");
      }
    };
    row.addEventListener("click", toggle);
    row.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
    tbody.append(row);
  }
  table.append(tbody);
  box.append(el("p", { class: "hint", text: "행을 누르면 근거 문장이 출처 앞뒤 문맥 안에서 노랗게 표시됩니다." }), table);

  if (s.red_items.length) {
    const rb = el("div", { class: "report-box" });
    const ta = el("textarea", { rows: "6", readonly: "readonly", class: "hidden" });
    const btn = el("button", { class: "btn ghost", type: "button", text: "포털 오류 신고 문장 복사" });
    btn.addEventListener("click", async () => {
      ta.value = reportText(result);
      ta.classList.remove("hidden");
      try { await navigator.clipboard.writeText(ta.value); btn.textContent = "복사했습니다"; }
      catch { ta.select(); btn.textContent = "아래 글을 복사해 쓰세요"; }
    });
    rb.append(btn, ta);
    box.append(rb);
  }
  box.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function loadExample(id, btn) {
  document.querySelectorAll(".example-buttons button").forEach((b) => b.classList.toggle("active", b === btn));
  const r = await fetch(`/api/examples/${encodeURIComponent(id)}`);
  if (!r.ok) return;
  render(await r.json(), { saved: true });
}

async function refreshMeta() {
  try {
    const meta = await (await fetch("/api/meta")).json();
    document.getElementById("model-name").textContent = `${meta.model_label}, 모델 ID ${meta.model}`;
    document.getElementById("limit-hint").textContent = meta.live_enabled
      ? `직접 확인은 하루 전체 ${meta.daily_limit}회, 접속 주소당 ${meta.ip_daily_limit}회까지입니다(오늘 남은 전체 ${meta.remaining_today}회). 1건에 10~30초 걸립니다.`
      : "이 서버에는 AI 키가 없어 직접 확인을 쓸 수 없습니다. 예시는 볼 수 있습니다.";
    if (!meta.live_enabled) document.getElementById("run-btn").disabled = true;
  } catch { /* 메타를 못 읽어도 예시는 보여 준다 */ }
}

async function init() {
  await refreshMeta();

  const ex = await (await fetch("/api/examples")).json();
  const wrap = document.getElementById("example-buttons");
  for (const e of ex) {
    const b = el("button", { type: "button" }, el("span", { class: "ex-id", text: e.id }), e.title);
    b.addEventListener("click", () => loadExample(e.id, b));
    wrap.append(b);
  }

  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => { x.classList.toggle("active", x === t); x.setAttribute("aria-selected", x === t); });
    document.getElementById("tab-examples").classList.toggle("hidden", t.dataset.tab !== "examples");
    document.getElementById("tab-live").classList.toggle("hidden", t.dataset.tab !== "live");
  }));

  document.getElementById("live-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const fd = new FormData(form);
    const status = document.getElementById("live-status");
    const btn = document.getElementById("run-btn");
    if (!fd.get("summary_url") && !String(fd.get("summary_text") || "").trim()) {
      status.className = "status err"; status.textContent = "요약 주소나 요약 글 중 하나를 넣어 주세요."; return;
    }
    const f = fd.get("original_file");
    if (f && !f.name) fd.delete("original_file");
    btn.disabled = true; status.className = "status"; status.textContent = "원문을 읽고 AI가 근거를 찾는 중입니다(10~30초)…";
    try {
      const r = await fetch("/api/check", { method: "POST", body: fd });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || `오류 ${r.status}`);
      status.textContent = `끝났습니다(${data.elapsed_s}초).`;
      render(data);
    } catch (err) {
      status.className = "status err"; status.textContent = err.message;
    } finally {
      btn.disabled = false;
      refreshMeta();
    }
  });
}

init();
