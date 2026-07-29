"use strict";

const fs = require("fs");
const http = require("http");
const path = require("path");

const root = path.resolve(__dirname, "..", "web");
const portArg = process.argv.indexOf("--port");
const port = portArg >= 0 ? Number(process.argv[portArg + 1]) : 4175;
const now = "2026-07-28T08:00:00Z";

function meta(source) {
  return {
    schema: "munea.admin-data-meta.v1",
    metricVersion: "local-i18n-fixture.v1",
    generatedAt: now,
    dataAsOf: now,
    status: "ready",
    degraded: false,
    degradationReasons: [],
    freshness: { status: "fresh" },
    sources: [source],
  };
}

function account(id, name, localeContext, plan, points, status) {
  return {
    accountId: id,
    accountName: `${name} household`,
    locale: localeContext.uiLocale,
    preferredLanguages: [localeContext.conversationLocale, localeContext.uiLocale],
    localeContext,
    createdAt: "2026-06-01T08:00:00Z",
    updatedAt: "2026-07-28T07:30:00Z",
    familyGroup: { id: `family-${id}`, name: `${name} family` },
    primaryPerson: {
      id: `person-${id}`,
      displayName: name,
      relationship: "elder",
      locale: localeContext.conversationLocale,
      timezone: localeContext.timeZone,
      regionCode: localeContext.countryCode,
    },
    companion: { templateId: "nening-real-female", displayName: "Munea" },
    familyMembers: { count: 3, byRole: { elder: 1, child: 2 } },
    plan,
    points,
    status,
    usage: {
      totalMinutes: 86,
      voiceMinutes: 54,
      avatarMinutes: 32,
      lastActiveAt: "2026-07-28T07:30:00Z",
    },
    isTestAccount: false,
  };
}

const accounts = [
  account("tw-001", "Mei", {
    version: 1,
    uiLocale: "zh-TW",
    conversationLocale: "zh-TW",
    preferredLanguages: ["zh-TW", "en"],
    countryCode: "TW",
    timeZone: "Asia/Taipei",
    units: "metric",
    currency: "TWD",
    safetyRegion: "TW",
    legalRegion: "TW",
    dataRegion: "tw-primary",
  }, "plus", 120, "on"),
  account("us-001", "Grace", {
    version: 1,
    uiLocale: "en",
    conversationLocale: "en",
    preferredLanguages: ["en", "es"],
    countryCode: "US",
    timeZone: "America/Los_Angeles",
    units: "us",
    currency: "USD",
    safetyRegion: "US",
    legalRegion: "US",
    dataRegion: "us-central",
  }, "pro", 240, "on"),
  account("jp-001", "Yuki", {
    version: 1,
    uiLocale: "ja",
    conversationLocale: "en",
    preferredLanguages: ["en", "ja"],
    countryCode: "JP",
    timeZone: "Asia/Tokyo",
    units: "metric",
    currency: "JPY",
    safetyRegion: "JP",
    legalRegion: "JP",
    dataRegion: "jp-primary",
  }, "plus", 64, "idle"),
  account("mx-001", "Sofía", {
    version: 1,
    uiLocale: "es",
    conversationLocale: "es",
    preferredLanguages: ["es", "en"],
    countryCode: "MX",
    timeZone: "America/Mexico_City",
    units: "metric",
    currency: "MXN",
    safetyRegion: "MX",
    legalRegion: "MX",
    dataRegion: "us-central",
  }, "free", 5, "off"),
];

