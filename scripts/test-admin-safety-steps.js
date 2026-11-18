"use strict";

// 後台「安全守護警示」：標了受暴的那幾筆，處理步驟要換成「不要聯絡家人或家庭圈的人」——加害人可能就是家人
// （#727 信任關卡複審）。真的把 admin.js 的 renderSafety 拿出來跑：一般事件照舊、受暴類那一筆換步驟、
// 一般步驟旁邊標出例外。跑法：node scripts/test-admin-safety-steps.js

const assert = require("assert");
const fs = require("fs");
const path = require("path");

const js = fs.readFileSync(path.join(__dirname, "..", "web", "src", "admin.js"), "utf8");
const start = js.indexOf("  // 受暴類（提到受暴／AI 判過受暴）");
const end = js.indexOf("  function renderMedication(){");
assert(start > 0 && end > start, "renderSafety（連同 isAbuseEvent／ABUSE_STEPS_HTML）找不到");
const source = js.slice(start, end);

const esc = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;").replace(/'/g, "&#39;");

function render(safety) {
  const factory = new Function(
    "D", "kpiRow", "n", "principle", "card", "emptyBox", "esc", "zh", "RISK_ZH", "fmtTime",
    `${source}\nreturn renderSafety;`,
  );
  const renderSafety = factory(
    () => ({ safety }),
    () => "",
    (x) => String(x),
    (text) => `<div class="principle">${text}</div>`,
    (title, note, body) => `<section data-card="${title}">${body}</section>`,
    (text) => `<div class="empty-note">${esc(text)}</div>`,
    esc,
    (map, value, fallback) => value || fallback,
    {},
    (value) => String(value),
  );
  return renderSafety();
}

function rows(html) {
  return html.split('<div class="row-item').slice(1);
}

const ABUSE_STEP = "不要聯絡家人或家庭圈的人";
const HOTLINE_STEP = "必要時協助撥 113 保護專線或轉社工";
const FAMILY_STEP = "聯繫家庭圈指定的人";
const EXCEPTION_NOTE = "標了受暴的那幾筆不照這個步驟";

const base = { riskLevel: "high", categories: ["medical_emergency_signal"], personId: "p", eventTime: "2026-11-18T00:00:00Z" };

// 一、受暴類那一筆換步驟；一般那一筆照舊；一般步驟旁標出例外
{
  const html = render({
    totals: {},
    recent: [
      { ...base, id: "abuse", categories: ["protection_event"], handling: "abuse", protectionMentioned: true },
      { ...base, id: "plain", handling: "standard" },
    ],
  });
  const [abuseRow, plainRow] = rows(html);
  assert(abuseRow.includes(ABUSE_STEP), "受暴類那一筆要寫「不要聯絡家人或家庭圈的人」");
  assert(abuseRow.includes(HOTLINE_STEP), "受暴類那一筆要寫 113 保護專線／轉社工");
  assert(!abuseRow.includes(FAMILY_STEP), "受暴類那一筆不能出現「聯繫家庭圈指定的人」");
  assert(!plainRow.includes(ABUSE_STEP), "一般事件照舊、不出現受暴類步驟");
  assert(html.includes(FAMILY_STEP), "一般步驟照舊");
  assert(html.includes(EXCEPTION_NOTE), "清單裡有受暴類時，一般步驟旁要標出例外");
}

// 二、舊回應沒有 handling 欄：看「AI 判過受暴」「提到受暴」兩個旗標
{
  for (const flags of [{ abuseConfirmed: true }, { protectionMentioned: true }]) {
    const [row] = rows(render({ totals: {}, recent: [{ ...base, ...flags }] }));
    assert(row.includes(ABUSE_STEP), `沒有 handling 也要看旗標：${JSON.stringify(flags)}`);
  }
}

// 三、清單裡沒有受暴類：不出現例外那句，也不出現受暴類步驟
{
  const html = render({ totals: {}, recent: [{ ...base, handling: "standard" }] });
  assert(!html.includes(EXCEPTION_NOTE));
  assert(!html.includes(ABUSE_STEP));
}

// 四、新字串四語都有（翻譯檔 exact 字串）
for (const locale of ["en", "ja", "es"]) {
  const catalog = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "web", "src", "i18n", `admin-${locale}.json`), "utf8"));
  for (const text of ["先確認本人安全", ABUSE_STEP, HOTLINE_STEP, EXCEPTION_NOTE, "——加害人可能就是家人，照那一筆寫的處理。"]) {
    assert(catalog.exact[text], `${locale} 少了：${text}`);
  }
}

console.log("Admin safety abuse-handling steps OK");
