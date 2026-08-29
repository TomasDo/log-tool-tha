const $ = (id) => document.getElementById(id);

const LINE_H = 18;
const RULER_H = 28;
const MAX_SCALE = 2;
const TRACKS = [
  { key: "cases", name: "手术", h: 72 },
  { key: "log", name: "日志", h: 36 },
  { key: "l1", name: "一级", h: 42 },
  { key: "l2", name: "二级", h: 38 },
  { key: "l3", name: "三级", h: 34 },
  { key: "device", name: "设备", h: 32 },
];

const CASE_PALETTE = [
  "#3d8bff",
  "#ff8c42",
  "#e63956",
  "#2ec4b6",
  "#7b61ff",
  "#f4c430",
  "#ff5d8f",
  "#3ddc97",
  "#c77dff",
  "#ffb703",
];
const UNKNOWN_CASE_COLOR = "#6b7684";

const L1_COLOR = {
  方案预览: "#b07cff",
  设备准备: "#3d9bff",
  髋导航: "#2ed573",
  股骨导航: "#14b8a6",
  术后: "#ff9f1c",
};
const L2_COLOR = {
  安装髋标记钉: "#4da3ff",
  髋配准: "#89c4ff",
  髋臼打磨: "#22c55e",
  安装髋臼杯: "#8b5cf6",
  验证髋臼杯: "#f5d76e",
  安装股骨导航组件: "#38bdf8",
  安装股骨钉: "#12d4c4",
  股骨配准: "#7af0de",
  股骨截骨: "#fb923c",
};
const L3_COLOR = {
  配准稀疏采集: "#c084fc",
  配准密采集: "#818cf8",
  配准验证点: "#ffe066",
  杯验证点: "#f472b6",
};
const DEV_COLOR = {
  示踪器: "#2dd4bf",
  示教开关: "#94a3b8",
  急停: "#fb7185",
  KUKA: "#a3e635",
  MXIO: "#38bdf8",
  设备准备1: "#60a5fa",
  设备准备2: "#60a5fa",
  设备准备3: "#60a5fa",
  设备准备4: "#60a5fa",
  设备准备5: "#60a5fa",
};
const LOG_COLOR = {
  重点: "#e8b84a",
  异常: "#ff5c5c",
  噪声: "#5c6e82",
  启动: "#6ec89a",
};

const LEGEND = [
  {
    title: "手术",
    note: "不同手术轮换色，同 uuid 同色",
    swatches: CASE_PALETTE,
    items: [["未打开方案", UNKNOWN_CASE_COLOR]],
  },
  { title: "日志", items: Object.entries(LOG_COLOR) },
  { title: "一级", items: Object.entries(L1_COLOR) },
  {
    title: "二级",
    items: Object.entries(L2_COLOR),
  },
  { title: "三级", items: Object.entries(L3_COLOR) },
  { title: "设备", items: Object.entries(DEV_COLOR) },
];

const state = {
  logs: [],
  selected: null,
  data: null,
  playhead: 1,
  follow: true,
  scale: 1,
  scrollX: 0,
  viewLines: [],
  lineIndex: new Map(),
  progScroll: false,
  hits: [],
  drawQueued: false,
  drag: null,
};

function fmtRange(log) {
  const d = log.date || "日期未知";
  const a = log.start_time || "--:--:--";
  const b = log.end_time || "--:--:--";
  return `${d}  ${a} – ${b}`;
}

