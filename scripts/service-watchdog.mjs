import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

// 服務看門狗（2026-07-16 · 上線前後端完善度）
//
// 守的線：Brain／Voice／Gateway／公開網站倒了，5 分鐘內有人知道——
// 之前這些服務靜默掛掉只能等用戶回報。定時由 GitHub Actions 排程觸發，
// 告警走既有的 MUNEA_SLACK_ALERT_WEBHOOK（跟 CI 紅燈同一條線、不新增密鑰）。
//
// 跑法：node scripts/service-watchdog.mjs               巡一輪、有倒的發告警並以非 0 結束
//       node scripts/service-watchdog.mjs --dry-run     只列巡邏對象、不打網路
//
// 判定規則：每個對象有「預期回應碼」——200＝正常服務；Gateway 匿名 401＝活著且門有鎖。
// 單次失敗會隔 10 秒重試一次才算倒（避免單一網路抖動誤報）。

export const TARGETS = [
  // 2026-07-16 PR #118 重建正式兩台（STATUS 94 號）：munea-brain／munea-voice 已服役，
  // App Store 正式通知網址（/apple/notifications）也指這台 Brain——倒了要第一時間知道。
  {
    name: "Brain 正式（munea-brain＝正式 App 後端）",
    url: "https://munea-brain-491603544409.asia-east1.run.app/healthz/",
    expect: [200],
    check: "json-ok",
  },
  {
    name: "Voice 正式（munea-voice）",
    url: "https://munea-voice-491603544409.asia-east1.run.app/",
    expect: [200], // websocket 服務的 HTTP 門面；能回頁面＝程序活著
  },
  {
    name: "Brain 測試環境（munea-brain-staging）",
    url: "https://munea-brain-staging-491603544409.asia-east1.run.app/healthz/",
    expect: [200],
    check: "json-ok", // 回應要是 JSON 且 ok=true（新舊部署版本都支援 /healthz/）
  },
  {
    name: "Voice 測試環境（munea-voice-staging）",
    url: "https://munea-voice-staging-491603544409.asia-east1.run.app/",
    expect: [200], // websocket 服務的 HTTP 門面；能回頁面＝程序活著
  },
  {
    name: "Gateway 通話總機",
    url: "https://munea-call-control-fiu65jd4da-de.a.run.app/health",
    expect: [401], // 匿名必須被擋：401＝服務活著「且」門有鎖；200/404/5xx 都是異常
  },
  {
    name: "Gateway 容量看守（monitor）",
    url: "https://munea-gateway-monitor-fiu65jd4da-de.a.run.app/",
    expect: [403], // 平台層鎖門：匿名 403＝服務在、鎖也在
  },
  {
    name: "RunPod 備援控制器",
    url: "https://munea-runpod-controller-fiu65jd4da-de.a.run.app/",
    expect: [200],
    check: "json-ok",
  },
  {
    name: "公開網站 app.munea.net",
    url: "https://app.munea.net/",
    expect: [200],
  },
];

const TIMEOUT_MS = 15_000;
const RETRY_DELAY_MS = 10_000;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function probeOnce(target, fetchImpl) {
  const startedAt = performance.now();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetchImpl(target.url, { signal: controller.signal, redirect: "follow" });
    if (!target.expect.includes(res.status)) {
      return {
        ok: false,
        status: res.status,
        latencyMs: Math.round(performance.now() - startedAt),
        detail: `回應碼 ${res.status}（預期 ${target.expect.join("/")}）`,
      };
    }
    if (target.check === "json-ok") {
      const body = await res.text();
      let parsed = null;
      try {
        parsed = JSON.parse(body);
      } catch {
        return {
          ok: false,
          status: res.status,
          latencyMs: Math.round(performance.now() - startedAt),
          detail: "回應不是 JSON",
        };
      }
      if (parsed?.ok !== true) {
        return {
          ok: false,
          status: res.status,
          latencyMs: Math.round(performance.now() - startedAt),
          detail: "回應 JSON 沒有 ok=true",
        };
      }
    }
    return {
      ok: true,
      status: res.status,
      latencyMs: Math.round(performance.now() - startedAt),
      detail: `回應碼 ${res.status}`,
    };
  } catch (err) {
    const reason = err?.name === "AbortError" ? `逾時（>${TIMEOUT_MS / 1000} 秒沒回）` : `連不上（${err?.message || err}`.slice(0, 120) + "）";
    return {
      ok: false,
      status: null,
      latencyMs: Math.round(performance.now() - startedAt),
      detail: reason,
    };
  } finally {
    clearTimeout(timer);
  }
}

