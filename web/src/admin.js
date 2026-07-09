(function () {
  const ADMIN_BASE_KEY = "munea.admin.apiBaseUrl";
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

  const $ = (id) => document.getElementById(id);

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

  function setStatus(text, state) {
    const node = $("connectionStatus");
    node.textContent = text;
    node.className = "status-pill" + (state ? ` ${state}` : "");
  }

  function setRaw(payload) {
    $("rawOutput").textContent = JSON.stringify(payload || {}, null, 2);
  }

  function fmt(value, fallback = "-") {
    if (value === null || value === undefined || value === "") return fallback;
    return String(value);
  }

  function countMap(map) {
    const source = map || {};
    return Object.keys(source)
      .sort()
      .map((key) => `<span class="tag">${escapeHtml(key)}: ${escapeHtml(source[key])}</span>`)
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
      throw new Error(`${endpoint}: ${code}`);
    }

    return payload;
  }

  async function refreshAdmin() {
    const baseUrl = normalizeBaseUrl($("apiBaseUrl").value);
    const token = $("adminToken").value.trim();
    const accountQuery = $("accountQuery").value.trim();

    if (!baseUrl) {
      setStatus("API URL required", "error");
      return;
    }
    if (!token) {
      setStatus("Admin token required", "error");
      return;
    }

    localStorage.setItem(ADMIN_BASE_KEY, baseUrl);
    setStatus("Loading", "");

    const requests = { ...ENDPOINTS };
    requests.accounts = {
      ...ENDPOINTS.accounts,
      body: { ...ENDPOINTS.accounts.body, query: accountQuery },
    };

    try {
      const entries = await Promise.all(
        Object.entries(requests).map(async ([key, config]) => {
          const payload = await postAdmin(baseUrl, token, config.path, config.body);
          return [key, payload];
        })
      );
      const data = Object.fromEntries(entries);
      renderAll(data);
      setRaw(data);
      setStatus("Connected", "ok");
    } catch (error) {
      setStatus(error.message || "Request failed", "error");
      setRaw({ ok: false, error: error.message });
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
    $("metricBackend").textContent = backend.provider ? fmt(backend.provider) : fmt(backend.enabled);
  }

  function renderAccounts(payload) {
    const accounts = (payload && payload.accounts) || [];
    if (!accounts.length) {
      $("accountsPanel").innerHTML = '<div class="muted">No accounts found.</div>';
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
          <td>${escapeHtml(family.name || family.id)}</td>
          <td>${escapeHtml(person.displayName || person.id)}</td>
          <td>${escapeHtml(companion.displayName || companion.templateId)}</td>
          <td>${escapeHtml(members.count || 0)}</td>
          <td>${escapeHtml(account.updatedAt || account.createdAt || "-")}</td>
        </tr>
      `;
    }).join("");
    $("accountsPanel").innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Account</th>
            <th>Family</th>
            <th>Primary Person</th>
            <th>Companion</th>
            <th>Members</th>
            <th>Updated</th>
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
        <strong>${escapeHtml(payload && payload.activePlan ? payload.activePlan : "unknown plan")}</strong>
        <div class="meta">status: ${escapeHtml(subscription.status || "unknown")}</div>
        <div class="tag-row">
          <span class="tag">monthly ${escapeHtml(wallet.monthlyRemaining ?? "-")}</span>
          <span class="tag">purchased ${escapeHtml(wallet.purchasedRemaining ?? "-")}</span>
          <span class="tag">total ${escapeHtml(wallet.totalRemaining ?? "-")}</span>
        </div>
      </div>
      <div class="item">
        <strong>Entitlements</strong>
        <div class="tag-row">${countMap(entitlements)}</div>
      </div>
    `;
  }

  function renderSafety(payload) {
    const totals = (payload && payload.totals) || {};
    const recent = (payload && payload.recent) || [];
    const items = recent.slice(0, 6).map((event) => `
      <div class="item">
        <strong>${escapeHtml(event.riskLevel || event.source || "review")}</strong>
        <div class="meta">${escapeHtml(event.eventTime || "-")}</div>
        <div class="tag-row">${(event.categories || []).map((cat) => `<span class="tag warn">${escapeHtml(cat)}</span>`).join("")}</div>
      </div>
    `).join("");
    $("safetyPanel").innerHTML = `
      <div class="tag-row">
        ${countMap(totals.byRiskLevel)}
        <span class="tag danger">escalation ${escapeHtml(totals.requiresHumanEscalation || 0)}</span>
      </div>
      ${items || '<div class="muted">No safety events.</div>'}
    `;
  }

  function renderPrivacy(payload) {
    const totals = (payload && payload.totals) || {};
    const recent = (payload && payload.recent) || [];
    const items = recent.slice(0, 6).map((request) => `
      <div class="item">
        <strong>${escapeHtml(request.type || "request")}</strong>
        <div class="meta">${escapeHtml(request.status || "-")} · ${escapeHtml(request.requestedAt || "-")}</div>
        <div>${escapeHtml(request.reason || "")}</div>
      </div>
    `).join("");
    $("privacyPanel").innerHTML = `
      <div class="tag-row">${countMap(totals.byStatus)}${countMap(totals.byType)}</div>
      ${items || '<div class="muted">No privacy requests.</div>'}
    `;
  }

  function renderFeedback(payload) {
    const latest = (payload && payload.latest) || [];
    const nps = payload && payload.nps !== null && payload.nps !== undefined ? payload.nps : "-";
    const items = latest.slice(0, 6).map((item) => {
      // 附圖（7/9）：只接受 data:image/ 開頭的內嵌小圖，點開看大圖
      const safeImg = typeof item.image === "string" && item.image.indexOf("data:image/") === 0 ? item.image : "";
      const imgHtml = safeImg ? `<a href="${safeImg}" target="_blank" rel="noopener"><img src="${safeImg}" alt="附圖" style="margin-top:8px;max-width:160px;max-height:120px;border-radius:8px;border:1px solid #ccc;display:block"></a>` : "";
      return `
      <div class="item">
        <strong>${escapeHtml(item.type || "feedback")}${item.score !== null && item.score !== undefined ? ` · ${escapeHtml(item.score)}` : ""}${safeImg ? " · 📎圖" : ""}</strong>
        <div class="meta">${escapeHtml(item.category || "-")} · ${escapeHtml(item.createdAt || "-")}</div>
        <div>${escapeHtml(item.text || "")}</div>
        ${imgHtml}
      </div>
    `;
    }).join("");
    $("feedbackPanel").innerHTML = `
      <div class="tag-row">
        ${countMap(payload && payload.totals)}
        <span class="tag">NPS ${escapeHtml(nps)}</span>
        <span class="tag">n ${escapeHtml((payload && payload.npsCount) || 0)}</span>
      </div>
      ${items || '<div class="muted">No feedback yet.</div>'}
    `;
  }

  function renderAudit(payload) {
    const recent = (payload && payload.recent) || [];
    const items = recent.slice(0, 8).map((event) => `
      <div class="item">
        <strong>${escapeHtml(event.eventType || "event")}</strong>
        <div class="meta">${escapeHtml(event.targetTable || "-")} · ${escapeHtml(event.createdAt || "-")}</div>
        <div>${escapeHtml(event.targetId || event.accountId || "")}</div>
      </div>
    `).join("");
    $("auditPanel").innerHTML = items || '<div class="muted">No audit events.</div>';
  }

  function renderSummaries(payload) {
    const recent = (payload && payload.recent) || [];
    const items = recent.slice(0, 8).map((summary) => `
      <div class="item">
        <strong>${escapeHtml(summary.createdAt || summary.id || "summary")}</strong>
        <div>${escapeHtml(summary.summary || "")}</div>
        <div class="tag-row">
          ${(summary.memoryTags || []).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}
          ${summary.safetyRelevant ? '<span class="tag danger">safety</span>' : ""}
        </div>
      </div>
    `).join("");
    $("summariesPanel").innerHTML = items || '<div class="muted">No conversation summaries.</div>';
  }

  function init() {
    $("apiBaseUrl").value = initialBaseUrl();
    $("refreshAdmin").addEventListener("click", refreshAdmin);
    $("accountQuery").addEventListener("keydown", (event) => {
      if (event.key === "Enter") refreshAdmin();
    });
    $("clearRaw").addEventListener("click", () => setRaw({}));
  }

  document.addEventListener("DOMContentLoaded", init);
})();
