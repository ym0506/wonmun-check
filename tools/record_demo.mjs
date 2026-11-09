// 시연 영상 녹화: 헤드리스 크롬을 개발자 도구 프로토콜(CDP)로 움직이며 실제 화면을 찍어 mp4로 만든다.
// 직접 확인 1건은 실제로 AI를 부른다(약 0.0033달러). 기다리는 동안의 화면은 영상에서 줄인다(자막에 밝힘).
//
// 실행(로컬 서버가 켜져 있어야 함):
//   WORK=/tmp/demo node tools/record_demo.mjs web/static/demo/demo.mp4
// 환경변수: BASE(기본 http://localhost:8780), WORK(프레임 임시 폴더)

import { spawn, execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const BASE = process.env.BASE || "http://localhost:8780";
const OUT = path.resolve(process.argv[2] || "demo.mp4");
const WORK = process.env.WORK || fs.mkdtempSync("/tmp/demo-");
const PORT = 9333;
const SUMMARY_URL = "https://linkareer.com/activity/342034";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

fs.mkdirSync(WORK, { recursive: true });
for (const f of fs.readdirSync(WORK)) if (f.endsWith(".jpg")) fs.unlinkSync(path.join(WORK, f));

const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`, "--window-size=1280,800",
  `--user-data-dir=${path.join(WORK, "prof")}`, "--hide-scrollbars", "--force-device-scale-factor=1",
  "--no-first-run", "--remote-allow-origins=*", "about:blank"], { stdio: "ignore" });

async function pageTarget() {
  for (let i = 0; i < 60; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const p = list.find((t) => t.type === "page");
      if (p) return p;
    } catch { /* 크롬이 아직 안 뜸 */ }
    await sleep(250);
  }
  throw new Error("크롬 디버깅 포트에 붙지 못함");
}

const target = await pageTarget();
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r, j) => {
  ws.onopen = r;
  ws.onerror = (e) => j(new Error("CDP 연결 실패: " + (e.message || e.type)));
  setTimeout(() => j(new Error("CDP 연결 시간 초과")), 10000);
});
console.log("CDP 연결됨");
let seq = 0;
const pending = new Map();
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    const { res, rej } = pending.get(m.id);
    pending.delete(m.id);
    m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result);
  }
};
const send = (method, params = {}) => new Promise((res, rej) => {
  const id = ++seq;
  pending.set(id, { res, rej });
  ws.send(JSON.stringify({ id, method, params }));
  setTimeout(() => { if (pending.delete(id)) rej(new Error(method + " 시간 초과")); }, 20000);
});
const ev = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result.value;

await send("Page.enable");
await send("Runtime.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 1280, height: 800, deviceScaleFactor: 1, mobile: false });

// ---- 녹화: 약 8장/초. skipping 동안은 1.5초마다 한 장만 남기고 영상에서 짧게 보여 준다.
const frames = [];
let recording = true;
let skipping = false;
let lastKept = 0;
const recorder = (async () => {
  while (recording) {
    const t0 = Date.now();
    try {
      const { data } = await send("Page.captureScreenshot", { format: "jpeg", quality: 82 });
      if (!skipping || t0 - lastKept > 1500) {
        const f = path.join(WORK, `f${String(frames.length).padStart(5, "0")}.jpg`);
        fs.writeFileSync(f, Buffer.from(data, "base64"));
        frames.push({ f, t: t0, skip: skipping });
        if (skipping) lastKept = t0;
      }
    } catch { /* 이동 중에는 찍히지 않을 수 있음 */ }
    await sleep(Math.max(0, 120 - (Date.now() - t0)));
  }
})();

async function go(url) {
  await send("Page.navigate", { url });
  for (let i = 0; i < 80; i++) {
    if ((await ev("document.readyState").catch(() => "")) === "complete") break;
    await sleep(150);
  }
  await sleep(900);
}

async function caption(text) {
  await ev(`(() => {
    let d = document.getElementById("__cap");
    if (!d) {
      d = document.createElement("div"); d.id = "__cap";
      Object.assign(d.style, { position: "fixed", left: "50%", bottom: "26px", transform: "translateX(-50%)",
        width: "1120px", background: "rgba(17,17,17,.88)", color: "#fff",
        font: '600 21px/1.5 "Apple SD Gothic Neo", -apple-system, sans-serif', padding: "12px 22px",
        borderRadius: "10px", zIndex: 2147483647, textAlign: "center", pointerEvents: "none", boxSizing: "border-box" });
      document.body.appendChild(d);
    }
    d.textContent = ${JSON.stringify(text)};
    return true;
  })()`);
}

async function click(sel) {
  const s = JSON.stringify(sel);
  await ev(`document.querySelector(${s}).scrollIntoView({ block: "center", behavior: "smooth" })`);
  await sleep(800);
  await ev(`(() => {
    const e = document.querySelector(${s}); const r = e.getBoundingClientRect();
    const c = document.createElement("div");
    Object.assign(c.style, { position: "fixed", left: (r.left + Math.min(r.width / 2, 60) - 18) + "px", top: (r.top + r.height / 2 - 18) + "px",
      width: "36px", height: "36px", borderRadius: "50%", border: "3px solid #c4231c", background: "rgba(196,35,28,.18)",
      zIndex: 2147483646, pointerEvents: "none", transition: "opacity .6s" });
    document.body.appendChild(c);
    setTimeout(() => (c.style.opacity = "0"), 700); setTimeout(() => c.remove(), 1400);
    e.click(); return true;
  })()`);
}

async function type(sel, text) {
  const s = JSON.stringify(sel);
  for (let i = 2; i < text.length; i += 3) {
    await ev(`document.querySelector(${s}).value = ${JSON.stringify(text.slice(0, i))}`);
    await sleep(35);
  }
  await ev(`document.querySelector(${s}).value = ${JSON.stringify(text)}`);
}

const scrollTo = (y) => ev(`window.scrollTo({ top: ${y}, behavior: "smooth" })`);

// ---- 장면
await go(`${BASE}/`);
// 첫 화면이 실제로 찍히기 시작한 뒤에 진행한다(앞부분이 빠지는 것 방지)
for (let i = 0; i < 100 && frames.length < 4; i++) await sleep(200);
if (frames.length < 4) throw new Error("화면을 찍지 못함");
const startIdx = frames.length - 1;
await caption("「원문 확인」: 공고 요약이 주최 측 원문과 다른 곳을 근거 문장과 함께 찾아 줍니다");
await sleep(4500);
await caption("포털은 마감 11.25(D-21)로 띄웠지만 주최 측 원문의 제출 마감은 11.06입니다(11월 4일 기준)");
await sleep(5500);

await click('.item-row[data-key="deadline"]');
await caption("항목을 누르면 원문 속 근거 문장이 노랗게 보입니다. 코드가 원문에 글자 그대로 있는지 확인한 문장만 띄웁니다");
await sleep(6500);

await click("#example-buttons button:nth-child(2)");
await caption("쇼츠 공모전: 포털 마감 11.15, 밀양시 원문 마감 11.07");
await sleep(5000);
await click("#example-buttons button:nth-child(3)");
await caption("청년정책: 요약만 보면 청년이 신청하는 사업 같지만, 원문의 신청 주체는 기업이고 마감은 오전 11시입니다");
await sleep(6500);

await scrollTo(0);
await sleep(700);
await click('.tab[data-tab="live"]');
await caption("직접 확인: 포털 공고 주소 하나만 넣어도 됩니다(원문 주소나 파일을 함께 넣으면 원문과도 대조)");
await sleep(1200);
await type('input[name="summary_url"]', SUMMARY_URL);
await sleep(1800);
await click("#run-btn");
await caption("Claude Haiku 5.5가 일곱 항목의 근거 문장을 찾고, 같은지 다른지는 코드가 판정합니다(실제 약 20초, 영상에서는 줄임)");
skipping = true;
let status = "";
for (let i = 0; i < 120; i++) {
  status = await ev(`(document.getElementById("live-status") || {}).textContent || ""`);
  const err = await ev(`(document.getElementById("live-status") || {}).className || ""`);
  if (status.includes("끝났습니다") || err.includes("err")) break;
  await sleep(1000);
}
skipping = false;
console.log("직접 확인 상태:", status);
if (!status.includes("끝났습니다")) { recording = false; await recorder; chrome.kill(); throw new Error("직접 확인 실패: " + status); }
await sleep(800);
await caption(`11월 ${new Date().getDate()}일 다시 확인: 같은 페이지의 위쪽 칸은 여전히 11.25, 본문은 11.06. 마감은 이미 지났습니다`);
await sleep(7000);

await go(`${BASE}/evidence`);
await caption("근거 자료: 표본 23건과 원문 주소, 원문과 다른 7건의 값, 화면 캡처, 시험 15건의 칸별 결과");
await sleep(3500);
await scrollTo(1400);
await sleep(3500);
await scrollTo(3200);
await sleep(3500);
await caption("AI가 근거를 찾고, 코드가 확인하고 판정합니다. 결과는 참고용이니 내기 전에 원문을 한 번 더 보세요");
await sleep(4000);

recording = false;
await recorder;
ws.close();
chrome.kill();

// ---- mp4 만들기
const lines = ["ffconcat version 1.0"];
frames.splice(0, startIdx);
for (let i = 0; i < frames.length; i++) {
  const fr = frames[i];
  let d = i + 1 < frames.length ? (frames[i + 1].t - fr.t) / 1000 : 2.0;
  if (fr.skip) d = 0.35;
  lines.push(`file '${fr.f}'`, `duration ${Math.max(0.04, d).toFixed(3)}`);
}
lines.push(`file '${frames[frames.length - 1].f}'`);
const list = path.join(WORK, "list.txt");
fs.writeFileSync(list, lines.join("\n"));
fs.mkdirSync(path.dirname(OUT), { recursive: true });
execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list,
  "-vf", "fps=25,format=yuv420p", "-c:v", "libx264", "-crf", "27", "-preset", "slow", "-movflags", "+faststart", OUT]);
console.log("frames", frames.length, "->", OUT);
