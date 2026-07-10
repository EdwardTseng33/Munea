(function () {
  "use strict";

  // ══ 常數與對照表 ═══════════════════════════════
  const ADMIN_BASE_KEY = "munea.admin.apiBaseUrl";
  const ADMIN_TOKEN_KEY = "munea.admin.token";
  const ACK_KEY = "munea.admin.alertAck";
  const DONE_KEY = "munea.admin.inboxDone";
  const DEFAULT_LOCAL_API = "http://127.0.0.1:8200";

  const ENDPOINTS = {
    northStar: { path: "/admin/north-star", body: { days: 30 } },
    accounts: { path: "/admin/accounts", body: { limit: 25 } },
    usage: { path: "/admin/usage", body: { days: 90 } },
    credits: { path: "/admin/credits", body: { limit: 12 } },
    summaries: { path: "/admin/conversation-summaries", body: { limit: 10 } },
    privacy: { path: "/admin/privacy-requests", body: { limit: 10 } },
    feedback: { path: "/admin/feedback", body: { limit: 10 } },
    safety: { path: "/admin/safety-events", body: { days: 30, limit: 20 } },
    audit: { path: "/admin/audit-events", body: { limit: 12 } },
  };

  const PAGES = {
    overview: "總覽",
    metrics: "數據看板",
    subscription: "訂閱營運",
    members: "會員管理",
    alerts: "告警中心",
    inbox: "開發者信箱",
    records: "系統紀錄",
    settings: "連線設定",
  };

  const ASSUME_KEY = "munea.admin.assumptions";
  const ASSUME_DEFAULTS = { plusPrice: 299, proPrice: 599, plusCount: 0, proCount: 0, newPaid: 0, marketing: 0, lifeMonths: 12 };

  // 霍爾判準表：健康門檻（dir=up 越高越好、down 越低越好）
  const THRESHOLDS = {
    voiceRate: { good: 0.95, warn: 0.90, dir: "up" },       // 語音接通成功率
    conversion: { good: 0.08, warn: 0.04, dir: "up" },      // 免費→付費轉換率
    ltvCac: { good: 3, warn: 1, dir: "up" },                // LTV:CAC 比值（業界通用）
    nps: { good: 40, warn: 20, dir: "up" },                 // NPS
  };

  const FEEDBACK_TYPE_ZH = { bug: "問題回報", idea: "功能許願", praise: "稱讚", nps: "打分數" };
  const PRIVACY_TYPE_ZH = {
    account_deletion: "刪除帳號", deletion: "刪除帳號", delete: "刪除帳號",
    export: "資料副本", data_export: "資料副本", correction: "資料更正",
  };
  const STATUS_ZH = {
    pending: "待處理", open: "待處理", received: "已收到", processing: "處理中",
    in_progress: "處理中", done: "已完成", completed: "已完成", closed: "已結案",
    rejected: "已婉拒", active: "生效中", expired: "已過期", canceled: "已取消",
    cancelled: "已取消", none: "沒有訂閱", unknown: "不明",
  };
  const RISK_ZH = {
    critical: "🔴 最高風險", high: "🔴 高風險", medium: "🟡 中風險",
    moderate: "🟡 中風險", low: "🟢 低風險",
  };
  const PLAN_ZH = { free: "免費版", plus: "Plus", pro: "Pro" };

  const CHART = { green: "#0e8a63", orange: "#b65f2a", prev: "#aab4af", grid: "#e8e6df", ink: "#1d2724", muted: "#65716d" };

  // ══ 小工具 ═════════════════════════════════════
  const $ = (id) => document.getElementById(id);

  const state = { data: null, errors: {}, connected: false, trendDays: 30 };

  function zh(map, value, fallback) {
    if (value === null || value === undefined || value === "") return fallback || "－";
    const key = String(value).toLowerCase();
    return map[key] || String(value);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function fmt(value, fallback = "－") {
    if (value === null || value === undefined || value === "") return fallback;
    return String(value);
  }

  function fmtNum(value) {
    if (value === null || value === undefined || value === "" || isNaN(value)) return "－";
    const n = Number(value);
    if (Number.isInteger(n)) return n.toLocaleString("en-US");
    return (Math.round(n * 10) / 10).toLocaleString("en-US");
  }

  function fmtMoney(value) {
    if (value === null || value === undefined || isNaN(value)) return "－";
    return "NT$" + Math.round(Number(value)).toLocaleString("en-US");
  }

  function eventCount(name) {
    const counts = (state.data && state.data.usage && state.data.usage.eventCounts) || {};
    return Number(counts[name] || 0);
  }

  // 從幾個可能的事件名裡取第一個有值的計數（引擎命名還在演進）
  function eventCountAny(names) {
    for (const n of names) { if (eventCount(n) > 0) return { count: eventCount(n), name: n }; }
    return { count: 0, name: names[0] };
  }

  function fmtTime(value) {
    if (!value) return "－";
    const date = new Date(value);
    if (isNaN(date.getTime())) return String(value);
    try {
      return new Intl.DateTimeFormat("zh-TW", {
        timeZone: "Asia/Taipei", month: "numeric", day: "numeric",
        hour: "2-digit", minute: "2-digit", hour12: false,
      }).format(date);
    } catch (e) { return String(value); }
  }

  function explainError(message) {
    const text = String(message || "");
    if (/invalid_admin_token/.test(text)) return "通行碼不對，再檢查一下有沒有貼錯";
    if (/admin_token_not_configured/.test(text)) return "伺服器那端還沒設定通行碼（要請工程端補設定）";
    if (/http_401|http_403/.test(text)) return "被大門擋住了（權限不夠或通行碼錯）";
    if (/http_404/.test(text)) return "這台伺服器沒有這項資料（可能版本太舊）";
    if (/http_5\d\d/.test(text)) return "伺服器那端出錯了";
    if (/Failed to fetch|NetworkError|load failed/i.test(text)) return "連不到伺服器（網址不對、服務沒開、或網路問題）";
    return text;
  }

  function emptyNote(text) { return `<div class="empty-note">${escapeHtml(text)}</div>`; }

  // 燈號：依門檻回傳 🟢🟡🔴 + 文字
  function lightFor(value, spec) {
    if (value === null || value === undefined || isNaN(value)) return { klass: "na", text: "－ 尚無資料" };
    const good = spec.dir === "up" ? value >= spec.good : value <= spec.good;
    const warn = spec.dir === "up" ? value >= spec.warn : value <= spec.warn;
    if (good) return { klass: "good", text: "🟢 健康" };
    if (warn) return { klass: "warn", text: "🟡 注意" };
    return { klass: "bad", text: "🔴 危險" };
  }

  function lightSpan(value, spec) {
    const l = lightFor(value, spec);
    return `<span class="light ${l.klass}">${l.text}</span>`;
  }

  function loadStore(key) {
    try { return JSON.parse(localStorage.getItem(key) || "{}"); } catch (e) { return {}; }
  }
  function saveStore(key, obj) { localStorage.setItem(key, JSON.stringify(obj)); }

  // ══ 連線 ═══════════════════════════════════════
  function initialBaseUrl() {
    const saved = localStorage.getItem(ADMIN_BASE_KEY);
    if (saved) return saved;
    if (location.protocol === "http:" || location.protocol === "https:") return location.origin;
    return DEFAULT_LOCAL_API;
  }

  function normalizeBaseUrl(value) { return String(value || "").trim().replace(/\/+$/, ""); }

  function envLabelFor(baseUrl) {
    const url = String(baseUrl || "");
    if (/munea-brain-staging/.test(url)) return "雲端試營運（給我們自己測的那台）";
    if (/127\.0\.0\.1|localhost/.test(url)) return "這台電腦（本機測試）";
    if (/run\.app/.test(url)) return "雲端伺服器";
    if (!url) return "－";
    return url.replace(/^https?:\/\//, "");
  }

  function updateEnvLabel() {
    const label = envLabelFor($("apiBaseUrl").value);
    $("envLabel").textContent = label;
    $("envChip").textContent = label.replace(/（.*?）/, "");
  }

  function setStatus(text, klass) {
    const node = $("connectionStatus");
    node.textContent = text;
    node.className = "status-pill" + (klass ? ` ${klass}` : "");
  }

  function setRaw(payload) {
    $("rawOutput").textContent = JSON.stringify(payload || {}, null, 2);
    $("rawUpdatedAt").textContent = payload && Object.keys(payload).length
      ? `抓取時間：${fmtTime(new Date().toISOString())}` : "";
  }

  async function postAdmin(baseUrl, token, endpoint, body) {
    const response = await fetch(`${baseUrl}${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json; charset=utf-8", "X-Munea-Admin-Token": token },
      body: JSON.stringify(body || {}),
    });
    const text = await response.text();
    let payload = {};
    try { payload = text ? JSON.parse(text) : {}; }
    catch (e) { payload = { ok: false, error: { code: "invalid_json", message: text.slice(0, 300) } }; }
    if (!response.ok || payload.ok === false) {
      const code = payload.error && payload.error.code ? payload.error.code : `http_${response.status}`;
      throw new Error(code);
    }
    return payload;
  }

  async function refreshAll() {
    const baseUrl = normalizeBaseUrl($("apiBaseUrl").value);
    const token = $("adminToken").value.trim();

    if (!baseUrl) { setStatus("要先填伺服器網址", "error"); location.hash = "#settings"; $("advancedRow").hidden = false; return; }
    if (!token) { setStatus("要先貼通行碼", "error"); location.hash = "#settings"; $("adminToken").focus(); return; }

    localStorage.setItem(ADMIN_BASE_KEY, baseUrl);
    if ($("rememberToken").checked) localStorage.setItem(ADMIN_TOKEN_KEY, token);
    else localStorage.removeItem(ADMIN_TOKEN_KEY);
    updateEnvLabel();
    setStatus("讀取中…", "");

    const requests = { ...ENDPOINTS };
    const q = $("accountQuery").value.trim();
    requests.accounts = { ...ENDPOINTS.accounts, body: { ...ENDPOINTS.accounts.body, query: q } };

    const entries = Object.entries(requests);
    const results = await Promise.allSettled(
      entries.map(async ([key, cfg]) => ({ key, payload: await postAdmin(baseUrl, token, cfg.path, cfg.body) }))
    );

    const data = {}; const errors = {};
    results.forEach((result, i) => {
      const key = entries[i][0];
      if (result.status === "fulfilled") data[key] = result.value.payload;
      else errors[key] = (result.reason && result.reason.message) || "request_failed";
    });

    state.data = data;
    state.errors = errors;
    state.connected = Object.keys(data).length > 0;
    setRaw({ data, errors });
    $("lastUpdated").textContent = state.connected ? `資料時間 ${fmtTime(new Date().toISOString())}` : "";

    renderCurrentPage();
    updateBadges();
    updateGate();

    const failed = Object.keys(errors).length;
    if (failed === 0) setStatus("✅ 已連上", "ok");
    else if (failed === entries.length) {
      setStatus("❌ 連不上", "error");
      $("connectHint").textContent = `連線失敗：${explainError(errors[Object.keys(errors)[0]])}`;
    } else setStatus(`⚠ 有 ${failed} 區讀不到`, "warn");
  }

  // ══ 分頁路由 ═══════════════════════════════════
  function currentPage() {
    const hash = (location.hash || "#overview").slice(1);
    return PAGES[hash] ? hash : "overview";
  }

  function showPage() {
    const page = currentPage();
    document.querySelectorAll(".page").forEach((el) => { el.hidden = el.id !== `page-${page}`; });
    document.querySelectorAll("#sideNav a").forEach((a) => a.classList.toggle("on", a.dataset.page === page));
    $("pageTitle").textContent = PAGES[page];
    updateGate();
    renderCurrentPage();
  }

  function updateGate() {
    const page = currentPage();
    const needGate = !state.connected && page !== "settings";
    $("connectGate").hidden = !needGate;
    if (needGate) $(`page-${page}`).hidden = true;
  }

  // ══ 圖表引擎（純 SVG 手刻） ═════════════════════
  const SVG_NS = "http://www.w3.org/2000/svg";

  function niceMax(value) {
    if (!value || value <= 0) return 4;
    const raw = value * 1.12;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    for (const m of [1, 2, 2.5, 4, 5, 8, 10]) {
      if (m * mag >= raw) return m * mag;
    }
    return 10 * mag;
  }

  function svgEl(tag, attrs) {
    const el = document.createElementNS(SVG_NS, tag);
    Object.entries(attrs || {}).forEach(([k, v]) => el.setAttribute(k, v));
    return el;
  }

  function showTip(html, clientX, clientY) {
    const tip = $("chartTip");
    tip.innerHTML = html;
    tip.hidden = false;
    const pad = 14;
    const rect = tip.getBoundingClientRect();
    let x = clientX + pad; let y = clientY + pad;
    if (x + rect.width > window.innerWidth - 8) x = clientX - rect.width - pad;
    if (y + rect.height > window.innerHeight - 8) y = clientY - rect.height - pad;
    tip.style.left = `${x}px`; tip.style.top = `${y}px`;
  }
  function hideTip() { $("chartTip").hidden = true; }

  function shortDate(iso) {
    const parts = String(iso).split("-");
    return parts.length === 3 ? `${Number(parts[1])}/${Number(parts[2])}` : iso;
  }

  // 折線圖（1-2 條線、滑過出十字線與提示）
  function buildLineChart(container, opts) {
    const { series, labels } = opts; // series: [{name,color,values,wash}]
    const W = 720, H = 250, L = 48, R = 16, T = 16, B = 30;
    const plotW = W - L - R, plotH = H - T - B;
    const maxVal = niceMax(Math.max(1, ...series.flatMap((s) => s.values)));
    const n = labels.length;
    const x = (i) => L + (n <= 1 ? plotW / 2 : (i / (n - 1)) * plotW);
    const y = (v) => T + plotH - (v / maxVal) * plotH;

    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" });

    // 格線＋Y 軸刻度（乾淨數字）
    for (let t = 0; t <= 4; t++) {
      const val = (maxVal / 4) * t;
      const gy = y(val);
      svg.appendChild(svgEl("line", { x1: L, x2: W - R, y1: gy, y2: gy, stroke: CHART.grid, "stroke-width": 1 }));
      const tick = svgEl("text", { x: L - 8, y: gy + 4, "text-anchor": "end", "font-size": 11, fill: CHART.muted });
      tick.textContent = fmtNum(val);
      svg.appendChild(tick);
    }
    // X 軸標籤（約 6 個）
    const step = Math.max(1, Math.ceil(n / 6));
    for (let i = 0; i < n; i += step) {
      const tx = svgEl("text", { x: x(i), y: H - 8, "text-anchor": "middle", "font-size": 11, fill: CHART.muted });
      tx.textContent = shortDate(labels[i]);
      svg.appendChild(tx);
    }

    series.forEach((s) => {
      const pts = s.values.map((v, i) => `${x(i)},${y(v)}`).join(" ");
      if (s.wash) {
        const area = svgEl("polygon", {
          points: `${L},${T + plotH} ${pts} ${x(n - 1)},${T + plotH}`,
          fill: s.color, opacity: 0.1,
        });
        svg.appendChild(area);
      }
      svg.appendChild(svgEl("polyline", {
        points: pts, fill: "none", stroke: s.color,
        "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round",
      }));
      // 尾端點（白圈）＋尾端數值標
      const lastV = s.values[n - 1];
      svg.appendChild(svgEl("circle", { cx: x(n - 1), cy: y(lastV), r: 4.5, fill: s.color, stroke: "#fff", "stroke-width": 2 }));
      const endLabel = svgEl("text", { x: x(n - 1) - 6, y: y(lastV) - 10, "text-anchor": "end", "font-size": 11.5, "font-weight": 700, fill: CHART.ink });
      endLabel.textContent = fmtNum(lastV);
      svg.appendChild(endLabel);
    });

    // 滑過層：十字線＋跟著的點
    const cross = svgEl("line", { x1: 0, x2: 0, y1: T, y2: T + plotH, stroke: CHART.muted, "stroke-width": 1, opacity: 0 });
    svg.appendChild(cross);
    const hoverDots = series.map((s) => {
      const dot = svgEl("circle", { r: 5, fill: s.color, stroke: "#fff", "stroke-width": 2, opacity: 0 });
      svg.appendChild(dot);
      return dot;
    });
    const overlay = svgEl("rect", { x: L, y: T, width: plotW, height: plotH, fill: "transparent" });
    overlay.addEventListener("mousemove", (event) => {
      const rect = svg.getBoundingClientRect();
      const px = ((event.clientX - rect.left) / rect.width) * W;
      const i = Math.max(0, Math.min(n - 1, Math.round(((px - L) / plotW) * (n - 1))));
      cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("opacity", 0.45);
      const lines = series.map((s, si) => {
        hoverDots[si].setAttribute("cx", x(i)); hoverDots[si].setAttribute("cy", y(s.values[i])); hoverDots[si].setAttribute("opacity", 1);
        return `<span style="color:#c9d6cf">${escapeHtml(s.name)}</span>　<b>${fmtNum(s.values[i])}</b>`;
      });
      showTip(`<div>${shortDate(labels[i])}</div>${lines.join("<br>")}`, event.clientX, event.clientY);
    });
    overlay.addEventListener("mouseleave", () => {
      cross.setAttribute("opacity", 0);
      hoverDots.forEach((d) => d.setAttribute("opacity", 0));
      hideTip();
    });
    svg.appendChild(overlay);

    container.innerHTML = "";
    container.appendChild(svg);
    if (series.length >= 2) {
      const legend = document.createElement("div");
      legend.className = "legend";
      legend.innerHTML = series.map((s) => `<span class="key"><span class="swatch" style="background:${s.color}"></span>${escapeHtml(s.name)}</span>`).join("");
      container.appendChild(legend);
    }
  }

  // 分組長條圖（本期 vs 前期）
  function buildCompareBars(container, opts) {
    const { groups, curName, prevName } = opts; // groups: [{label, cur, prev}]
    const W = 720, H = 250, L = 48, R = 16, T = 20, B = 30;
    const plotW = W - L - R, plotH = H - T - B;
    const maxVal = niceMax(Math.max(1, ...groups.flatMap((g) => [g.cur, g.prev])));
    const y = (v) => T + plotH - (v / maxVal) * plotH;
    const band = plotW / groups.length;
    const barW = Math.min(24, band * 0.22);

    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" });

    for (let t = 0; t <= 4; t++) {
      const val = (maxVal / 4) * t;
      const gy = y(val);
      svg.appendChild(svgEl("line", { x1: L, x2: W - R, y1: gy, y2: gy, stroke: CHART.grid, "stroke-width": 1 }));
      const tick = svgEl("text", { x: L - 8, y: gy + 4, "text-anchor": "end", "font-size": 11, fill: CHART.muted });
      tick.textContent = fmtNum(val);
      svg.appendChild(tick);
    }

    groups.forEach((g, gi) => {
      const cx = L + band * gi + band / 2;
      const bars = [
        { v: g.prev, color: CHART.prev, name: prevName, x: cx - barW - 1 },
        { v: g.cur, color: CHART.green, name: curName, x: cx + 1 },
      ];
      bars.forEach((b) => {
        const top = y(b.v);
        const h = Math.max(0, T + plotH - top);
        const rect = svgEl("path", {
          // 上端 4px 圓角、底端貼基線方角
          d: h <= 0.5
            ? `M ${b.x} ${T + plotH} h ${barW}`
            : `M ${b.x} ${T + plotH} V ${top + 4} Q ${b.x} ${top} ${b.x + 4} ${top} H ${b.x + barW - 4} Q ${b.x + barW} ${top} ${b.x + barW} ${top + 4} V ${T + plotH} Z`,
          fill: b.color,
        });
        rect.addEventListener("mousemove", (event) => showTip(`<div>${escapeHtml(g.label)} · ${escapeHtml(b.name)}</div><b>${fmtNum(b.v)}</b>`, event.clientX, event.clientY));
        rect.addEventListener("mouseleave", hideTip);
        svg.appendChild(rect);
        const cap = svgEl("text", { x: b.x + barW / 2, y: top - 6, "text-anchor": "middle", "font-size": 11, fill: CHART.muted });
        cap.textContent = fmtNum(b.v);
        svg.appendChild(cap);
      });
      const lbl = svgEl("text", { x: cx, y: H - 8, "text-anchor": "middle", "font-size": 11.5, fill: CHART.ink });
      lbl.textContent = g.label;
      svg.appendChild(lbl);
    });

    container.innerHTML = "";
    container.appendChild(svg);
    const legend = document.createElement("div");
    legend.className = "legend";
    legend.innerHTML = `
      <span class="key"><span class="swatch" style="background:${CHART.green}"></span>${escapeHtml(curName)}</span>
      <span class="key"><span class="swatch" style="background:${CHART.prev}"></span>${escapeHtml(prevName)}</span>`;
    container.appendChild(legend);
  }

  // 迷你趨勢線（KPI 卡用）：整條低調灰、末端綠點
  function sparkline(values) {
    const W = 120, H = 32, P = 3;
    const max = Math.max(1, ...values);
    const n = values.length;
    const x = (i) => P + (i / (n - 1)) * (W - P * 2);
    const y = (v) => H - P - (v / max) * (H - P * 2);
    const pts = values.map((v, i) => `${x(i)},${y(v)}`).join(" ");
    return `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" aria-hidden="true">
      <polyline points="${pts}" fill="none" stroke="${CHART.prev}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
      <circle cx="${x(n - 1)}" cy="${y(values[n - 1])}" r="3.5" fill="${CHART.green}" stroke="#fff" stroke-width="2"/>
    </svg>`;
  }

  // ══ 數據運算：由每日明細算窗口與比較 ═══════════
  function dailyMap() {
    const usage = state.data && state.data.usage;
    const map = {};
    ((usage && usage.daily) || []).forEach((d) => { map[d.date] = d; });
    return map;
  }

  function lastNDates(n, offset = 0) {
    const out = [];
    const now = new Date();
    for (let i = n - 1 + offset; i >= offset; i--) {
      const d = new Date(now.getTime() - i * 86400000);
      out.push(d.toISOString().slice(0, 10));
    }
    return out;
  }

  function seriesFor(metric, dates, map) {
    return dates.map((date) => Number((map[date] || {})[metric] || 0));
  }

  function sumWindow(metric, n, offset, map) {
    return seriesFor(metric, lastNDates(n, offset), map).reduce((a, b) => a + b, 0);
  }

  const COMPARE_METRICS = [
    { key: "meaningfulEvents", name: "有意義互動" },
    { key: "events", name: "互動次數" },
    { key: "voiceMinutes", name: "語音分鐘" },
    { key: "avatarMinutes", name: "視訊臉分鐘" },
  ];

  function deltaBadge(cur, prev) {
    if (!prev && !cur) return '<span class="kpi-delta flat">— 持平</span>';
    if (!prev) return '<span class="kpi-delta up">▲ 新增</span>';
    const pct = ((cur - prev) / prev) * 100;
    if (Math.abs(pct) < 0.5) return '<span class="kpi-delta flat">— 持平</span>';
    const cls = pct > 0 ? "up" : "down";
    const arrow = pct > 0 ? "▲" : "▼";
    return `<span class="kpi-delta ${cls}">${arrow} ${Math.abs(pct) >= 100 ? Math.round(Math.abs(pct)) : Math.abs(pct).toFixed(1)}%</span>`;
  }

  // ══ 各頁渲染 ═══════════════════════════════════
  function renderCurrentPage() {
    if (!state.connected) return;
    const page = currentPage();
    if (page === "overview") renderOverview();
    else if (page === "metrics") renderMetrics();
    else if (page === "subscription") renderSubscription();
    else if (page === "members") { renderAccounts(); renderCredits(); }
    else if (page === "alerts") renderAlerts();
    else if (page === "inbox") renderInbox();
    else if (page === "records") { renderSummaries(); renderAudit(); }
    renderErrors();
  }

  function renderErrors() {
    const PANEL_BY_ENDPOINT = {
      accounts: "accountsPanel", credits: "creditsPanel", summaries: "summariesPanel",
      privacy: "privacyPanel", feedback: "feedbackPanel", safety: "safetyPanel", audit: "auditPanel",
    };
    Object.entries(state.errors).forEach(([key, message]) => {
      const panelId = PANEL_BY_ENDPOINT[key];
      if (!panelId || !$(panelId)) return;
      $(panelId).innerHTML = `<div class="item error-item"><strong>這區暫時讀不到</strong><div class="meta">${escapeHtml(explainError(message))}</div></div>`;
    });
  }

  function renderOverview() {
    const north = (state.data && state.data.northStar) || {};
    $("nsValue").textContent = fmt(north.meaningfulCompanionDays);
    $("supActive").textContent = fmt(north.activePeople);
    const vr = north.voiceSessionSuccessRate;
    if (vr !== null && vr !== undefined) {
      $("supVoiceRate").innerHTML = `${Math.round(vr * 100)}%${lightSpan(vr, THRESHOLDS.voiceRate)}`;
    } else {
      $("supVoiceRate").textContent = "－";
    }
    $("supRoutine").textContent = fmt(north.routineCompletions);
    $("supFamily").textContent = fmt(north.familyInteractions);

    const map = dailyMap();
    $("kpiGrid").innerHTML = COMPARE_METRICS.map((m) => {
      const cur = sumWindow(m.key, 7, 0, map);
      const prev = sumWindow(m.key, 7, 7, map);
      const spark = seriesFor(m.key, lastNDates(14), map);
      return `
        <article class="card kpi-card">
          <span>${m.name}</span>
          <div><span class="kpi-value">${fmtNum(cur)}</span>${deltaBadge(cur, prev)}</div>
          <small>前 7 天：${fmtNum(prev)}</small>
          <div class="kpi-spark">${sparkline(spark)}</div>
        </article>`;
    }).join("");

    // 需要留意：告警＋信箱未處理
    const openAlerts = openAlertCount();
    const openInbox = openInboxCount();
    const rows = [];
    if (openAlerts > 0) rows.push(`<a class="attn hot" href="#alerts">🚨 有 <b>${openAlerts}</b> 件安全警訊還沒處理（建議 24 小時內跟進）<span class="go">去處理 →</span></a>`);
    if (openInbox > 0) rows.push(`<a class="attn" href="#inbox">📮 有 <b>${openInbox}</b> 則用戶意見／隱私申請還沒處理<span class="go">去看看 →</span></a>`);
    if (!rows.length) rows.push('<div class="attn">✅ 目前沒有要人跟進的事——都乾淨。</div>');
    $("attentionRow").innerHTML = rows.join("");
  }

  function renderMetrics() {
    const map = dailyMap();
    const days = state.trendDays;
    const dates = lastNDates(days);

    buildLineChart($("trendChart"), {
      labels: dates,
      series: [{ name: "有意義互動", color: CHART.green, values: seriesFor("meaningfulEvents", dates, map), wash: true }],
    });
    fillTable($("trendTable"), ["日期", "有意義互動"], dates.map((d) => [shortDate(d), fmtNum((map[d] || {}).meaningfulEvents || 0)]));

    buildLineChart($("usageChart"), {
      labels: dates,
      series: [
        { name: "語音分鐘", color: CHART.green, values: seriesFor("voiceMinutes", dates, map) },
        { name: "視訊臉分鐘", color: CHART.orange, values: seriesFor("avatarMinutes", dates, map) },
      ],
    });
    fillTable($("usageTable"), ["日期", "語音分鐘", "視訊臉分鐘"],
      dates.map((d) => [shortDate(d), fmtNum((map[d] || {}).voiceMinutes || 0), fmtNum((map[d] || {}).avatarMinutes || 0)]));

    const weekGroups = COMPARE_METRICS.map((m) => ({ label: m.name, cur: sumWindow(m.key, 7, 0, map), prev: sumWindow(m.key, 7, 7, map) }));
    buildCompareBars($("weekCompare"), { groups: weekGroups, curName: "近 7 天", prevName: "前 7 天" });
    fillTable($("weekTable"), ["指標", "近 7 天", "前 7 天"], weekGroups.map((g) => [g.label, fmtNum(g.cur), fmtNum(g.prev)]));

    const monthGroups = COMPARE_METRICS.map((m) => ({ label: m.name, cur: sumWindow(m.key, 30, 0, map), prev: sumWindow(m.key, 30, 30, map) }));
    buildCompareBars($("monthCompare"), { groups: monthGroups, curName: "近 30 天", prevName: "前 30 天" });
    fillTable($("monthTable"), ["指標", "近 30 天", "前 30 天"], monthGroups.map((g) => [g.label, fmtNum(g.cur), fmtNum(g.prev)]));
  }

  function fillTable(container, headers, rows) {
    container.innerHTML = `
      <table>
        <thead><tr>${headers.map((h, i) => `<th${i ? ' class="num"' : ""}>${escapeHtml(h)}</th>`).join("")}</tr></thead>
        <tbody>${rows.map((r) => `<tr>${r.map((c, i) => `<td${i ? ' class="num"' : ""}>${escapeHtml(c)}</td>`).join("")}</tr>`).join("")}</tbody>
      </table>`;
  }

  // ── 訂閱營運 ──
  function loadAssumptions() {
    const saved = loadStore(ASSUME_KEY);
    return { ...ASSUME_DEFAULTS, ...saved };
  }

  function readAssumptionsFromInputs() {
    const a = {
      plusPrice: Number($("aPlusPrice").value) || 0,
      proPrice: Number($("aProPrice").value) || 0,
      plusCount: Number($("aPlusCount").value) || 0,
      proCount: Number($("aProCount").value) || 0,
      newPaid: Number($("aNewPaid").value) || 0,
      marketing: Number($("aMarketing").value) || 0,
      lifeMonths: Math.max(1, Number($("aLifeMonths").value) || 1),
    };
    saveStore(ASSUME_KEY, a);
    return a;
  }

  function fillAssumptionInputs(a) {
    $("aPlusPrice").value = a.plusPrice;
    $("aProPrice").value = a.proPrice;
    $("aPlusCount").value = a.plusCount;
    $("aProCount").value = a.proCount;
    $("aNewPaid").value = a.newPaid;
    $("aMarketing").value = a.marketing;
    $("aLifeMonths").value = a.lifeMonths;
  }

  function bizCard(label, value, hint, opts) {
    opts = opts || {};
    const needs = opts.needs ? " needs" : "";
    const light = opts.light !== undefined ? ` ${opts.light}` : "";
    return `<article class="card kpi-card${needs}">
      <span>${escapeHtml(label)}</span>
      <div><span class="kpi-value">${escapeHtml(value)}</span>${light}</div>
      <span class="kpi-hint">${hint}</span>
    </article>`;
  }

  function renderSubscription() {
    const a = readAssumptionsFromInputs();
    const paidCount = a.plusCount + a.proCount;
    const mrr = a.plusCount * a.plusPrice + a.proCount * a.proPrice;
    const arpu = paidCount > 0 ? mrr / paidCount : null;
    const ltv = arpu !== null ? arpu * a.lifeMonths : null;
    const cac = a.newPaid > 0 ? a.marketing / a.newPaid : (a.marketing > 0 ? null : 0);
    const ratio = (ltv !== null && cac && cac > 0) ? ltv / cac : null;

    const biz = [];
    biz.push(bizCard("每月經常性收入 MRR", fmtMoney(mrr),
      `Plus ${a.plusCount} 人 × ${fmtMoney(a.plusPrice)} ＋ Pro ${a.proCount} 人 × ${fmtMoney(a.proPrice)}。每月穩定進帳的訂閱錢。`));
    biz.push(bizCard("每位付費用戶月貢獻 ARPU", arpu !== null ? fmtMoney(arpu) : "－",
      paidCount > 0 ? `MRR ÷ ${paidCount} 位付費用戶` : "先在上面填目前訂閱人數"));
    biz.push(bizCard("顧客終身價值 LTV", ltv !== null ? fmtMoney(ltv) : "－",
      arpu !== null ? `一位付費用戶一輩子帶來的錢 ＝ 月貢獻 × 預估 ${a.lifeMonths} 個月` : "先填訂閱人數"));
    biz.push(bizCard("獲客成本 CAC", cac === 0 ? "NT$0" : (cac !== null ? fmtMoney(cac) : "－"),
      a.newPaid > 0 ? `當月廣告花費 ÷ ${a.newPaid} 位新付費用戶` : "填「本月新增付費用戶」＋「行銷花費」才算得出"));

    const ratioLight = ratio !== null ? lightSpan(ratio, THRESHOLDS.ltvCac) : '<span class="light na">－ 尚無資料</span>';
    biz.push(bizCard("賺回本比值 LTV : CAC", ratio !== null ? `${ratio.toFixed(1)} : 1` : "－ : 1",
      "一塊錢獲客換回幾塊錢終身價值。業界看 ≥ 3 才算健康、1 以下是每拉一個客都虧。", { light: ratioLight }));
    biz.push(bizCard("單位經濟毛利", "－",
      "每位用戶的訂閱＋點數收入，扣掉他用掉的視訊臉／語音成本。", { needs: true, light: '<span class="light na">● 待補追蹤</span>' }));

    $("bizGrid").innerHTML = biz.join("");

    // 用戶轉換（近 30 天，來自事件計數）
    const usage = state.data && state.data.usage;
    const windowDays = (usage && usage.windowDays) || 90;
    const reg = eventCountAny(["person_onboarded", "onboarding_completed", "account_created"]);
    const paid = eventCountAny(["subscription_purchased", "subscription_started"]);
    const points = eventCountAny(["points_purchased", "credits_purchased"]);
    const convRate = reg.count > 0 ? paid.count / reg.count : null;

    const conv = [];
    conv.push(bizCard("新註冊", reg.count > 0 ? fmtNum(reg.count) : "－",
      reg.count > 0 ? `近 ${windowDays} 天（來自事件 ${reg.name}）` : "需補追蹤 person_onboarded 事件才有真數字", { needs: reg.count === 0, light: reg.count > 0 ? '<span class="light good">● 系統自動</span>' : '<span class="light na">● 待補追蹤</span>' }));
    conv.push(bizCard("新增付費訂閱", paid.count > 0 ? fmtNum(paid.count) : "－",
      paid.count > 0 ? `近 ${windowDays} 天（來自事件 ${paid.name}）` : "上線有人付費後會自動出現", { light: paid.count > 0 ? '<span class="light good">● 系統自動</span>' : '<span class="light na">● 尚無</span>' }));
    conv.push(bizCard("免費→付費轉換率", convRate !== null ? `${(convRate * 100).toFixed(1)}%` : "－",
      convRate !== null ? "付費數 ÷ 註冊數" : "要有註冊與付費事件才算得出", { light: convRate !== null ? lightSpan(convRate, THRESHOLDS.conversion) : '<span class="light na">－ 尚無資料</span>' }));
    conv.push(bizCard("點數加購次數", points.count > 0 ? fmtNum(points.count) : "－",
      points.count > 0 ? `近 ${windowDays} 天（來自事件 ${points.name}）` : "上線有人加購後會自動出現", { light: points.count > 0 ? '<span class="light good">● 系統自動</span>' : '<span class="light na">● 尚無</span>' }));

    $("convGrid").innerHTML = conv.join("");

    // 待補追蹤清單（霍爾調研）
    const todos = [
      ["person_onboarded", "帳號建立時間點——算註冊數、留存 cohort 的起點"],
      ["subscription_cancelled / downgraded", "訂閱取消、降階——現在只看得到「進」看不到「出」，算不出流失率"],
      ["trial_quota_exhausted", "免費 5 分鐘試用用完那刻——看多少人真的把試用用完"],
      ["每筆通話估算成本", "視訊臉／語音每次結束記下成本，才能算單位經濟毛利"],
      ["safety_event_acknowledged / resolved", "安全警訊處理時間戳——才有回應時效（SLA）可算"],
    ];
    $("todoTrack").innerHTML = todos.map(([code, why]) => `
      <div class="item todo-item">
        <span class="code">${escapeHtml(code)}</span>
        <span>${escapeHtml(why)}</span>
      </div>`).join("");
  }

  function renderAccounts() {
    const payload = state.data && state.data.accounts;
    const accounts = (payload && payload.accounts) || [];
    if (!accounts.length) { $("accountsPanel").innerHTML = emptyNote("還沒有帳號資料——正式開放註冊後，這裡會列出每一家。"); return; }
    const rows = accounts.map((account) => {
      const family = account.familyGroup || {};
      const person = account.primaryPerson || {};
      const companion = account.companion || {};
      const members = account.familyMembers || {};
      return `<tr>
        <td>${escapeHtml(account.accountName || account.accountId)}</td>
        <td>${escapeHtml(family.name || family.id || "－")}</td>
        <td>${escapeHtml(person.displayName || person.id || "－")}</td>
        <td>${escapeHtml(companion.displayName || companion.templateId || "－")}</td>
        <td class="num">${escapeHtml(members.count || 0)}</td>
        <td>${escapeHtml(fmtTime(account.updatedAt || account.createdAt))}</td>
      </tr>`;
    }).join("");
    $("accountsPanel").innerHTML = `
      <table>
        <thead><tr><th>帳號</th><th>家庭</th><th>主要使用者</th><th>陪伴角色</th><th class="num">家人數</th><th>最近更新</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  function renderCredits() {
    const payload = state.data && state.data.credits;
    const wallet = (payload && payload.walletSummary) || {};
    const subscription = (payload && payload.subscription) || {};
    const entitlements = (payload && payload.entitlements) || {};
    $("creditsPanel").innerHTML = `
      <div class="item">
        <strong>${escapeHtml(zh(PLAN_ZH, payload && payload.activePlan, "還沒有方案資料"))}</strong>
        <div class="meta">訂閱狀態：${escapeHtml(zh(STATUS_ZH, subscription.status, "不明"))}</div>
        <div class="tag-row">
          <span class="tag">本月額度剩 ${escapeHtml(wallet.monthlyRemaining ?? "－")}</span>
          <span class="tag">加購剩 ${escapeHtml(wallet.purchasedRemaining ?? "－")}</span>
          <span class="tag">合計可用 ${escapeHtml(wallet.totalRemaining ?? "－")}</span>
        </div>
      </div>
      <div class="item">
        <strong>開通的功能</strong>
        <div class="tag-row">${Object.keys(entitlements).sort().map((k) => `<span class="tag">${escapeHtml(k)}：${escapeHtml(entitlements[k])}</span>`).join("") || '<span class="tag">還沒有資料</span>'}</div>
      </div>`;
  }

  // ── 告警 ──
  function alertId(event) { return `${event.eventTime || ""}|${event.riskLevel || ""}`; }

  function alertList() {
    const payload = state.data && state.data.safety;
    return ((payload && payload.recent) || []).slice();
  }

  function openAlertCount() {
    const ack = loadStore(ACK_KEY);
    return alertList().filter((e) => !ack[alertId(e)]).length;
  }

  function renderAlerts() {
    const payload = (state.data && state.data.safety) || {};
    const totals = payload.totals || {};
    const ack = loadStore(ACK_KEY);
    const filterOn = document.querySelector("#alertFilter button.on");
    const mode = filterOn ? filterOn.dataset.f : "open";

    const escalation = totals.requiresHumanEscalation || 0;
    $("alertSummary").innerHTML = `
      <article class="card mini-stat"><span>要人跟進</span><strong>${escapeHtml(escalation)}</strong><small>建議 24 小時內回應</small></article>
      <article class="card mini-stat"><span>還沒標記處理</span><strong>${openAlertCount()}</strong><small>下方清單按「標記已處理」</small></article>
      <article class="card mini-stat"><span>風險分佈（近 30 天）</span><strong style="font-size:1rem;line-height:2.2">${Object.keys(totals.byRiskLevel || {}).sort().map((k) => `${zh(RISK_ZH, k)} ${totals.byRiskLevel[k]}`).join("　") || "沒有警訊"}</strong><small>&nbsp;</small></article>`;

    const order = { critical: 0, high: 1, medium: 2, moderate: 2, low: 3 };
    let list = alertList().sort((a, b) => {
      const ackDiff = (ack[alertId(a)] ? 1 : 0) - (ack[alertId(b)] ? 1 : 0);
      if (ackDiff) return ackDiff;
      return (order[String(a.riskLevel).toLowerCase()] ?? 9) - (order[String(b.riskLevel).toLowerCase()] ?? 9);
    });
    if (mode === "open") list = list.filter((e) => !ack[alertId(e)]);

    if (!list.length) {
      $("safetyPanel").innerHTML = emptyNote(mode === "open" ? "沒有待處理的警訊——是好消息。" : "這 30 天沒有安全警訊。");
      return;
    }
    $("safetyPanel").innerHTML = list.map((event) => {
      const id = alertId(event);
      const done = !!ack[id];
      return `
      <div class="item ${done ? "done" : ""}">
        <strong>${escapeHtml(zh(RISK_ZH, event.riskLevel, event.source || "待查看"))}${done ? "　✅ 已處理" : ""}</strong>
        <div class="meta">${escapeHtml(fmtTime(event.eventTime))}</div>
        <div class="tag-row">${(event.categories || []).map((c) => `<span class="tag warn">${escapeHtml(c)}</span>`).join("")}</div>
        <div class="item-actions">
          <button type="button" class="${done ? "undo" : ""}" data-ack="${escapeHtml(id)}">${done ? "改回未處理" : "標記已處理"}</button>
        </div>
      </div>`;
    }).join("");

    $("safetyPanel").querySelectorAll("[data-ack]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const store = loadStore(ACK_KEY);
        const id = btn.dataset.ack;
        if (store[id]) delete store[id]; else store[id] = new Date().toISOString();
        saveStore(ACK_KEY, store);
        renderAlerts(); updateBadges();
        if (currentPage() === "overview") renderOverview();
      });
    });
  }

  // ── 信箱 ──
  function inboxId(item) { return `${item.createdAt || item.requestedAt || ""}|${item.type || ""}`; }

  function openInboxCount() {
    const done = loadStore(DONE_KEY);
    const fb = ((state.data && state.data.feedback && state.data.feedback.latest) || []).filter((i) => !done[inboxId(i)]).length;
    const pv = ((state.data && state.data.privacy && state.data.privacy.recent) || []).filter((r) => {
      const s = String(r.status || "").toLowerCase();
      return s === "pending" || s === "open" || s === "received" || s === "";
    }).length;
    return fb + pv;
  }

  function renderInbox() {
    const payload = (state.data && state.data.feedback) || {};
    const latest = payload.latest || [];
    const done = loadStore(DONE_KEY);
    const nps = payload.nps !== null && payload.nps !== undefined ? payload.nps : "－";
    const filterOn = document.querySelector("#inboxFilter button.on");
    const mode = filterOn ? filterOn.dataset.f : "open";

    $("inboxSummary").innerHTML = `
      <article class="card mini-stat"><span>未處理意見</span><strong>${latest.filter((i) => !done[inboxId(i)]).length}</strong><small>處理完在清單打勾</small></article>
      <article class="card mini-stat"><span>推薦分數 NPS</span><strong>${escapeHtml(nps)}</strong><small>共 ${escapeHtml(payload.npsCount || 0)} 人打分</small></article>
      <article class="card mini-stat"><span>意見分佈</span><strong style="font-size:1rem;line-height:2.2">${Object.keys(payload.totals || {}).sort().map((k) => `${zh(FEEDBACK_TYPE_ZH, k)} ${payload.totals[k]}`).join("　") || "還沒有"}</strong><small>&nbsp;</small></article>`;

    let list = latest.slice().sort((a, b) => (done[inboxId(a)] ? 1 : 0) - (done[inboxId(b)] ? 1 : 0));
    if (mode === "open") list = list.filter((i) => !done[inboxId(i)]);

    if (!list.length) {
      $("feedbackPanel").innerHTML = emptyNote(mode === "open" ? "意見都處理完了。" : "還沒有人留意見——上線後這裡會熱鬧起來。");
    } else {
      $("feedbackPanel").innerHTML = list.map((item) => {
        const id = inboxId(item);
        const isDone = !!done[id];
        const safeImg = typeof item.image === "string" && item.image.indexOf("data:image/") === 0 ? item.image : "";
        const imgHtml = safeImg ? `<a href="${safeImg}" target="_blank" rel="noopener"><img src="${safeImg}" alt="附圖" style="margin-top:8px;max-width:160px;max-height:120px;border-radius:8px;border:1px solid #ccc;display:block"></a>` : "";
        return `
        <div class="item ${isDone ? "done" : ""}">
          <strong>${escapeHtml(zh(FEEDBACK_TYPE_ZH, item.type, "意見"))}${item.score !== null && item.score !== undefined ? `　${escapeHtml(item.score)} 分` : ""}${safeImg ? "　📎有附圖" : ""}${isDone ? "　✅ 已處理" : ""}</strong>
          <div class="meta">${escapeHtml(item.category || "－")} · ${escapeHtml(fmtTime(item.createdAt))} · App ${escapeHtml(item.appVersion || "?")}</div>
          <div>${escapeHtml(item.text || "")}</div>
          ${imgHtml}
          <div class="item-actions"><button type="button" class="${isDone ? "undo" : ""}" data-done="${escapeHtml(id)}">${isDone ? "改回未處理" : "標記已處理"}</button></div>
        </div>`;
      }).join("");
      $("feedbackPanel").querySelectorAll("[data-done]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const store = loadStore(DONE_KEY);
          const id = btn.dataset.done;
          if (store[id]) delete store[id]; else store[id] = new Date().toISOString();
          saveStore(DONE_KEY, store);
          renderInbox(); updateBadges();
        });
      });
    }

    const privacy = (state.data && state.data.privacy) || {};
    const recent = privacy.recent || [];
    const totals = privacy.totals || {};
    const items = recent.slice(0, 8).map((request) => `
      <div class="item">
        <strong>${escapeHtml(zh(PRIVACY_TYPE_ZH, request.type, "申請"))}</strong>
        <div class="meta">${escapeHtml(zh(STATUS_ZH, request.status))} · ${escapeHtml(fmtTime(request.requestedAt))}</div>
        <div>${escapeHtml(request.reason || "")}</div>
      </div>`).join("");
    $("privacyPanel").innerHTML = `
      <div class="tag-row">${Object.keys(totals.byStatus || {}).sort().map((k) => `<span class="tag">${escapeHtml(zh(STATUS_ZH, k))}：${escapeHtml(totals.byStatus[k])}</span>`).join("")}</div>
      ${items || emptyNote("目前沒有人申請刪帳號或要資料。")}`;
  }

  function renderSummaries() {
    const payload = (state.data && state.data.summaries) || {};
    const recent = payload.recent || [];
    const items = recent.slice(0, 8).map((summary) => `
      <div class="item">
        <strong>${escapeHtml(fmtTime(summary.createdAt) !== "－" ? fmtTime(summary.createdAt) : (summary.id || "摘要"))}</strong>
        <div>${escapeHtml(summary.summary || "")}</div>
        <div class="tag-row">
          ${(summary.memoryTags || []).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}
          ${summary.safetyRelevant ? '<span class="tag danger">涉及安全</span>' : ""}
        </div>
      </div>`).join("");
    $("summariesPanel").innerHTML = items || emptyNote("還沒有聊天摘要——有人開始跟沐寧聊天後就會出現。");
  }

  function renderAudit() {
    const payload = (state.data && state.data.audit) || {};
    const recent = payload.recent || [];
    const items = recent.slice(0, 10).map((event) => `
      <div class="item">
        <strong>${escapeHtml(event.eventType || "事件")}</strong>
        <div class="meta">${escapeHtml(event.targetTable || "－")} · ${escapeHtml(fmtTime(event.createdAt))}</div>
        <div>${escapeHtml(event.targetId || event.accountId || "")}</div>
      </div>`).join("");
    $("auditPanel").innerHTML = items || emptyNote("還沒有操作紀錄。");
  }

  function updateBadges() {
    const alerts = state.connected ? openAlertCount() : 0;
    const inbox = state.connected ? openInboxCount() : 0;
    $("alertBadge").hidden = !alerts;
    $("alertBadge").textContent = alerts;
    $("inboxBadge").hidden = !inbox;
    $("inboxBadge").textContent = inbox;
  }

  // ══ 啟動 ═══════════════════════════════════════
  function init() {
    $("apiBaseUrl").value = initialBaseUrl();
    updateEnvLabel();
    if (window.MuneaVersion) $("appVer").textContent = `v${window.MuneaVersion.current}`;

    const savedToken = localStorage.getItem(ADMIN_TOKEN_KEY) || "";
    if (savedToken) { $("adminToken").value = savedToken; $("rememberToken").checked = true; }

    $("refreshAdmin").addEventListener("click", refreshAll);
    $("connectBtn").addEventListener("click", refreshAll);
    $("gotoSettings").addEventListener("click", () => { location.hash = "#settings"; });
    $("accountQuery").addEventListener("keydown", (e) => { if (e.key === "Enter") refreshAll(); });
    $("clearRaw").addEventListener("click", () => setRaw({}));
    $("toggleAdvanced").addEventListener("click", () => { $("advancedRow").hidden = !$("advancedRow").hidden; });
    $("apiBaseUrl").addEventListener("input", updateEnvLabel);
    $("toggleToken").addEventListener("click", () => {
      const field = $("adminToken");
      const showing = field.type === "text";
      field.type = showing ? "password" : "text";
      $("toggleToken").textContent = showing ? "顯示" : "隱藏";
    });

    // 訂閱營運假設：帶入本機存值、改動即時重算
    fillAssumptionInputs(loadAssumptions());
    ["aPlusPrice", "aProPrice", "aPlusCount", "aProCount", "aNewPaid", "aMarketing", "aLifeMonths"].forEach((id) => {
      $(id).addEventListener("input", () => { if (currentPage() === "subscription") renderSubscription(); });
    });
    $("resetAssume").addEventListener("click", () => {
      saveStore(ASSUME_KEY, {});
      fillAssumptionInputs({ ...ASSUME_DEFAULTS });
      renderSubscription();
    });

    // 篩選鈕（範圍／告警／信箱）
    document.querySelectorAll(".pill-group").forEach((group) => {
      group.addEventListener("click", (e) => {
        const btn = e.target.closest("button");
        if (!btn) return;
        group.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b === btn));
        if (group.id === "rangePills") { state.trendDays = Number(btn.dataset.days) || 30; renderMetrics(); }
        else if (group.id === "alertFilter") renderAlerts();
        else if (group.id === "inboxFilter") renderInbox();
      });
    });

    window.addEventListener("hashchange", showPage);
    showPage();

    if (savedToken) refreshAll();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