const payloads = {
  "/admin/north-star": {
    ok: true,
    windowDays: 30,
    meaningfulCompanionDays: 42,
    activePeople: 4,
    voiceSessionSuccessRate: 0.96,
    routineCompletions: 18,
    familyInteractions: 23,
  },
  "/admin/usage": {
    ok: true,
    windowDays: 30,
    totals: { events: 86, voiceMinutes: 54, avatarMinutes: 32, voiceSessionSuccessRate: 0.96 },
    eventCounts: {},
    daily: [
      { date: "2026-07-25", events: 20, meaningfulEvents: 8, voiceMinutes: 14, avatarMinutes: 8 },
      { date: "2026-07-26", events: 26, meaningfulEvents: 11, voiceMinutes: 18, avatarMinutes: 10 },
      { date: "2026-07-27", events: 40, meaningfulEvents: 15, voiceMinutes: 22, avatarMinutes: 14 }
    ],
  },
  "/admin/accounts": {
    ok: true,
    accounts,
    count: accounts.length,
    hiddenTestAccountCount: 0,
  },
  "/admin/subscription-metrics": {
    ok: true,
    windowDays: 30,
    newSubscriptions: 3,
    pointsPurchases: 5,
    pointsTotal: 500,
    registrations: 12,
    freeToPaidConversion: 0.25,
    mrr: 2397,
    churnRate: null,
    pending: {},
  },
  "/admin/credits": {
    ok: true,
    walletSummary: { includedMonthly: 300, purchased: 129, total: 429 },
    recentTransactions: [],
  },
  "/admin/feedback": { ok: true, latest: [], totals: {}, nps: null, npsCount: 0 },
  "/admin/safety-events": {
    ok: true,
    totals: {
      requiresHumanEscalation: 1,
      byRiskLevel: { high: 1, low: 1 },
    },
    recent: [
      {
        id: "safety-1",
        riskLevel: "high",
        categories: ["self_harm_signal"],
        personId: "person-jp-001",
        eventTime: "2026-07-28T07:20:00Z",
        requiresHumanEscalation: true,
      },
      {
        id: "safety-2",
        riskLevel: "low",
        categories: ["low_mood"],
        personId: "person-mx-001",
        eventTime: "2026-07-27T09:00:00Z",
        requiresHumanEscalation: false,
      }
    ],
  },
  "/admin/privacy-requests": { ok: true, recent: [] },
  "/admin/conversation-summaries": { ok: true, recent: [] },
  "/admin/audit-events": { ok: true, recent: [] },
  "/admin/medication-adherence": { ok: true, windowDays: 30, totals: {}, daily: [], people: [] },
  "/admin/family-health": { ok: true, windowDays: 30, totals: {}, daily: [], households: [] },
  "/admin/mood-trend": { ok: true, windowDays: 30, totals: {}, daily: [], people: [] },
  "/admin/bond-depth": { ok: true, windowDays: 30, stuckDays: 14, totals: {}, stages: {}, people: [] },
  "/admin/growth-metrics": { ok: true, windowDays: 30, stickiness: {}, retention: [], funnel: [] },
};

for (const [endpoint, payload] of Object.entries(payloads)) {
  payload.meta = meta(`local-fixture:${endpoint}`);
}

const mime = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
};

function json(res, status, body) {
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
    "access-control-allow-origin": "*",
  });
  res.end(JSON.stringify(body));
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${port}`);
  if (req.method === "POST" && url.pathname === "/admin/login") {
    json(res, 200, { ok: true, token: "local-i18n-fixture-token" });
    return;
  }
  if (req.method === "POST" && payloads[url.pathname]) {
    json(res, 200, payloads[url.pathname]);
    return;
  }
  if (req.method === "POST" && url.pathname.startsWith("/admin/")) {
    json(res, 200, { ok: true, meta: meta(`local-fixture:${url.pathname}`) });
    return;
  }

  const relative = url.pathname === "/" ? "admin.html" : decodeURIComponent(url.pathname.slice(1));
  const resolved = path.resolve(root, relative);
  if (resolved !== root && !resolved.startsWith(root + path.sep)) {
    res.writeHead(403);
    res.end("forbidden");
    return;
  }
  fs.readFile(resolved, (error, body) => {
    if (error) {
      res.writeHead(error.code === "ENOENT" ? 404 : 500);
      res.end(error.code || "error");
      return;
    }
    res.writeHead(200, {
      "content-type": mime[path.extname(resolved).toLowerCase()] || "application/octet-stream",
      "cache-control": "no-store",
    });
    res.end(body);
  });
});

server.listen(port, "127.0.0.1", () => {
  console.log(`Munea admin i18n fixture listening on http://127.0.0.1:${port}/admin.html`);
});

function shutdown() {
  server.close(() => process.exit(0));
}
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