function fmtSize(n) {
  if (n == null) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

function clamp(v, a, b) {
  return Math.max(a, Math.min(b, v));
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

async function refreshSpec() {
  try {
    const s = await api("/api/spec");
    const c = s.counts || {};
    $("spec-info").textContent =
      `映射 ${c.mapping || 0} · 关键 ${c.key || 0} · 异常 ${c.anomaly || 0} · 噪声 ${c.noise || 0}`;
  } catch (e) {
    $("spec-info").textContent = "规则未加载";
  }
}

async function refreshLogs() {
  const data = await api("/api/logs");
  state.logs = data.logs || [];
  renderList();
}

function renderList() {
  const ul = $("file-list");
  ul.innerHTML = "";
  if (!state.logs.length) {
    ul.innerHTML = `<li style="cursor:default;opacity:.7">还没有导入的日志</li>`;
    return;
  }
  for (const log of state.logs) {
    const li = document.createElement("li");
    if (state.selected === log.id) li.classList.add("active");
    li.setAttribute("role", "button");
    li.tabIndex = 0;
    li.setAttribute("aria-pressed", state.selected === log.id ? "true" : "false");
    const counts = log.counts || {};
    li.innerHTML = `
      <button class="del" data-del="${log.id}" title="删除">删除</button>
      <div class="fname"></div>
      <div class="fmeta"><span></span><span></span></div>
      <div class="badges"></div>`;
    li.querySelector(".fname").textContent = log.original_name;
    li.querySelector(".fmeta span").textContent = fmtRange(log);
    li.querySelector(".fmeta span:last-child").textContent =
      `${log.line_count || 0} 行 · ${fmtSize(log.size)}`;
    const badges = li.querySelector(".badges");
    if (counts.key) {
      const b = document.createElement("span");
      b.className = "badge key";
      b.textContent = `重点 ${counts.key}`;
      badges.appendChild(b);
    }
    if (counts.anomaly) {
      const b = document.createElement("span");
      b.className = "badge anomaly";
      b.textContent = `异常 ${counts.anomaly}`;
      badges.appendChild(b);
    }
    li.addEventListener("click", (ev) => {
      if (ev.target.closest("[data-del]")) return;
      selectLog(log.id);
    });
    li.addEventListener("keydown", (ev) => {
      if (ev.target.closest("[data-del]")) return;
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        selectLog(log.id);
      }
    });
    li.querySelector("[data-del]").addEventListener("click", async (ev) => {
      ev.stopPropagation();
      if (!confirm(`删除 ${log.original_name} ？`)) return;
      await api(`/api/logs/${log.id}`, { method: "DELETE" });
      if (state.selected === log.id) {
        state.selected = null;
        state.data = null;
        $("timeline-wrap").hidden = true;
        $("empty-state").hidden = false;
      }
      await refreshLogs();
    });
    ul.appendChild(li);
  }
}

async function selectLog(id) {
  state.selected = id;
  renderList();
  await loadTimeline();
}

function lineVisible(ln) {
  if ($("tog-all").checked) return true;
  if (ln.special === "startup" || ln.special === "version") return true;
  if (ln.mark === "key" || ln.mark === "anomaly") return true;
  if ($("tog-noise").checked && ln.noise) return true;
  return false;
}

function rebuildViewLines() {
  const lines = (state.data && state.data.lines) || [];
  state.viewLines = lines.filter(lineVisible);
  state.lineIndex = new Map();
  state.viewLines.forEach((ln, i) => state.lineIndex.set(ln.n, i));
}

async function loadTimeline(opts) {
  if (!state.selected) return;
  $("empty-state").hidden = true;
  $("timeline-wrap").hidden = false;
  const term = $("term");
  if (!state.data) term.innerHTML = `<p class="hint" style="padding:12px">加载中…</p>`;
  const qs = new URLSearchParams();
  if (opts && opts.center) qs.set("center", String(opts.center));
  if (opts && opts.window) qs.set("window", String(opts.window));
  try {
    const data = await api(`/api/logs/${state.selected}/timeline?${qs.toString()}`);
    state.data = data;
    state.playhead = opts && opts.center ? opts.center : 1;
    state.follow = true;
    $("btn-follow").hidden = true;
    $("tl-title").textContent = data.name || "";
    const bits = [fmtRange(data)];
    if (data.date_source === "mtime") bits.push("日期取自文件时间");
    if (data.truncated) bits.push("事件已截断");
    if (data.lines_windowed) bits.push(`终端窗口 ${data.lines_start}–${data.lines_end}`);
    $("tl-meta").textContent = bits.join(" · ");
    renderCounts(data.counts || {});
    renderSummary(data.summaries || []);
    rebuildViewLines();
    renderLabels();
    fitZoom();
    renderTerm();
    scrollTermToPlayhead();
    queueDraw();
  } catch (e) {
    term.innerHTML = `<p class="err" style="padding:12px">${e.message}</p>`;
  }
}

function renderCounts(c) {
  $("counts").innerHTML = `
    <div class="count"><b>${c.total || 0}</b><span>总计</span></div>
    <div class="count k"><b>${c.key || 0}</b><span>重点</span></div>
    <div class="count a"><b>${c.anomaly || 0}</b><span>异常</span></div>
    <div class="count"><b>${c.hidden_noise || 0}</b><span>噪声</span></div>`;
  const extra = [];
  extra.push(`${state.data.line_count || 0} 行`);
  if (c.unmatched) extra.push(`未映射 ${c.unmatched}`);
  $("return-count").textContent = extra.join(" · ");
}

function renderSummary(summaries) {
  const wrap = $("plan-summary-wrap");
  const el = $("plan-summary");
  if (!wrap || !el) return;
  wrap.hidden = false;
  const items = summaries || [];
  el.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "ps-empty";
    empty.textContent = "暂无手术方案";
    el.append(empty);
    return;
  }
  for (const s of items) el.append(summaryCard(s));
}

function summaryCard(s) {
  const card = document.createElement("div");
  card.className = "ps-card";
  card.style.borderLeftColor = s.color || UNKNOWN_CASE_COLOR;
  const title = document.createElement("div");
  title.className = "ps-title";
  title.textContent = s.label || `手术${s.case_n || ""}`;
  const uid = document.createElement("div");
  uid.className = "ps-uuid";
  const full = s.uuid || "";
  uid.textContent = full.slice(0, 8);
  uid.title = full;
  card.append(title, uid);
  if (!s.started) {
    const idle = document.createElement("div");
    idle.className = "ps-idle";
    idle.textContent = "未开始手术";
    card.append(idle);
  } else {
    for (const st of s.steps || []) card.append(summaryStep(st));
  }
  card.addEventListener("click", () => setPlayhead(s.start || 1));
  return card;
}

function jumpLine(ev, n) {
  if (!n) return;
  ev.stopPropagation();
  setPlayhead(n);
}

function summaryStep(st) {
  const wrap = document.createElement("div");
  wrap.className = "ps-step " + (st.ok ? "ok" : "bad");
  const hd = document.createElement("div");
  hd.className = "ps-hd";
  const mark = document.createElement("span");
  mark.className = "ps-mark";
  mark.textContent = st.ok ? "✓" : "×";
  const body = document.createElement("div");
  const name = document.createElement("span");
  name.textContent = st.name;
  body.append(name);
  if (!st.ok && !(st.planes && st.planes.length)) {
    const d = document.createElement("span");
    d.className = "ps-detail";
    d.textContent = " " + (st.missing_detail || "未做");
    body.append(d);
  }
  if (st.points && st.points.length) {
    hd.title = "点 " + st.points.join(",");
  }
  hd.append(mark, body);
  wrap.append(hd);
  if (st.line) hd.addEventListener("click", (ev) => jumpLine(ev, st.line));
  const planes = st.planes || [];
  if (planes.length) {
    const box = document.createElement("div");
    box.className = "ps-planes";
    for (const p of planes) box.append(summaryPlane(p));
    wrap.append(box);
  }
  return wrap;
}

