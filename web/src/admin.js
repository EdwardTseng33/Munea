(function () {
  const ADMIN_BASE_KEY = "munea.admin.apiBaseUrl";
  const ADMIN_TOKEN_KEY = "munea.admin.token";
  const DEFAULT_LOCAL_API = "http://127.0.0.1:8200";
  const ENDPOINTS = {
    northStar: { path: "/admin/north-star", body: { days: 30 } },
    accounts: { path: "/admin/accounts", body: { limit: 25 } },
    usage: { path: "/admin/usage", body: { days: 30 } },
    credits: { path: "/admin/credits", body: { limit: 12 } },
    summaries: { path: "/admin/conversation-summaries", body: { limit: 10 } },
    privacy: { path: "/admin/privacy-requests", body: { limit: 10 } },
    feedback: { path: "/admin/feedback", body: { limit: 10 } },
    safety: { path: "/admin/safety-events", body: { days: 30, limit: 10 } },
    audit: { path: "/admin/audit-events", body: { limit: 12 } },
  };
  const PANEL_BY_ENDPOINT = {
    accounts: "accountsPanel",
    credits: "creditsPanel",
    summaries: "summariesPanel",
    privacy: "privacyPanel",
    feedback: "feedbackPanel",
    safety: "safetyPanel",
    audit: "auditPanel",
  };

  // ── 中文對照表：把工程代號翻成人話 ──────────────
  const FEEDBACK_TYPE_ZH = {
    bug: "問題回報",
    idea: "功能許願",
    praise: "稱讚",
    nps: "打分數",
  };
  const PRIVACY_TYPE_ZH = {
    account_deletion: "刪除帳號",
    deletion: "刪除帳號",
    delete: "刪除帳號",
    export: "資料副本",
    data_export: "資料副本",
    correction: "資料更正",
  };
  const STATUS_ZH = {
    pending: "待處理",
    open: "待處理",
    received: "已收到",
    processing: "處理中",
    in_progress: "處理中",
    done: "已完成",
    completed: "已完成",
    closed: "已結案",
    rejected: "已婉拒",
    active: "生效中",
    expired: "已過期",
    canceled: "已取消",
    cancelled: "已取消",
    none: "沒有訂閱",
    unknown: "不明",
  };
  const RISK_ZH = {
    critical: "🔴 最高風險",
    high: "🔴 高風險",
    medium: "🟡 中風險",
    moderate: "🟡 中風險",
    low: "🟢 低風險",
  };
  const PLAN_ZH = {
    free: "免費版",
    plus: "Plus",
    pro: "Pro",
  };

  const $ = (id) => document.getElementById(id);

  function zh(map, value, fallback) {
    if (value === null || value === undefined || value === "") return fallback || "－";
    const key = String(value).toLowerCase();
    return map[key] || String(value);
  }

  function initialBaseUrl() {
    const saved = localStorage.getItem(ADMIN_BASE_KEY);
    if (saved) return saved;
    if (window.location.protocol === "http:" || window.location.protocol === "https:") {
      return window.location.origin;
    }
    return DEFAULT_LOCAL_API;
  }

  function normalizeBaseUrl(value) {
    return String(value || "").trim().replace(/\/+$/, "");
  }

  // 網址 → 看得懂的環境名稱
  function envLabelFor(baseUrl) {
    const url = String(baseUrl || "");
    if (/munea-brain-staging/.test(url)) return "雲端試營運（給我們自己測的那台）";
    if (/127\.0\.0\.1|localhost/.test(url)) return "這台電腦（本機測試）";
    if (/run\.app/.test(url)) return "雲端伺服器";
    if (!url) return "－";
    return url.replace(/^https?:\/\//, "");
  }

  function updateEnvLabel() {
    $("envLabel").textContent = envLabelFor($("apiBaseUrl").value);
  }

  function setStatus(text, state) {
    const node = $("connectionStatus");
    node.textContent = text;
    node.className = "status-pill" + (state ? ` ${state}` : "");
  }

  function setRaw(payload) {
    $("rawOutput").textContent = JSON.stringify(payload || {}, null, 2);
    $("rawUpdatedAt").textContent = payload && Object.keys(payload).length
      ? `抓取時間：${fmtTime(new Date().toISOString())}`
      : "";
  }

  function fmt(value, fallback = "－") {
    if (value === null || value === undefined || value === "") return fallback;
    return String(value);
  }

  // 時間翻成台灣好讀格式：7/9 20:18
  function fmtTime(value) {
    if (!value) return "－";
    const date = new Date(value);
    if (isNaN(date.getTime())) return String(value);
    try {
      return new Intl.DateTimeFormat("zh-TW", {
        timeZone: "Asia/Taipei",
        month: "numeric",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(date);
    } catch (error) {
      return String(value);
    }
  }

  // 錯誤代號 → 人話
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

  function countMap(map, zhMap) {
    const source = map || {};
    return Object.keys(source)
      .sort()
      .map((key) => `<span class="tag">${escapeHtml(zhMap ? zh(zhMap, key) : key)}：${escapeHtml(source[key])}</span>`)
      .join("");
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function emptyNote(text) {
    return `<div class="empty-note">${escapeHtml(text)}</div>`;
  }

  async function postAdmin(baseUrl, token, endpoint, body) {
    const response = await fetch(`${baseUrl}${endpoint}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "X-Munea-Admin-Token": token,
      },
      body: JSON.stringify(body || {}),
    });

    const text = await response.text();
    let payload = {};
    try {
      payload = text ? JSON.parse(text) : {};
    } catch (error) {
      payload = { ok: false, error: { code: "invalid_json", message: text.slice(0, 300) } };
    }

    if (!response.ok || payload.ok === false) {
      const code = payload.error && payload.error.code ? payload.error.code : `http_${response.status}`;
      throw new Error(code);
    }

    return payload;
  }

  async function refreshAdmin() {
    const baseUrl = normalizeBaseUrl($("apiBaseUrl").value);
    const token = $("adminToken").value.trim();
    const accountQuery = $("accountQuery").value.trim();

    if (!baseUrl) {
      setStatus("要先填伺服器網址", "error");
      $("advancedRow").hidden = false;
      return;
    }
    if (!token) {
      setStatus("要先貼通行碼", "error");
      $("adminToken").focus();
      return;
    }

    localStorage.setItem(ADMIN_BASE_KEY, baseUrl);
    if ($("rememberToken").checked) {
      localStorage.setItem(ADMIN_TOKEN_KEY, token);
    } else {
      localStorage.removeItem(ADMIN_TOKEN_KEY);
    }
    updateEnvLabel();
    setStatus("讀取中…", "");

    const requests = { ...ENDPOINTS };
    requests.accounts = {
      ...ENDPOINTS.accounts,
      body: { ...ENDPOINTS.accounts.body, query: accountQuery },
    };

    const requestEntries = Object.entries(requests);
    const results = await Promise.allSettled(
      requestEntries.map(async ([key, config]) => ({
        key,
        payload: await postAdmin(baseUrl, token, config.path, config.body),
      }))
    );
    const data = {};
    const errors = {};

    results.forEach((result, index) => {
      const key = requestEntries[index][0];
      if (result.status === "fulfilled") {
        data[key] = result.value.payload;
      } else {
        errors[key] = result.reason && result.reason.message
          ? result.reason.message
          : "request_failed";
      }
    });

    renderAll(data);
    renderEndpointErrors(errors);
    setRaw({ data, errors });

    const failedCount = Object.keys(errors).length;
    if (failedCount === 0) {
      setStatus("✅ 已連上，資料是最新的", "ok");
      $("connectHint").textContent = `資料抓取時間：${fmtTime(new Date().toISOString())}。要看最新的，再按一次「連線看資料」。`;
    } else if (failedCount === requestEntries.length) {
      const firstError = errors[Object.keys(errors)[0]];
      setStatus("❌ 連不上", "error");
      $("connectHint").textContent = `連線失敗：${explainError(firstError)}`;
    } else {
      setStatus(`⚠ 有 ${failedCount} 區讀不到`, "warn");
      $("connectHint").textContent = "大部分資料有進來，讀不到的區塊裡有寫原因。";
    }
  }

  function renderAll(data) {
    renderMetrics(data);
    renderAccounts(data.accounts);
    renderCredits(data.credits);
    renderSafety(data.safety);
    renderPrivacy(data.privacy);
    renderFeedback(data.feedback);
    renderAudit(data.audit);
    renderSummaries(data.summaries);
  }

  function renderEndpointErrors(errors) {
    Object.entries(errors).forEach(([key, message]) => {
      const panelId = PANEL_BY_ENDPOINT[key];
      if (!panelId) return;
      $(panelId).innerHTML = `
        <div class="item error-item">
          <strong>這區暫時讀不到</strong>
          <div class="meta">${escapeHtml(explainError(message))}</div>
        </div>
      `;
    });
  }

  function renderMetrics(data) {
    const north = data.northStar || {};
    const usage = data.usage || {};
    const totals = usage.totals || {};
    const backend = usage.backend || north.backend || {};
    $("metricMeaningfulDays").textContent = fmt(north.meaningfulCompanionDays);
    $("metricActivePeople").textContent = fmt(north.activePeople);
    $("metricEvents").textContent = fmt(totals.events ?? north.eventCount);
    $("metricVoiceMinutes").textContent = fmt(totals.voiceMinutes);
    $("metricAvatarMinutes").textContent = fmt(totals.avatarMinutes);
    const provider = String(backend.provider || "").toLowerCase();
    $("metricBackend").textContent = provider === "supabase"
      ? "雲端資料櫃"
      : provider
        ? provider
        : backend.enabled
          ? "雲端資料櫃"
          : "這台伺服器的檔案";
  }

  function renderAccounts(payload) {
    const accounts = (payload && payload.accounts) || [];
    if (!accounts.length) {
      $("accountsPanel").innerHTML = emptyNote("還沒有帳號資料——正式開放註冊後，這裡會列出每一家。");
      return;
    }
    const rows = accounts.map((account) => {
      const family = account.familyGroup || {};
      const person = account.primaryPerson || {};
      const companion = account.companion || {};
      const members = account.familyMembers || {};
      return `
        <tr>
          <td>${escapeHtml(account.accountName || account.accountId)}</td>
          <td>${escapeHtml(family.name || family.id || "－")}</td>
          <td>${escapeHtml(person.displayName || person.id || "－")}</td>
          <td>${escapeHtml(companion.displayName || companion.templateId || "－")}</td>
          <td>${escapeHtml(members.count || 0)}</td>
          <td>${escapeHtml(fmtTime(account.updatedAt || account.createdAt))}</td>
        </tr>
      `;
    }).join("");
    $("accountsPanel").innerHTML = `
      <table>
        <thead>
          <tr>
            <th>帳號</th>
            <th>家庭</th>
            <th>主要使用者</th>
            <th>陪伴角色</th>
            <th>家人數</th>
            <th>最近更新</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  }

  function renderCredits(payload) {
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
        <div class="tag-row">${countMap(entitlements) || '<span class="tag">還沒有資料</span>'}</div>
      </div>
    `;
  }

  function renderSafety(payload) {
    const totals = (payload && payload.totals) || {};
    const recent = (payload && payload.recent) || [];
    const escalation = totals.requiresHumanEscalation || 0;
    const items = recent.slice(0, 6).map((event) => `
      <div class="item">
        <strong>${escapeHtml(zh(RISK_ZH, event.riskLevel, event.source || "待查看"))}</strong>
        <div class="meta">${escapeHtml(fmtTime(event.eventTime))}</div>
        <div class="tag-row">${(event.categories || []).map((cat) => `<span class="tag warn">${escapeHtml(cat)}</span>`).join("")}</div>
      </div>
    `).join("");
    $("safetyPanel").innerHTML = `
      <div class="tag-row">
        ${countMap(totals.byRiskLevel, RISK_ZH)}
        <span class="tag ${escalation ? "danger" : ""}">要人跟進：${escapeHtml(escalation)} 件</span>
      </div>
      ${items || emptyNote("這 30 天沒有安全警訊——是好消息。")}
    `;
  }

  function renderPrivacy(payload) {
    const totals = (payload && payload.totals) || {};
    const recent = (payload && payload.recent) || [];
    const items = recent.slice(0, 6).map((request) => `
      <div class="item">
        <strong>${escapeHtml(zh(PRIVACY_TYPE_ZH, request.type, "申請"))}</strong>
        <div class="meta">${escapeHtml(zh(STATUS_ZH, request.status))} · ${escapeHtml(fmtTime(request.requestedAt))}</div>
        <div>${escapeHtml(request.reason || "")}</div>
      </div>
    `).join("");
    $("privacyPanel").innerHTML = `
      <div class="tag-row">${countMap(totals.byStatus, STATUS_ZH)}${countMap(totals.byType, PRIVACY_TYPE_ZH)}</div>
      ${items || emptyNote("目前沒有人申請刪帳號或要資料。")}
    `;
  }

  function renderFeedback(payload) {
    const latest = (payload && payload.latest) || [];
    const nps = payload && payload.nps !== null && payload.nps !== undefined ? payload.nps : "－";
    const items = latest.slice(0, 6).map((item) => {
      // 附圖（7/9）：只接受 data:image/ 開頭的內嵌小圖，點開看大圖
      const safeImg = typeof item.image === "string" && item.image.indexOf("data:image/") === 0 ? item.image : "";
      const imgHtml = safeImg ? `<a href="${safeImg}" target="_blank" rel="noopener"><img src="${safeImg}" alt="附圖" style="margin-top:8px;max-width:160px;max-height:120px;border-radius:8px;border:1px solid #ccc;display:block"></a>` : "";
      return `
      <div class="item">
        <strong>${escapeHtml(zh(FEEDBACK_TYPE_ZH, item.type, "意見"))}${item.score !== null && item.score !== undefined ? `　${escapeHtml(item.score)} 分` : ""}${safeImg ? "　📎有附圖" : ""}</strong>
        <div class="meta">${escapeHtml(item.category || "－")} · ${escapeHtml(fmtTime(item.createdAt))}</div>
        <div>${escapeHtml(item.text || "")}</div>
        ${imgHtml}
      </div>
    `;
    }).join("");
    $("feedbackPanel").innerHTML = `
      <div class="tag-row">
        ${countMap(payload && payload.totals, FEEDBACK_TYPE_ZH)}
        <span class="tag">推薦分數 NPS：${escapeHtml(nps)}</span>
        <span class="tag">共 ${escapeHtml((payload && payload.npsCount) || 0)} 人打分</span>
      </div>
      ${items || emptyNote("還沒有人留意見——上線後這裡會熱鬧起來。")}
    `;
  }

  function renderAudit(payload) {
    const recent = (payload && payload.recent) || [];
    const items = recent.slice(0, 8).map((event) => `
      <div class="item">
        <strong>${escapeHtml(event.eventType || "事件")}</strong>
        <div class="meta">${escapeHtml(event.targetTable || "－")} · ${escapeHtml(fmtTime(event.createdAt))}</div>
        <div>${escapeHtml(event.targetId || event.accountId || "")}</div>
      </div>
    `).join("");
    $("auditPanel").innerHTML = items || emptyNote("還沒有操作紀錄。");
  }

  function renderSummaries(payload) {
    const recent = (payload && payload.recent) || [];
    const items = recent.slice(0, 8).map((summary) => `
      <div class="item">
        <strong>${escapeHtml(fmtTime(summary.createdAt) !== "－" ? fmtTime(summary.createdAt) : (summary.id || "摘要"))}</strong>
        <div>${escapeHtml(summary.summary || "")}</div>
        <div class="tag-row">
          ${(summary.memoryTags || []).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}
          ${summary.safetyRelevant ? '<span class="tag danger">涉及安全</span>' : ""}
        </div>
      </div>
    `).join("");
    $("summariesPanel").innerHTML = items || emptyNote("還沒有聊天摘要——有人開始跟沐寧聊天後就會出現。");
  }

  function init() {
    $("apiBaseUrl").value = initialBaseUrl();
    updateEnvLabel();

    const savedToken = localStorage.getItem(ADMIN_TOKEN_KEY) || "";
    if (savedToken) {
      $("adminToken").value = savedToken;
      $("rememberToken").checked = true;
    }

    $("refreshAdmin").addEventListener("click", refreshAdmin);
    $("accountQuery").addEventListener("keydown", (event) => {
      if (event.key === "Enter") refreshAdmin();
    });
    $("clearRaw").addEventListener("click", () => setRaw({}));
    $("toggleAdvanced").addEventListener("click", () => {
      const row = $("advancedRow");
      row.hidden = !row.hidden;
    });
    $("apiBaseUrl").addEventListener("input", updateEnvLabel);
    $("toggleToken").addEventListener("click", () => {
      const field = $("adminToken");
      const showing = field.type === "text";
      field.type = showing ? "password" : "text";
      $("toggleToken").textContent = showing ? "顯示" : "隱藏";
    });

    // 有記住通行碼就直接連，開頁即看到資料
    if (savedToken) {
      refreshAdmin();
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