export async function checkTarget(target, fetchImpl, retryDelayMs = RETRY_DELAY_MS) {
  const first = await probeOnce(target, fetchImpl);
  if (first.ok) {
    return {
      name: target.name,
      url: target.url,
      ...first,
      attempts: 1,
      recoveredAfterRetry: false,
      totalLatencyMs: first.latencyMs,
    };
  }
  await sleep(retryDelayMs);
  const second = await probeOnce(target, fetchImpl);
  return {
    name: target.name,
    url: target.url,
    ...second,
    attempts: 2,
    recoveredAfterRetry: second.ok,
    totalLatencyMs: first.latencyMs + second.latencyMs,
    detail: second.ok ? `${second.detail}（第一次 ${first.detail}、重試後恢復）` : `${second.detail}（重試仍失敗）`,
  };
}

export function buildSnapshot(results, capturedAt = new Date().toISOString()) {
  const targets = results.map((result) => ({
    name: result.name,
    url: result.url,
    ok: result.ok,
    status: result.status,
    latencyMs: result.latencyMs,
    totalLatencyMs: result.totalLatencyMs,
    attempts: result.attempts,
    recoveredAfterRetry: result.recoveredAfterRetry,
    detail: result.detail,
  }));

  return {
    schema: "munea.service-watchdog.snapshot.v1",
    capturedAt,
    evidenceType: "synthetic-control-plane",
    cadence: "single-round",
    summary: {
      targetCount: targets.length,
      passed: targets.filter((target) => target.ok).length,
      failed: targets.filter((target) => !target.ok).length,
      recoveredAfterRetry: targets.filter((target) => target.recoveredAfterRetry).length,
    },
    targets,
  };
}

export async function writeSnapshot(snapshotPath, snapshot) {
  const outputPath = resolve(snapshotPath);
  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(snapshot, null, 2)}\n`, "utf8");
  return outputPath;
}

export async function runChecks(targets, fetchImpl, retryDelayMs = RETRY_DELAY_MS) {
  const results = [];
  for (const target of targets) {
    results.push(await checkTarget(target, fetchImpl, retryDelayMs));
  }
  return results;
}

export function buildAlertText(failures) {
  const lines = failures.map((f) => `• ${f.name}：${f.detail}\n  ${f.url}`);
  return `🔴 沐寧服務看門狗：${failures.length} 個服務異常\n${lines.join("\n")}\n（每 5 分鐘巡一輪；恢復後告警自然停止）`;
}

export async function sendAlert(text, webhookUrl, fetchImpl) {
  if (!webhookUrl) return false;
  const res = await fetchImpl(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  return res.ok;
}

function readOption(flag) {
  const index = process.argv.indexOf(flag);
  if (index === -1) return null;
  const value = process.argv[index + 1];
  if (!value || value.startsWith("--")) throw new Error(`${flag} requires a value`);
  return value;
}

export async function main() {
  const snapshotPath = readOption("--snapshot");
  if (process.argv.includes("--dry-run")) {
    console.log("巡邏對象（dry-run、不打網路）：");
    for (const t of TARGETS) console.log(`  ${t.name} → ${t.url}（預期 ${t.expect.join("/")}${t.check === "json-ok" ? "＋ok=true" : ""}）`);
    return;
  }
  const results = await runChecks(TARGETS, fetch);
  for (const r of results) console.log(`${r.ok ? "  OK  " : " FAIL "}${r.name}：${r.detail}`);
  if (snapshotPath) {
    const outputPath = await writeSnapshot(snapshotPath, buildSnapshot(results));
    console.log(`SNAPSHOT ${outputPath}`);
  }
  const failures = results.filter((r) => !r.ok);
  if (!failures.length) {
    console.log("✅ 全部服務正常");
    return;
  }
  const webhook = (process.env.MUNEA_SLACK_ALERT_WEBHOOK || "").trim();
  if (webhook) {
    const sent = await sendAlert(buildAlertText(failures), webhook, fetch);
    console.log(sent ? "已發 Slack 告警" : "⚠ Slack 告警發送失敗");
  } else {
    console.log("⚠ 未設 MUNEA_SLACK_ALERT_WEBHOOK、只以紅燈回報");
  }
  process.exit(1);
}

const invokedDirectly = process.argv[1] && import.meta.url.endsWith(process.argv[1].replace(/\\/g, "/").split("/").pop());
if (invokedDirectly) {
  await main();
}
