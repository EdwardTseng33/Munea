import { mkdir, readFile, writeFile } from "node:fs/promises";
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
    // 2026-07-29 事故後升級：只檢查「有沒有回應」是不夠的。當晚模型額度用完，
    // 大腦跟聊聊兩台都啞了、真的用戶打不通，八盞燈卻全綠——因為誰都沒在問
    // 「她還講不講得出話」。ai-alive 會看 /healthz 回來的 ai 那一格。
    check: "ai-alive",
    userFacing: true,
  },
  {
    name: "Voice 正式（munea-voice）",
    url: "https://munea-voice-491603544409.asia-east1.run.app/",
    expect: [200], // websocket 服務的 HTTP 門面；能回頁面＝程序活著
    userFacing: true,
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
    name: "公開網站 munea.net（正門）",
    url: "https://munea.net/",
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
    if (target.check === "json-ok" || target.check === "ai-alive") {
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
      if (target.check === "ai-alive") {
        const ai = parsed?.ai;
        // 沒有 ai 這格＝跑的是舊版，先不當成倒（升級期間不誤報）
        if (ai && ai.ok !== true) {
          const why = ai.state === "unknown"
            ? "問不出她講不講得出話（太久沒有真流量、探測也沒成功）"
            : `她講不出話了：${(ai.lastError || "").slice(0, 120)}`;
          return {
            ok: false,
            status: res.status,
            latencyMs: Math.round(performance.now() - startedAt),
            detail: `服務活著、但${why}`,
          };
        }
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
  // 2026-07-29 分級：正式的大腦／聊聊倒了＝使用者現在打不通、叫不到人，
  // 半夜也要叫得醒（<!channel> 才穿得透手機的免打擾）。其他（測試機、周邊）
  // 安靜進頻道、早上看就好——只有真的會咬人的才吵，狼來了幾次以後就沒人理了。
  if (failures.some((f) => f.userFacing)) {
    return `<!channel> 🚨 沐寧服務中斷：${failures.length} 個服務異常（使用者現在打不通）\n`
      + `${lines.join("\n")}\n（每 5 分鐘巡一輪；恢復後告警自然停止）`;
  }
  return `🔴 沐寧服務看門狗：${failures.length} 個服務異常\n${lines.join("\n")}\n（每 5 分鐘巡一輪；恢復後告警自然停止）`;
}

// ─── 講過就不要再講一遍 ────────────────────────────────────────────────────────
// Edward 2026-08-19：「不要再一直發同樣訊息」。原本每 5 分鐘無條件重發一次——
// Gemini 儲值用完那次連發了 60 幾則一模一樣的，訊息洗到後面沒有人會看。
// 狼來了喊太多次，真的來的時候就沒人理了。
//
// 新規矩三條：
//   ① 剛壞掉      → 發（這是真正的新消息）
//   ② 一直壞著    → 閉嘴，只在滿 REMIND_AFTER_MS（預設 1 小時）補一則提醒，
//                    並註明已經壞多久——讓人知道「還沒好」但不會被洗版
//   ③ 修好了      → 發一則平安，然後把記錄清掉
//
// 狀態存在跨輪的小檔案裡（GitHub Actions 用 cache 帶著走）。檔案讀不到＝當成
// 「以前都好好的」，最多就是多發一則，不會漏報——寧可多講一次，不可以不講。
export const REMIND_AFTER_MS = 60 * 60 * 1000;

export async function loadAlertState(statePath) {
  if (!statePath) return {};
  try {
    return JSON.parse(await readFile(resolve(statePath), "utf8")) || {};
  } catch {
    return {};   // 第一次跑／檔案壞掉 → 當成全部正常，寧可多發一則
  }
}

export async function saveAlertState(statePath, state) {
  if (!statePath) return null;
  const outputPath = resolve(statePath);
  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(state, null, 2)}\n`, "utf8");
  return outputPath;
}

// 純函式，方便驗：吃「這輪誰倒了」＋「上輪記到什麼」，吐「要發什麼、下輪記什麼」。
export function decideAlerts(results, prevState = {}, nowMs = Date.now(), remindAfterMs = REMIND_AFTER_MS) {
  const failing = results.filter((r) => !r.ok);
  const nextState = {};
  const fresh = [];      // 剛壞掉的
  const remind = [];     // 壞很久、該補一則提醒的
  for (const f of failing) {
    const prev = prevState[f.name];
    if (!prev) {
      nextState[f.name] = { since: nowMs, lastAlertAt: nowMs };
      fresh.push(f);
    } else if (nowMs - (prev.lastAlertAt || 0) >= remindAfterMs) {
      nextState[f.name] = { since: prev.since || nowMs, lastAlertAt: nowMs };
      remind.push({ ...f, downForMs: nowMs - (prev.since || nowMs) });
    } else {
      nextState[f.name] = prev;   // 還在壞、但講過了 → 這輪安靜
    }
  }
  const failingNames = new Set(failing.map((f) => f.name));
  const recovered = Object.keys(prevState).filter((name) => !failingNames.has(name));
  return { fresh, remind, recovered, nextState };
}

export function buildRecoveryText(names) {
  return `✅ 沐寧服務恢復：${names.join("、")}（先前的告警可以忽略了）`;
}

export function buildReminderText(items) {
  const lines = items.map((f) => {
    const mins = Math.round((f.downForMs || 0) / 60000);
    const dur = mins >= 60 ? `${Math.floor(mins / 60)} 小時 ${mins % 60} 分` : `${mins} 分鐘`;
    return `• ${f.name}：已經壞 ${dur} 還沒好\n  ${f.url}`;
  });
  return `🔴 沐寧服務仍未恢復\n${lines.join("\n")}\n（這是每小時一次的提醒，不是新事件）`;
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
  const webhook = (process.env.MUNEA_SLACK_ALERT_WEBHOOK || "").trim();

  // 講過就不要再講一遍（Edward 2026-08-19）。沒帶 --state 就退回舊行為（每輪都發），
  // 這樣單獨手動跑一次也照樣會通知、不會因為少一個參數就變成靜音。
  const statePath = readOption("--state");
  const prevState = await loadAlertState(statePath);
  const { fresh, remind, recovered, nextState } = decideAlerts(results, prevState);
  if (statePath) await saveAlertState(statePath, nextState);

  if (!webhook) {
    console.log("⚠ 未設 MUNEA_SLACK_ALERT_WEBHOOK、只以紅燈回報");
  } else if (!statePath) {
    if (failures.length) {
      const sent = await sendAlert(buildAlertText(failures), webhook, fetch);
      console.log(sent ? "已發 Slack 告警" : "⚠ Slack 告警發送失敗");
    }
  } else {
    if (recovered.length) {
      await sendAlert(buildRecoveryText(recovered), webhook, fetch);
      console.log(`已發恢復通知：${recovered.join("、")}`);
    }
    if (fresh.length) {
      await sendAlert(buildAlertText(fresh), webhook, fetch);
      console.log(`已發新故障告警：${fresh.map((f) => f.name).join("、")}`);
    }
    if (remind.length) {
      await sendAlert(buildReminderText(remind), webhook, fetch);
      console.log(`已發每小時提醒：${remind.map((f) => f.name).join("、")}`);
    }
    if (!recovered.length && !fresh.length && !remind.length) {
      console.log(failures.length ? "還在壞、但已經講過了 → 這輪不吵" : "✅ 全部服務正常");
    }
  }

  if (!failures.length) {
    console.log("✅ 全部服務正常");
    return;
  }
  process.exit(1);
}

const invokedDirectly = process.argv[1] && import.meta.url.endsWith(process.argv[1].replace(/\\/g, "/").split("/").pop());
if (invokedDirectly) {
  await main();
}
