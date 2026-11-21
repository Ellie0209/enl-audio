/* Shadow & Shine Daily — PWA (no login, no server; progress stays on this device).
   Data: ../daily/index.json, ../daily/dNNN/scripts.json, audio + PDF in ../daily/l{lv}/dNNN/ */
"use strict";
const DATA = "../daily/";
const LEVELS = {
  1: { name: "Sprout", kr: "새싹", fs: "22px", solo: "목표 단어를 혼자 읽어요. 하나씩 눌러 들어 보고 따라 해요.", soloEn: "Read the target words by yourself." },
  2: { name: "Seedling", kr: "떡잎", fs: "19px", solo: "글을 보지 않고 처음 → 중간 → 끝으로 다시 말해요.", soloEn: "Retell the story: Beginning, Middle, End." },
  3: { name: "Sapling", kr: "묘목", fs: "17.5px", solo: "정확한 발음 · 쉼 · 강세로 스피치하듯 읽어요.", soloEn: "Read it like a speech with accurate sounds." },
  4: { name: "Tree", kr: "나무", fs: "16.5px", solo: "기억해서 전체 내용을 자세히 다시 말해요.", soloEn: "Retell the whole text from memory." },
};
const TRACKS = [
  { key: "1", label: "Normal", kr: "보통 · 쉐도잉" },
  { key: "slow", label: "Slow", kr: "천천히" },
  { key: "2", label: "Repeat", kr: "따라 말하기" },
];
const STEPS = [
  ["Listen ×2", "글을 보지 않고 Normal(또는 Slow)을 두 번 들어요."],
  ["Repeat", "Repeat 트랙의 쉼에서 한 덩어리씩 따라 말해요."],
  ["Shadow", "Normal을 틀고 글을 보며 동시에 말해요. / 에서 쉬고, 굵은 단어는 강하게!"],
  ["Solo", ""],
];
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pad = (n) => String(n).padStart(3, "0");