function summaryPlane(p) {
  const row = document.createElement("div");
  row.className = "ps-plane " + (p.ok ? "ok" : "bad");
  const mark = p.ok ? "✓ " : "× ";
  let text = mark + p.name;
  if (!p.ok) {
    if (p.touched && p.missing && p.missing.length) {
      text += " 未做完 · " + p.missing.join("、") + " 未采集";
    } else {
      text += " " + (p.missing_detail || "未做");
    }
  }
  row.textContent = text;
  if (p.line) row.addEventListener("click", (ev) => jumpLine(ev, p.line));
  return row;
}

function renderLabels() {
  const labs = $("nle-labels");
  const rows = [{ name: "行号", h: RULER_H, ruler: true }, ...TRACKS];
  labs.innerHTML = rows
    .map(
      (r) =>
        `<div class="nle-lab${r.ruler ? " ruler" : ""}" style="height:${r.h}px">${r.name}</div>`
    )
    .join("");
  renderLegend();
}

function renderLegend() {
  const el = $("nle-legend");
  if (!el) return;
  el.innerHTML = LEGEND.map((g) => {
    const dots = (g.swatches || [])
      .map((c) => `<i class="lg-swatch" style="background:${c}"></i>`)
      .join("");
    const items = (g.items || [])
      .map(
        ([name, col]) =>
          `<div class="lg-item"><i class="lg-dot" style="background:${col}"></i><span>${name}</span></div>`
      )
      .join("");
    const note = g.note ? `<p class="lg-note">${g.note}</p>` : "";
    const extra = dots ? `<div class="lg-swatches">${dots}</div>` : "";
    return `<section class="lg-group"><h3>${g.title}</h3>${note}${extra}${items}</section>`;
  }).join("");
}

function lineCount() {
  return (state.data && state.data.line_count) || 1;
}

function canvasSize(cv) {
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth;
  const h = cv.clientHeight;
  const pw = Math.max(1, Math.floor(w * dpr));
  const ph = Math.max(1, Math.floor(h * dpr));
  if (cv.width !== pw || cv.height !== ph) {
    cv.width = pw;
    cv.height = ph;
  }
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { w, h, ctx };
}

function minScale() {
  const cv = $("nle-canvas");
  const w = cv.clientWidth || 800;
  return Math.min(MAX_SCALE, w / Math.max(1, lineCount()));
}

function maxScroll() {
  const cv = $("nle-canvas");
  const w = cv.clientWidth || 800;
  return Math.max(0, lineCount() * state.scale - w);
}

function fitZoom() {
  state.scale = minScale();
  state.scrollX = 0;
}

function xOfLine(n) {
  return (n - 1) * state.scale - state.scrollX;
}

function lineAtX(x) {
  return clamp(Math.floor((x + state.scrollX) / state.scale) + 1, 1, lineCount());
}

function trackLayout() {
  let y = RULER_H;
  return TRACKS.map((t) => {
    const rec = { key: t.key, name: t.name, h: t.h, y };
    y += t.h;
    return rec;
  });
}

function spanRect(span) {
  const x = xOfLine(span.start);
  const w = Math.max(2, (span.end - span.start + 1) * state.scale);
  return { x, w };
}

function uniqueStartups(markers) {
  const out = [];
  for (const m of markers || []) {
    if (m.kind !== "startup") continue;
    const last = out[out.length - 1];
    if (last && m.line - last.line <= 8) {
      if (m.version && !last.version) {
        last.version = m.version;
        last.version_line = m.version_line;
      }
      continue;
    }
    out.push({ ...m });
  }
  for (const s of (state.data.tracks && state.data.tracks.sessions) || []) {
    if (!s.version) continue;
    const pin = out.find((p) => Math.abs(p.line - s.start) <= 8);
    if (pin && !pin.version) {
      pin.version = s.version;
      pin.version_line = s.version_line;
    }
  }
  return out;
}

function roundRect(ctx, x, y, w, h, r) {
  const rr = Math.min(r, h / 2, w / 2);
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.arcTo(x + w, y, x + w, y + h, rr);
  ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr);
  ctx.arcTo(x, y, x + w, y, rr);
  ctx.closePath();
}

function drawFlag(ctx, x, y, version) {
  ctx.save();
  ctx.fillStyle = "#6ec89a";
  ctx.beginPath();
  ctx.moveTo(x, y);
  ctx.lineTo(x + 11, y + 6);
  ctx.lineTo(x, y + 12);
  ctx.closePath();
  ctx.fill();
  ctx.strokeStyle = "#1a3a2a";
  ctx.lineWidth = 1;
  ctx.stroke();
  if (version) {
    ctx.font = "10px ui-sans-serif, sans-serif";
    const tw = Math.ceil(ctx.measureText(version).width) + 8;
    let bx = x + 13;
    const vw = $("nle-canvas").clientWidth;
    if (bx + tw > vw - 4) {
      bx = x > vw * 0.55 ? x - tw - 4 : Math.max(0, vw - tw - 4);
    }
    ctx.fillStyle = "#163328";
    roundRect(ctx, bx, y, tw, 13, 3);
    ctx.fill();
    ctx.strokeStyle = "#6ec89a";
    ctx.stroke();
    ctx.fillStyle = "#b8f0d0";
    ctx.fillText(version, bx + 4, y + 10);
    ctx.restore();
    return { x: Math.min(x, bx), y, w: Math.abs(bx - x) + tw + 11, h: 13 };
  }
  ctx.restore();
  return { x, y, w: 12, h: 12 };
}

function drawPlayhead(ctx, h) {
  const x = xOfLine(state.playhead) + state.scale * 0.5;
  ctx.save();
  ctx.strokeStyle = "rgba(255,255,255,0.85)";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(x, 0);
  ctx.lineTo(x, h);
  ctx.stroke();
  ctx.strokeStyle = "#ff4d4d";
  ctx.lineWidth = 1.5;
  ctx.stroke();
  ctx.fillStyle = "#ff4d4d";
  ctx.beginPath();
  ctx.moveTo(x - 6, 0);
  ctx.lineTo(x + 6, 0);
  ctx.lineTo(x, 10);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

function drawTicks(ctx, y, h, w) {
  const n = lineCount();
  const ticks = (state.data && state.data.ticks) || { key: [], anomaly: [] };
  const keySet = new Set(ticks.key || []);
  const anomSet = new Set(ticks.anomaly || []);
  const showDim = $("tog-all").checked;
  if (state.scale >= 1.15) {
    const a = lineAtX(0);
    const b = lineAtX(w);
    for (let i = a; i <= b; i++) {
      const x = xOfLine(i);
      let color = null;
      if (anomSet.has(i)) color = LOG_COLOR.异常;
      else if (keySet.has(i)) color = LOG_COLOR.重点;
      else if (showDim) color = "rgba(90,110,130,0.45)";
      if (!color) continue;
      ctx.fillStyle = color;
      ctx.fillRect(x, y + 4, Math.max(1, state.scale * 0.7), h - 8);
    }
    return;
  }
  for (let px = 0; px < w; px++) {
    const a = lineAtX(px);
    const b = lineAtX(px + 1);
    let anom = false;
    let key = false;
    for (let i = a; i <= b; i++) {
      if (anomSet.has(i)) {
        anom = true;
        break;
      }
      if (keySet.has(i)) key = true;
    }
    if (anom) ctx.fillStyle = LOG_COLOR.异常;
    else if (key) ctx.fillStyle = LOG_COLOR.重点;
    else if (showDim) ctx.fillStyle = "rgba(90,110,130,0.28)";
    else continue;
    ctx.fillRect(px, y + 5, 1, h - 10);
  }
}

function ellipsize(ctx, text, maxW) {
  const t = text || "";
  if (maxW <= 0) return "";
  if (ctx.measureText(t).width <= maxW) return t;
  const ell = "…";
  let lo = 0;
  let hi = t.length;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    if (ctx.measureText(t.slice(0, mid) + ell).width <= maxW) lo = mid;
    else hi = mid - 1;
  }
  return lo ? t.slice(0, lo) + ell : "";
}

function drawSpans(ctx, spans, y, h, colorFn, trackKey) {
  for (const s of spans || []) {
    const { x, w } = spanRect(s);
    if (x + w < 0 || x > ctx.canvas.clientWidth) continue;
    const col = colorFn(s) || "#4a6078";
    ctx.fillStyle = col;
    roundRect(ctx, x, y + 4, w, h - 8, 3);
    ctx.fill();
    ctx.fillStyle = "rgba(0,0,0,0.18)";
    ctx.fillRect(x, y + 4, Math.min(2, w), h - 8);
    if (w >= 28) {
      ctx.save();
      ctx.beginPath();
      ctx.rect(x + 4, y + 4, w - 8, h - 8);
      ctx.clip();
      ctx.fillStyle = "rgba(255,255,255,0.92)";
      ctx.font = "12px ui-sans-serif, sans-serif";
      ctx.fillText(ellipsize(ctx, s.label || "", w - 10), x + 6, y + h / 2 + 4);
      ctx.restore();
    }
    state.hits.push({
      type: "span",
      track: trackKey,
      span: s,
      x,
      y: y + 4,
      w,
      h: h - 8,
    });
  }
}

function fullCaseLabel(s) {
  if (!s.uuid) return "未打开方案";
  if (s.restart) return `#${s.n} 重启`;
  return s.case_label || s.label || "手术";
}

function compactCaseLabel(s) {
  if (!s.uuid) return "未开";
  if (s.restart) return `#${s.n}`;
  const n = s.case_n || s.n;
  return n ? `手术${n}` : "手术";
}

function pickCaseLabel(ctx, s, maxW) {
  if (maxW < 10) return "";
  const full = fullCaseLabel(s);
  if (ctx.measureText(full).width <= maxW) return full;
  const compact = compactCaseLabel(s);
  if (ctx.measureText(compact).width <= maxW) return compact;
  return ellipsize(ctx, compact, maxW);
}

function drawCases(ctx, y, h, w) {
  const sessions = ((state.data && state.data.tracks) || {}).sessions || [];
  const labelH = 18;
  const barY = y + labelH + 1;
  const barH = Math.max(10, h - labelH - 6);
  ctx.font = "12px ui-sans-serif, sans-serif";
  for (let i = 0; i < sessions.length; i++) {
    const s = sessions[i];
    const x = xOfLine(s.start);
    const endX = xOfLine(s.end + 1);
    const nextX = i + 1 < sessions.length ? xOfLine(sessions[i + 1].start) : w + 8;
    let barW = Math.max(3, endX - x);
    if (x + barW > nextX - 1) barW = Math.max(2, nextX - 1 - x);
    if (x + barW < 0 || x > w) continue;
    const col = s.color || (s.uuid ? "#4e79a7" : "#5a6570");
    ctx.fillStyle = col;
    roundRect(ctx, x, barY, barW, barH, 3);
    ctx.fill();
    if (!s.uuid) {
      ctx.fillStyle = "rgba(255,255,255,0.12)";
      for (let px = x; px < x + barW; px += 4) {
        ctx.fillRect(px, barY, 1.5, barH);
      }
    }
    ctx.fillStyle = "rgba(14,20,27,0.85)";
    ctx.fillRect(x + barW - 1, barY, 1, barH);
    state.hits.push({
      type: "span",
      track: "cases",
      span: s,
      x,
      y: barY,
      w: barW,
      h: barH,
    });
  }
  let prevEnd = -1e9;
  for (let i = 0; i < sessions.length; i++) {
    const s = sessions[i];
    const x = Math.max(0, xOfLine(s.start));
    const nextX = i + 1 < sessions.length ? xOfLine(sessions[i + 1].start) : w;
    const maxW = Math.max(0, Math.min(nextX, w) - x - 3);
    if (maxW < 10 || x + 2 < prevEnd) continue;
    const label = pickCaseLabel(ctx, s, maxW);
    if (!label) continue;
    ctx.fillStyle = "rgba(230,238,246,0.92)";
    ctx.fillText(label, x + 1, y + 12);
    prevEnd = x + 1 + ctx.measureText(label).width;
  }
}

function drawRuler(ctx, w) {
  ctx.fillStyle = "#101820";
  ctx.fillRect(0, 0, w, RULER_H);
  ctx.fillStyle = "#6a7c90";
  ctx.font = "10px ui-sans-serif, sans-serif";
  const n = lineCount();
  const target = 80;
  const linesPer = Math.max(1, Math.round(target / state.scale));
  const step = niceStep(linesPer);
  const a = lineAtX(0);
  const b = lineAtX(w);
  const start = Math.floor(a / step) * step;
  for (let i = Math.max(1, start); i <= b; i += step) {
    const x = xOfLine(i);
    ctx.fillStyle = "#3a516c";
    ctx.fillRect(x, RULER_H - 6, 1, 6);
    ctx.fillStyle = "#8a9bb0";
    ctx.fillText(String(i), x + 3, 12);
  }
  void n;
}

function niceStep(n) {
  const p = Math.pow(10, Math.floor(Math.log10(Math.max(1, n))));
  const m = n / p;
  if (m <= 1) return p;
  if (m <= 2) return 2 * p;
  if (m <= 5) return 5 * p;
  return 10 * p;
}

function drawNle() {
  const data = state.data;
  if (!data) return;
  const cv = $("nle-canvas");
  const { w, h, ctx } = canvasSize(cv);
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#121a22";
  ctx.fillRect(0, 0, w, h);
  state.hits = [];
  const layout = trackLayout();
  drawRuler(ctx, w);
  ctx.strokeStyle = "#1b2733";
  ctx.lineWidth = 1;
  for (const t of layout) {
    ctx.beginPath();
    ctx.moveTo(0, t.y);
    ctx.lineTo(w, t.y);
    ctx.stroke();
  }
  const tracks = data.tracks || {};
  const byKey = Object.fromEntries(layout.map((t) => [t.key, t]));
  drawCases(ctx, byKey.cases.y, byKey.cases.h, w);
  drawTicks(ctx, byKey.log.y, byKey.log.h, w);
  drawSpans(ctx, tracks.l1, byKey.l1.y, byKey.l1.h, (s) => L1_COLOR[s.label], "l1");
  drawSpans(ctx, tracks.l2, byKey.l2.y, byKey.l2.h, (s) => L2_COLOR[s.label] || "#5aa6e8", "l2");
  drawSpans(ctx, tracks.l3, byKey.l3.y, byKey.l3.h, (s) => L3_COLOR[s.label] || "#e07070", "l3");
  if (byKey.device) {
    drawSpans(ctx, tracks.device, byKey.device.y, byKey.device.h, (s) => DEV_COLOR[s.label] || "#6a7c8f", "device");
  }

  // exit markers: thin dim line
  for (const m of tracks.markers || []) {
    if (m.kind !== "exit") continue;
    const x = xOfLine(m.line) + state.scale * 0.5;
    ctx.strokeStyle = "rgba(227,93,93,0.45)";
    ctx.setLineDash([2, 3]);
    ctx.beginPath();
    ctx.moveTo(x, RULER_H);
    ctx.lineTo(x, h);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  const pins = uniqueStartups(tracks.markers).slice().sort((a, b) => a.line - b.line);
  let badgeRight = -1e9;
  ctx.font = "10px ui-sans-serif, sans-serif";
  for (const pin of pins) {
    const x = xOfLine(pin.line) + state.scale * 0.5;
    ctx.strokeStyle = "rgba(110,200,154,0.7)";
    ctx.lineWidth = 1.25;
    ctx.setLineDash([3, 2]);
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
    ctx.stroke();
    ctx.setLineDash([]);
    let ver = pin.version || "";
    let right = x + 12;
    if (ver) {
      const tw = Math.ceil(ctx.measureText(ver).width) + 8;
      const bx = x + 13;
      if (bx < badgeRight + 8) ver = "";
      else right = bx + tw;
    }
    const r1 = drawFlag(ctx, x, 2, ver);
    if (ver) badgeRight = right;
    state.hits.push({ type: "pin", pin, ...r1 });
  }

  drawPlayhead(ctx, h);
  updatePlayInfo();
  drawOverview();
}

function drawOverview() {
  const cv = $("overview");
  const data = state.data;
  if (!data) return;
  const { w, h, ctx } = canvasSize(cv);
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#0c1218";
  ctx.fillRect(0, 0, w, h);
  const n = lineCount();
  const px = (line) => ((line - 1) / n) * w;
  for (const c of (data.tracks && data.tracks.cases) || []) {
    ctx.fillStyle = c.color || "#4e79a7";
    ctx.globalAlpha = 0.55;
    ctx.fillRect(px(c.start), 4, Math.max(2, px(c.end + 1) - px(c.start)), h - 8);
    ctx.globalAlpha = 1;
  }
  const viewW = $("nle-canvas").clientWidth || w;
  const x0 = (state.scrollX / (n * state.scale)) * w;
  const x1 = ((state.scrollX + viewW) / (n * state.scale)) * w;
  ctx.strokeStyle = "rgba(255,255,255,0.7)";
  ctx.strokeRect(x0, 1, Math.max(2, x1 - x0), h - 2);
  const ph = px(state.playhead);
  ctx.fillStyle = "#ff4d4d";
  ctx.fillRect(ph, 0, 2, h);
  for (const m of (data.tracks && data.tracks.markers) || []) {
    if (m.kind !== "startup") continue;
    ctx.fillStyle = "#6ec89a";
    ctx.fillRect(px(m.line), 1, 2, h - 2);
  }
}

function queueDraw() {
  if (state.drawQueued) return;
  state.drawQueued = true;
  requestAnimationFrame(() => {
    state.drawQueued = false;
    drawNle();
  });
}

function timeOfLine(n) {
  const lines = (state.data && state.data.lines) || [];
  if (!lines.length) return "";
  const first = lines[0].n;
  const ln = lines[n - first];
  if (ln && ln.n === n) return ln.t || "";
  let best = "";
  for (const l of lines) {
    if (l.n > n) break;
    if (l.t) best = l.t;
  }
  return best;
}

function updatePlayInfo() {
  const el = $("play-info");
  if (!el || !state.data) return;
  const t = timeOfLine(state.playhead);
  el.textContent = `行 ${state.playhead} / ${lineCount()}` + (t ? `  ${t}` : "");
}

async function setPlayhead(n, fromTerm) {
  const next = clamp(n | 0, 1, lineCount());
  const changed = next !== state.playhead;
  state.playhead = next;
  if (state.data && state.data.lines_windowed) {
    if (next < state.data.lines_start || next > state.data.lines_end) {
      await loadTimeline({ center: next });
      return;
    }
  }
  if (state.follow && !fromTerm) scrollTermToPlayhead();
  else renderTerm();
  queueDraw();
  void changed;
}

function scrollTermToPlayhead() {
  const term = $("term");
  const idx = state.lineIndex.has(state.playhead)
    ? state.lineIndex.get(state.playhead)
    : state.viewLines.findIndex((l) => l.n >= state.playhead);
  if (idx < 0) {
    renderTerm();
    return;
  }
  const y = idx * LINE_H - term.clientHeight * 0.35;
  state.progScroll = true;
  term.scrollTop = Math.max(0, y);
  renderTerm();
  requestAnimationFrame(() => {
    state.progScroll = false;
  });
}

function renderTerm() {
  const term = $("term");
  const lines = state.viewLines;
  if (!state.data) return;
  let spacer = term.querySelector("#term-spacer");
  if (!spacer) {
    term.innerHTML = "";
    spacer = document.createElement("div");
    spacer.id = "term-spacer";
    term.appendChild(spacer);
  }
  spacer.style.height = `${Math.max(lines.length, 1) * LINE_H}px`;
  const y = term.scrollTop;
  const vh = term.clientHeight || 200;
  const start = Math.max(0, Math.floor(y / LINE_H) - 6);
  const end = Math.min(lines.length, Math.ceil((y + vh) / LINE_H) + 6);
  const keep = new Set();
  for (let i = start; i < end; i++) keep.add(String(lines[i].n));
  for (const node of [...spacer.children]) {
    if (!keep.has(node.dataset.n)) node.remove();
  }
  const have = new Set([...spacer.children].map((n) => n.dataset.n));
  for (let i = start; i < end; i++) {
    const ln = lines[i];
    const id = String(ln.n);
    let el = have.has(id)
      ? spacer.querySelector(`[data-n="${id}"]`)
      : null;
    if (!el) {
      el = document.createElement("div");
      el.dataset.n = id;
      el.innerHTML = `<span class="tn"></span><span class="tt"></span><span class="tlv"></span><span class="traw"></span>`;
      el.addEventListener("click", () => {
        state.follow = true;
        $("btn-follow").hidden = true;
        setPlayhead(ln.n, true);
        scrollTermToPlayhead();
      });
      spacer.appendChild(el);
    }
    el.style.top = `${i * LINE_H}px`;
    const cls = ["tline"];
    if (ln.n === state.playhead) cls.push("play");
    if (ln.special === "startup") cls.push("startup");
    else if (ln.special === "version") cls.push("version");
    if (ln.mark === "key") cls.push("key");
    if (ln.mark === "anomaly") cls.push("anomaly");
    if (ln.noise) cls.push("noise");
    el.className = cls.join(" ");
    el.querySelector(".tn").textContent = ln.n;
    el.querySelector(".tt").textContent = ln.t || "";
    const lv = el.querySelector(".tlv");
    lv.textContent = ln.lv || "";
    lv.className = "tlv" + (ln.lv ? ` lv-${ln.lv}` : "");
    el.querySelector(".traw").textContent = ln.raw || "";
  }
}

function hitAt(mx, my) {
  for (let i = state.hits.length - 1; i >= 0; i--) {
    const h = state.hits[i];
    if (mx >= h.x && mx <= h.x + h.w && my >= h.y && my <= h.y + h.h) return h;
  }
  return null;
}

function tipHtml(hit) {
  if (!hit) return "";
  if (hit.type === "pin") {
    const p = hit.pin;
    return `启动${p.version ? "  " + p.version : ""}\n行 ${p.line}` + (p.t ? `  ${p.t}` : "");
  }
  const s = hit.span;
  const name = hit.track === "cases" ? fullCaseLabel(s) : s.label;
  let out = `${name}\n行 ${s.start}–${s.end}`;
  if (s.t0) out += `\n${s.t0} – ${s.t1 || ""}`;
  const errs = s.errors || [];
  if (errs.length) {
    for (const e of errs) {
      const flag = e.over ? "  >1mm" : "";
      out += `\n${e.label}  ${Number(e.value).toFixed(2)} mm${flag}`;
    }
    if (s.error_max != null) out += `\n最大  ${Number(s.error_max).toFixed(2)} mm`;
  }
  const cuts = s.cut_deltas || [];
  if (cuts.length) {
    for (const c of cuts) {
      if (c.missing) {
        out += `\n${c.label}  未采集  标注`;
        continue;
      }
      const unit = c.unit === "mm" ? "mm" : "°";
      const flag = c.over2 ? "  重点" : c.over1 ? "  标注" : "";
      if (c.plan == null || c.delta == null || c.measured == null) {
        const meas = c.measured != null ? Number(c.measured).toFixed(2) : "—";
        out += `\n${c.label}  实测 ${meas} ${unit}${flag}`;
        continue;
      }
      const d = Number(c.delta);
      const dstr = (d >= 0 ? "+" : "") + d.toFixed(2);
      out += `\n${c.label}  目标 ${Number(c.plan).toFixed(2)}  实测 ${Number(c.measured).toFixed(2)}  Δ ${dstr} ${unit}${flag}`;
    }
  }
  return out;
}

function bindNle() {
  const cv = $("nle-canvas");
  const ov = $("overview");
  const tip = $("nle-tip");

  cv.addEventListener("wheel", (ev) => {
    if (!state.data) return;
    ev.preventDefault();
    const dx = ev.deltaX || ev.deltaY;
    state.scrollX = clamp(state.scrollX + dx, 0, maxScroll());
    queueDraw();
  }, { passive: false });

  cv.addEventListener("pointerdown", (ev) => {
    if (!state.data) return;
    cv.setPointerCapture(ev.pointerId);
    const rect = cv.getBoundingClientRect();
    const x = ev.clientX - rect.left;
    const y = ev.clientY - rect.top;
    cv.classList.add("dragging");
    state.drag = {
      kind: "pan",
      x0: x,
      y0: y,
      sx: state.scrollX,
      moved: false,
      hit: hitAt(x, y),
    };
  });

  cv.addEventListener("pointermove", (ev) => {
    const rect = cv.getBoundingClientRect();
    const x = ev.clientX - rect.left;
    const y = ev.clientY - rect.top;
    if (state.drag) {
      const dx = x - state.drag.x0;
      if (Math.abs(dx) > 3) state.drag.moved = true;
      state.scrollX = clamp(state.drag.sx - dx, 0, maxScroll());
      queueDraw();
      tip.hidden = true;
      return;
    }
    const hit = hitAt(x, y);
    if (hit) {
      tip.hidden = false;
      tip.textContent = tipHtml(hit);
      const box = $("nle").getBoundingClientRect();
      tip.style.left = `${ev.clientX - box.left + 12}px`;
      tip.style.top = `${ev.clientY - box.top + 12}px`;
      cv.style.cursor = "pointer";
    } else {
      tip.hidden = true;
      cv.style.cursor = "grab";
    }
  });

  function endDrag(ev) {
    if (!state.drag) return;
    const rect = cv.getBoundingClientRect();
    const x = ev.clientX - rect.left;
    const y = ev.clientY - rect.top;
    const d = state.drag;
    state.drag = null;
    cv.classList.remove("dragging");
    if (!d.moved) {
      if (d.hit && d.hit.type === "span") setPlayhead(d.hit.span.start);
      else if (d.hit && d.hit.type === "pin") setPlayhead(d.hit.pin.line);
      else setPlayhead(lineAtX(x));
    }
    void y;
  }
  cv.addEventListener("pointerup", endDrag);
  cv.addEventListener("pointercancel", () => {
    state.drag = null;
    cv.classList.remove("dragging");
  });

  ov.addEventListener("pointerdown", (ev) => {
    if (!state.data) return;
    ov.setPointerCapture(ev.pointerId);
    const seek = (e) => {
      const r = ov.getBoundingClientRect();
      const t = clamp((e.clientX - r.left) / r.width, 0, 1);
      setPlayhead(Math.round(t * (lineCount() - 1)) + 1);
      const viewW = $("nle-canvas").clientWidth || r.width;
      const x = (state.playhead - 1) * state.scale;
      state.scrollX = clamp(x - viewW / 2, 0, maxScroll());
      queueDraw();
    };
    state.drag = { kind: "overview" };
    seek(ev);
    const move = (e) => seek(e);
    const up = () => {
      ov.removeEventListener("pointermove", move);
      ov.removeEventListener("pointerup", up);
      state.drag = null;
    };
    ov.addEventListener("pointermove", move);
    ov.addEventListener("pointerup", up);
  });

  $("btn-zoom-in").addEventListener("click", () => {
    const cvw = $("nle-canvas").clientWidth / 2;
    const line = (cvw + state.scrollX) / state.scale;
    state.scale = clamp(state.scale * 1.25, minScale(), MAX_SCALE);
    state.scrollX = clamp(line * state.scale - cvw, 0, maxScroll());
    queueDraw();
  });
  $("btn-zoom-out").addEventListener("click", () => {
    const cvw = $("nle-canvas").clientWidth / 2;
    const line = (cvw + state.scrollX) / state.scale;
    state.scale = clamp(state.scale / 1.25, minScale(), MAX_SCALE);
    state.scrollX = clamp(line * state.scale - cvw, 0, maxScroll());
    queueDraw();
  });
  $("btn-zoom-fit").addEventListener("click", () => {
    fitZoom();
    queueDraw();
  });
}

function bindTerm() {
  const term = $("term");
  term.addEventListener("scroll", () => {
    if (state.progScroll) {
      renderTerm();
      return;
    }
    if (state.follow) {
      state.follow = false;
      $("btn-follow").hidden = false;
    }
    renderTerm();
  });
  $("btn-follow").addEventListener("click", () => {
    state.follow = true;
    $("btn-follow").hidden = true;
    scrollTermToPlayhead();
  });
}

function bindSplit() {
  const split = $("split");
  const term = $("term-wrap");
  const workspace = $("workspace");
  const nle = $("nle");
  const applyTermH = (h) => {
    nle.style.flex = "";
    nle.style.height = "";
    term.style.flex = `0 0 ${h}px`;
    term.style.height = `${h}px`;
    queueDraw();
  };
  const maxTerm = () => {
    const ws = workspace.getBoundingClientRect().height;
    const splitH = split.getBoundingClientRect().height || 8;
    return Math.max(64, ws - splitH - 200);
  };
  split.addEventListener("pointerdown", (ev) => {
    if (ev.button !== 0) return;
    ev.preventDefault();
    split.setPointerCapture(ev.pointerId);
    const startY = ev.clientY;
    const startH = term.getBoundingClientRect().height;
    const move = (e) => {
      applyTermH(clamp(startH + (e.clientY - startY), 64, maxTerm()));
    };
    const up = () => {
      split.removeEventListener("pointermove", move);
      split.removeEventListener("pointerup", up);
      split.removeEventListener("pointercancel", up);
    };
    split.addEventListener("pointermove", move);
    split.addEventListener("pointerup", up);
    split.addEventListener("pointercancel", up);
  });
  window.addEventListener("resize", () => {
    const h = term.getBoundingClientRect().height;
    const mx = maxTerm();
    if (h > mx) applyTermH(mx);
  });
}

function bindKeys() {
  window.addEventListener("keydown", (ev) => {
    if (!state.data) return;
    const tag = (ev.target && ev.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA") return;
    if (ev.key === "ArrowLeft") {
      ev.preventDefault();
      setPlayhead(state.playhead - 1);
    } else if (ev.key === "ArrowRight") {
      ev.preventDefault();
      setPlayhead(state.playhead + 1);
    } else if (ev.key === "Home") {
      ev.preventDefault();
      setPlayhead(1);
    } else if (ev.key === "End") {
      ev.preventDefault();
      setPlayhead(lineCount());
    }
  });
  window.addEventListener("resize", () => {
    if (!state.data) return;
    state.scale = clamp(state.scale, minScale(), MAX_SCALE);
    state.scrollX = clamp(state.scrollX, 0, maxScroll());
    renderTerm();
    queueDraw();
  });
}

$("file-input").addEventListener("change", async (ev) => {
  const files = [...ev.target.files];
  ev.target.value = "";
  if (!files.length) return;
  const fd = new FormData();
  for (const f of files) fd.append("files", f, f.name);
  $("upload-status").textContent = `正在导入 ${files.length} 个文件…`;
  try {
    const res = await fetch("/api/logs", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "导入失败");
    const n = (data.imported || []).length;
    const errn = (data.errors || []).length;
    $("upload-status").textContent = `已导入 ${n} 个` + (errn ? `，失败 ${errn}` : "");
    await refreshLogs();
    if (data.imported && data.imported[0]) selectLog(data.imported[0].id);
  } catch (e) {
    $("upload-status").textContent = e.message;
  }
});

$("tog-noise").addEventListener("change", () => {
  rebuildViewLines();
  renderTerm();
  queueDraw();
});
$("tog-all").addEventListener("change", () => {
  rebuildViewLines();
  renderTerm();
  if (state.follow) scrollTermToPlayhead();
  queueDraw();
});
$("reload-spec").addEventListener("click", async () => {
  await api("/api/spec/reload", { method: "POST" });
  await refreshSpec();
  if (state.selected) await loadTimeline({ center: state.playhead });
});

bindNle();
bindTerm();
bindSplit();
bindKeys();
refreshSpec();
refreshLogs();