/* ---------- per-device storage (safe if blocked) ---------- */
const store = {
  get(k, d) { try { const v = localStorage.getItem("ssd:" + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("ssd:" + k, JSON.stringify(v)); } catch { /* private mode */ } },
};
const st = { lv: String(store.get("lv", "1")), acc: store.get("acc", "us"), index: null, cache: {} };
const progKey = (lv, day) => `p:${lv}-${day}`;
const getProg = (lv, day) => store.get(progKey(lv, day), { steps: [false, false, false, false], rec: false, best: 0 });
const setProg = (lv, day, p) => store.set(progKey(lv, day), p);
const starsOf = (p) => (p.steps.every(Boolean) ? 1 : 0) + (p.rec ? 1 : 0) + (p.best >= 80 ? 1 : 0);

/* ---------- data ---------- */
async function getJSON(url) {
  const r = await fetch(url, { cache: "no-cache" });
  if (!r.ok) throw new Error(r.status + " " + url);
  return r.json();
}
async function loadIndex() { st.index = await getJSON(DATA + "index.json"); return st.index; }
async function loadDay(day) {
  if (!st.cache[day]) st.cache[day] = await getJSON(`${DATA}d${pad(day)}/scripts.json`);
  return st.cache[day];
}
const levelFiles = (lv, day) => `${DATA}l${lv}/d${pad(day)}/`;
const pdfName = (lv, day) => `ShadowShine_Daily_D${pad(day)}_L${lv}_${LEVELS[lv].name}.pdf`;

/* ---------- text rendering ---------- */
function lineHTML(line) {
  return line.split(" | ").map((part) =>
    esc(part)
      .replace(/\*([^*]+)\*/g, "<b>$1</b>")
      .replace(/ ?↗/g, '&nbsp;<span class="arw" aria-label="올라가는 억양">↗</span>')
      .replace(/ ?↘/g, '&nbsp;<span class="arw" aria-label="내려가는 억양">↘</span>')
  ).join(' <span class="bar" aria-hidden="true">/</span> ');
}
const plain = (line) => line.replace(/\*/g, "").replace(/\s*[↗↘]/g, "").replace(/\s*\|\s*/g, " ").trim();

/* ---------- reading comparison (word alignment) ---------- */
const NUM = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split(" ");
const TENS = { 30: "thirty", 40: "forty", 50: "fifty", 60: "sixty", 70: "seventy", 80: "eighty", 90: "ninety", 100: "hundred" };
function numWord(n) {
  n = +n;
  if (n <= 20) return NUM[n];
  if (TENS[n]) return TENS[n];
  if (n < 100) return TENS[n - (n % 10)] + " " + NUM[n % 10];
  return String(n);
}
function tokens(text) {
  return text.toLowerCase()
    .replace(/[’‘]/g, "'").replace(/[“”"]/g, " ")
    .replace(/\d+/g, (m) => " " + numWord(m) + " ")
    .replace(/-/g, " ")
    .replace(/[^a-z' ]+/g, " ")
    .split(/\s+/).map((w) => w.replace(/^'+|'+$/g, "")).filter(Boolean);
}
function align(target, heard) {
  const n = target.length, m = heard.length;
  const dp = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  const same = (a, b) => a === b || a.replace(/'/g, "") === b.replace(/'/g, "") || (a.length > 3 && (a + "s" === b || b + "s" === a));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
    dp[i][j] = same(target[i], heard[j]) ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const ok = new Array(n).fill(false);
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (same(target[i], heard[j])) { ok[i] = true; i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) i++; else j++;
  }
  return ok;
}

/* ---------- audio helpers ---------- */
function stopAll() {
  document.querySelectorAll("audio").forEach((a) => a.pause());
  try { speechSynthesis.cancel(); } catch { }
}
function sayWord(w) {
  try {
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(w);
    u.lang = st.acc === "uk" ? "en-GB" : "en-US";
    u.rate = 0.8;
    speechSynthesis.speak(u);
  } catch { }
}

/* ---------- header ---------- */
function renderLevels() {
  const nav = $("#levels");
  nav.innerHTML = Object.entries(LEVELS).map(([lv, L]) =>
    `<button role="tab" data-lv="${lv}" aria-selected="${lv === st.lv}">L${lv} ${L.name}<small>${L.kr}</small></button>`).join("");
  nav.querySelectorAll("button").forEach((b) => b.onclick = () => {
    st.lv = b.dataset.lv; store.set("lv", st.lv);
    const m = location.hash.match(/d(\d+)/);
    location.hash = m ? `#/l${st.lv}/d${m[1]}` : `#/l${st.lv}`;
  });
  document.body.dataset.lv = st.lv;
  $("#acc").textContent = st.acc === "uk" ? "🇬🇧 UK" : "🇺🇸 US";
}
$("#acc").onclick = () => {
  st.acc = st.acc === "uk" ? "us" : "uk"; store.set("acc", st.acc);
  renderLevels();
  const a = $("#player");
  if (a) { const t = a.dataset.track; a.src = a.dataset.base + `${st.acc}-${t}.mp3`; }
};
$("#back").onclick = () => { location.hash = `#/l${st.lv}`; };

/* ---------- install banner ---------- */
let installEvt = null;
window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); installEvt = e; const b = $(".install"); if (b) showInstall(b); });
function showInstall(box) {
  const standalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone;
  if (standalone || store.get("installHidden", false)) return;
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
  if (installEvt) {
    box.innerHTML = `<span>📲 홈 화면에 앱으로 추가할 수 있어요.</span><button type="button">설치</button>`;
    box.querySelector("button").onclick = async () => { installEvt.prompt(); await installEvt.userChoice; installEvt = null; box.classList.remove("show"); };
    box.classList.add("show");
  } else if (ios) {
    box.innerHTML = `<span>📲 Safari 아래쪽 <b>공유</b> 버튼 → <b>홈 화면에 추가</b>를 누르면 앱처럼 쓸 수 있어요.</span><button type="button" aria-label="닫기">✕</button>`;
    box.querySelector("button").onclick = () => { store.set("installHidden", true); box.classList.remove("show"); };
    box.classList.add("show");
  }
}

/* ---------- list view ---------- */
async function showList() {
  $("#back").hidden = true;
  const main = $("#main");
  const idx = st.index || await loadIndex();
  const days = [...idx].sort((a, b) => b.day - a.day);
  const lv = st.lv, L = LEVELS[lv];
  main.innerHTML = `<div class="install"></div>
    <p class="intro">매일 새로운 지문 · Level ${lv} ${L.name} · 원어민 오디오로 듣고, 따라 하고, 녹음하고, 읽기 체크까지!</p>
    <ul class="days">${days.map((d, i) => {
      const s = d.levels[lv]; if (!s) return "";
      const stars = starsOf(getProg(lv, d.day));
      const date = new Date(d.date + "T00:00:00");
      return `<li><button class="day${i === 0 ? " new" : ""}" data-day="${d.day}">
        <span class="num"><small>DAY</small>${d.day}</span>
        <span class="t"><b>${esc(s.title)}</b><span>${date.getMonth() + 1}월 ${date.getDate()}일 · ${esc(s.genre)}${i === 0 ? " · 오늘의 지문" : ""}</span></span>
        <span class="stars" aria-label="별 ${stars}개">${"★".repeat(stars)}${"☆".repeat(3 - stars)}</span></button></li>`;
    }).join("")}</ul>`;
  main.querySelectorAll(".day").forEach((b) => b.onclick = () => { location.hash = `#/l${lv}/d${pad(b.dataset.day)}`; });
  showInstall($(".install", main));
}

/* ---------- day view ---------- */
let recState = null, liveState = null;
async function showDay(day) {
  $("#back").hidden = false;
  const main = $("#main");
  main.innerHTML = '<p class="loading">불러오는 중…</p>';
  const d = await loadDay(day);
  const lv = st.lv, L = LEVELS[lv], s = d.scripts[lv];
  if (!s) { main.innerHTML = '<p class="empty">이 레벨의 지문이 없어요.</p>'; return; }
  const base = levelFiles(lv, day);
  const p = getProg(lv, day);
  const steps = STEPS.map((x, i) => i === 3 ? [x[0], L.solo] : x);
  main.innerHTML = `
  <section class="head">
    <p class="meta">DAY ${d.day} · ${esc(d.date)} · Level ${lv} ${L.name}</p>
    <h1>${esc(s.title)}</h1><p class="kr">${esc(s.title_kr)} · ${esc(s.genre)}</p>
  </section>

  <section class="card">
    <h2><span class="n">1</span>듣기 · Listen</h2>
    <div class="seg" role="group" aria-label="트랙">${TRACKS.map((t, i) =>
      `<button type="button" data-t="${t.key}" aria-pressed="${i === 0}">${t.label}<small>${t.kr}</small></button>`).join("")}</div>
    <audio id="player" controls preload="none" data-base="${base}" data-track="1" src="${base}${st.acc}-1.mp3"></audio>
    <div class="row" style="margin-top:10px"><button type="button" class="btn ghost" id="toggleText">🙈 글 가리기</button></div>
    <div class="text" id="text" style="--fs:${L.fs}">${s.lines.map((l, i) => `<p class="line" data-i="${i}">${lineHTML(l)}</p>`).join("")}</div>
    <p class="legend"><b>/</b> 쉬기 · <b>굵은 글씨</b> 강하게 · ↗ 올라가는 억양 · ↘ 내려가는 억양</p>
  </section>

  <section class="card">
    <h2><span class="n">2</span>4단계 연습 · Steps</h2>
    <ul class="steps">${steps.map((x, i) => `<li><label><input type="checkbox" data-step="${i}" ${p.steps[i] ? "checked" : ""}>
      <span><b>${i + 1}. ${x[0]}</b><span>${esc(x[1])}</span></span></label></li>`).join("")}</ul>
    ${lv === "1" ? `<p class="hint" style="margin-top:10px">목표 단어 · 눌러서 들어 보세요</p><div class="targets">${s.targets.map((w) => `<button type="button" data-say="${esc(w)}">${esc(w)}</button>`).join("")}</div>` : ""}
    <div class="starrow" id="stars"></div>
  </section>

  <section class="card">
    <h2><span class="n">3</span>녹음해서 비교하기 · Record</h2>
    <p class="hint">내 목소리를 녹음하고 원어민 소리와 비교해요. 녹음은 이 기기에만 잠깐 남고 어디에도 올라가지 않아요.</p>
    <div class="row">
      <button type="button" class="btn rec" id="recBtn">● 녹음 시작</button>
      <button type="button" class="btn ghost" id="modelBtn">▶ 원어민 듣기</button>
    </div>
    <p class="status" id="recStatus" aria-live="polite"></p>
    <div class="mine" id="mine"></div>
  </section>

  <section class="card">
    <h2><span class="n">4</span>읽기 체크 · Feedback</h2>
    <p class="hint">시작을 누르고 글 전체를 소리 내어 읽은 뒤 <b>끝</b>을 눌러요. 잘 들린 단어는 초록, 다시 연습할 단어는 빨강으로 보여 줘요.</p>
    <div class="row">
      <button type="button" class="btn" id="liveBtn">🎤 읽기 체크 시작</button>
      <button type="button" class="btn ghost" id="liveEnd" disabled>■ 끝</button>
    </div>
    <p class="status" id="liveStatus" aria-live="polite"></p>
    <div class="result" id="result"></div>
    <p class="note">읽기 체크는 브라우저의 음성 인식 기능을 사용해요. Chrome 등 일부 브라우저는 인식을 위해 음성을 브라우저 회사 서버로 보낼 수 있어요. 이 앱은 음성이나 결과를 따로 저장하거나 보내지 않아요(최고 점수만 이 기기에 저장).</p>
  </section>

  <section class="card">
    <h2>📚 단어 · 소리 · 표현</h2>
    <details open><summary>Words · 단어 (${s.vocab.length})</summary>
      <table class="vocab">${s.vocab.map(([w, k]) => `<tr><td>${esc(w)} <button type="button" data-say="${esc(w)}" aria-label="${esc(w)} 듣기">🔊</button></td><td>${esc(k)}</td></tr>`).join("")}</table></details>
    <details><summary>Sound Tips · 소리 포인트</summary>${s.sounds.map(([n, ex, tip]) =>
      `<div class="sound"><b>${esc(n)}</b> <i>${esc(ex)}</i><p>${esc(tip)}</p></div>`).join("")}</details>
    <details><summary>Read Like a Pro · 표현 팁</summary><p>${esc(s.expression)}</p>
      <p class="hint">Practice: ${s.practice.map(esc).join(" · ")}</p></details>
  </section>

  <section class="card">
    <h2>🖨 워크시트</h2>
    <a class="pdf" href="${base}${pdfName(lv, day)}" target="_blank" rel="noopener" download>
      <span class="ic">PDF</span><span><b>${esc(pdfName(lv, day))}</b><br><span class="hint">쉐도잉 · 받아쓰기 · 정답 (A4)</span></span></a>
  </section>`;

  /* tracks */
  const player = $("#player");
  main.querySelectorAll(".seg button").forEach((b) => b.onclick = () => {
    main.querySelectorAll(".seg button").forEach((x) => x.setAttribute("aria-pressed", x === b));
    player.dataset.track = b.dataset.t;
    player.src = `${base}${st.acc}-${b.dataset.t}.mp3`;
    player.play().catch(() => { });
  });
  player.onerror = () => { $("#recStatus").textContent = ""; };
  $("#toggleText").onclick = (e) => {
    const t = $("#text"); const hid = t.classList.toggle("hidden-text");
    e.currentTarget.textContent = hid ? "👀 글 보기" : "🙈 글 가리기";
  };
  main.querySelectorAll("[data-say]").forEach((b) => b.onclick = () => sayWord(b.dataset.say));

  /* steps + stars */
  const paintStars = () => {
    const q = getProg(lv, day), n = starsOf(q);
    $("#stars").innerHTML = `${"★".repeat(n)}${"☆".repeat(3 - n)}<small>4단계 완료 · 녹음 · 읽기 체크 80%+${q.best ? ` (최고 ${q.best}%)` : ""}</small>`;
  };
  main.querySelectorAll("[data-step]").forEach((c) => c.onchange = () => {
    const q = getProg(lv, day); q.steps[+c.dataset.step] = c.checked; setProg(lv, day, q); paintStars();
  });
  paintStars();

  /* recording */
  $("#modelBtn").onclick = () => { stopAll(); const a = new Audio(`${base}${st.acc}-1.mp3`); a.play().catch(() => { }); recState && (recState.model = a); };
  $("#recBtn").onclick = () => toggleRecord(lv, day, paintStars);

  /* feedback */
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    $("#liveBtn").disabled = true;
    $("#liveStatus").textContent = "이 브라우저는 음성 인식을 지원하지 않아요. Chrome이나 Safari 최신 버전에서 써 주세요.";
  } else {
    $("#liveBtn").onclick = () => startLive(SR, s, lv, day, paintStars);
    $("#liveEnd").onclick = () => finishLive();
  }
}

async function toggleRecord(lv, day, paintStars) {
  const btn = $("#recBtn"), status = $("#recStatus");
  if (recState?.rec?.state === "recording") { recState.rec.stop(); return; }
  if (liveState) { status.textContent = "읽기 체크를 먼저 끝내 주세요."; return; }
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) { status.textContent = "이 기기에서는 녹음이 지원되지 않아요."; return; }
  stopAll();
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mime = ["audio/webm", "audio/mp4", "audio/ogg"].find((x) => MediaRecorder.isTypeSupported?.(x));
    const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    const chunks = [];
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    rec.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
      if (recState?.url) URL.revokeObjectURL(recState.url);
      const url = URL.createObjectURL(blob);
      recState = { url };
      btn.textContent = "● 다시 녹음"; btn.classList.add("rec");
      status.textContent = "녹음 완료! 원어민 소리와 번갈아 들어 보세요.";
      $("#mine").innerHTML = `<p class="hint" style="margin:0 0 4px">🎧 내 녹음</p><audio controls src="${url}"></audio>`;
      const q = getProg(lv, day); q.rec = true; setProg(lv, day, q); paintStars();
    };
    rec.start();
    recState = { ...(recState || {}), rec };
    btn.textContent = "■ 녹음 멈추기";
    status.textContent = "녹음 중… 글을 읽고 멈추기를 눌러요.";
  } catch {
    status.textContent = "마이크 사용을 허용해 주세요 (브라우저 주소창의 권한 설정).";
  }
}

function startLive(SR, s, lv, day, paintStars) {
  if (liveState) return;
  if (recState?.rec?.state === "recording") { $("#liveStatus").textContent = "녹음을 먼저 멈춰 주세요."; return; }
  stopAll();
  const r = new SR();
  r.lang = st.acc === "uk" ? "en-GB" : "en-US";
  r.continuous = true; r.interimResults = false; r.maxAlternatives = 1;
  liveState = { r, heard: [], start: performance.now(), s, lv, day, paintStars, active: true, firstSpeech: null, lastSpeech: null };
  r.onresult = (e) => {
    for (let i = e.resultIndex; i < e.results.length; i++)
      if (e.results[i].isFinal) liveState.heard.push(e.results[i][0].transcript);
    liveState.lastSpeech = performance.now();
    $("#liveStatus").textContent = `듣고 있어요… (${tokens(liveState.heard.join(" ")).length}단어)`;
  };
  r.onspeechstart = () => { if (liveState && !liveState.firstSpeech) liveState.firstSpeech = performance.now(); };
  r.onerror = (e) => {
    if (!liveState) return;
    if (e.error === "not-allowed" || e.error === "service-not-allowed") { liveState.active = false; $("#liveStatus").textContent = "마이크/음성 인식 사용을 허용해 주세요."; }
    if (e.error === "network") { liveState.active = false; $("#liveStatus").textContent = "음성 인식에 인터넷 연결이 필요해요."; }
  };
  r.onend = () => {
    if (liveState?.active) { try { r.start(); return; } catch { } }
    if (liveState?.finishing || (liveState && !liveState.active)) report();
  };
  try { r.start(); } catch { liveState = null; return; }
  $("#liveBtn").disabled = true; $("#liveEnd").disabled = false;
  $("#result").innerHTML = "";
  $("#liveStatus").textContent = "읽어 주세요! 다 읽으면 ■ 끝을 눌러요.";
}
function finishLive() {
  if (!liveState) return;
  liveState.active = false; liveState.finishing = true;
  $("#liveEnd").disabled = true;
  $("#liveStatus").textContent = "결과를 만드는 중…";
  try { liveState.r.stop(); } catch { report(); }
  setTimeout(() => liveState && report(), 2500);
}
function report() {
  const L = liveState; if (!L) return;
  liveState = null;
  try { L.r.abort(); } catch { }
  $("#liveBtn").disabled = false; $("#liveEnd").disabled = true;
  const { s, lv, day } = L;
  const heard = tokens(L.heard.join(" "));
  if (!heard.length) { $("#liveStatus").textContent = "소리가 들리지 않았어요. 마이크 가까이에서 다시 해 볼까요?"; return; }
  const lines = s.lines.map(plain);
  const words = lines.map((l) => ({ raw: l.split(/\s+/), tok: l.split(/\s+/).map((w) => tokens(w)) }));
  const flat = words.flatMap((w) => w.tok.flat());
  const ok = align(flat, heard);
  let k = 0, okCount = 0;
  const missed = new Set();
  const html = words.map((w) => w.raw.map((raw, i) => {
    const parts = w.tok[i]; if (!parts.length) return esc(raw);
    const good = ok.slice(k, k + parts.length).every(Boolean);
    k += parts.length;
    if (good) okCount++; else missed.add(parts.join(" "));
    return `<span class="w ${good ? "ok" : "miss"}">${esc(raw)}</span>`;
  }).join(" ")).join("<br>");
  const total = words.reduce((n, w) => n + w.tok.filter((t) => t.length).length, 0);
  const pct = Math.round((okCount / total) * 100);
  const secs = Math.max(1, ((L.lastSpeech || performance.now()) - (L.firstSpeech || L.start)) / 1000);
  const wpm = secs >= 3 ? Math.round(heard.length / (secs / 60)) : 0;
  const q = getProg(lv, day); q.best = Math.max(q.best || 0, pct); setProg(lv, day, q); L.paintStars();

  const tips = [];
  const missList = [...missed];
  const targetsMissed = s.targets.filter((t) => missList.includes(t.toLowerCase()));
  if (targetsMissed.length) tips.push(`목표 단어 <b>${targetsMissed.map(esc).join(", ")}</b> — 위의 Words에서 🔊로 듣고 다시 말해 봐요.`);
  for (const [name, ex, tip] of s.sounds) {
    const exs = tokens(ex);
    const hit = missList.find((m) => exs.includes(m));
    if (hit && tips.length < 4) tips.push(`<b>${esc(hit)}</b> · ${esc(name)}: ${esc(tip)}`);
  }
  const band = { 1: [70, 85], 2: [85, 105], 3: [105, 125], 4: [120, 145] }[lv];
  if (!wpm) { /* too short to measure speed */ }
  else if (wpm < band[0] - 15) tips.push("조금 더 자연스럽게 이어서 읽어 봐요. Shadow 단계로 원어민 속도를 따라가 보세요.");
  else if (wpm > band[1] + 25) tips.push("조금 천천히! / 에서 쉬고 굵은 단어를 또박또박 강하게 말해요.");
  const cheer = pct >= 90 ? "🌟 아주 잘했어요!" : pct >= 80 ? "👏 잘했어요! 빨간 단어만 다시 연습해요." : pct >= 60 ? "💪 좋아요! 빨간 단어를 연습하고 다시 도전!" : "🙂 천천히 한 줄씩 다시 읽어 봐요.";
  $("#liveStatus").textContent = cheer;
  $("#result").innerHTML = `<div class="score">
      <div><b>${pct}%</b><span>정확도</span></div>
      <div><b>${wpm || "–"}</b><span>WPM (권장 ${band[0]}–${band[1]})</span></div>
      <div><b>${okCount}/${total}</b><span>잘 들린 단어</span></div></div>
    <div class="words">${html}</div>
    ${tips.length ? `<ul class="tips">${tips.map((t) => `<li>${t}</li>`).join("")}</ul>` : ""}
    <p class="note">음성 인식은 완벽하지 않아요. 이름이나 잘 쓰지 않는 단어는 맞게 읽어도 빨강이 될 수 있어요 — 선생님 확인이 가장 정확해요.</p>`;
}

/* ---------- router ---------- */
async function route() {
  stopAll();
  if (liveState) { liveState.active = false; try { liveState.r.abort(); } catch { } liveState = null; }
  if (recState?.rec?.state === "recording") recState.rec.stop();
  const m = location.hash.match(/^#\/l([1-4])(?:\/d(\d+))?/);
  if (m) { st.lv = m[1]; store.set("lv", st.lv); }
  renderLevels();
  try {
    if (m && m[2]) await showDay(+m[2]); else await showList();
  } catch (e) {
    $("#main").innerHTML = `<p class="empty">불러오지 못했어요. 인터넷 연결을 확인하고 다시 열어 주세요.<br><small>${esc(e.message)}</small></p>`;
  }
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", route);
route();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => { });
