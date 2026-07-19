// 服務看門狗 · 契約測試（2026-07-16）
// 守的線：判定規則不被改壞——200/401 預期碼、json ok=true、逾時重試、告警文字與 7 日分母。
// 跑法：node scripts/test-service-watchdog.js
const FAILS = [];
const { mkdtempSync, readFileSync, rmSync, writeFileSync } = require("node:fs");
const { tmpdir } = require("node:os");
const { join } = require("node:path");
const { spawnSync } = require("node:child_process");

function check(name, cond) {
  console.log((cond ? "  OK  " : " FAIL ") + name);
  if (!cond) FAILS.push(name);
}

function fakeResponse(status, body) {
  return { status, ok: status >= 200 && status < 300, text: async () => body ?? "" };
}

async function main() {
  const mod = await import("./service-watchdog.mjs");
  const { TARGETS, checkTarget, runChecks, buildAlertText, buildSnapshot, sendAlert } = mod;

  // 契約 1：巡邏名單涵蓋現役後端服務＋公開網站
  const names = TARGETS.map((t) => t.name).join("|");
  check("名單含 Brain 測試環境", names.includes("Brain 測試環境"));
  check("名單含 Voice", names.includes("Voice"));
  check("名單含 Gateway 總機", names.includes("Gateway 通話總機"));
  check("名單含容量看守", names.includes("容量看守"));
  check("名單含 RunPod 控制器", names.includes("RunPod"));
  check("名單含公開網站", names.includes("app.munea.net"));

  // 契約 1b：正式兩台（2026-07-16 PR #118 重建、STATUS 94 號）判定規則比照 staging
  const brainProd = TARGETS.find((t) => t.name.includes("Brain 正式"));
  const voiceProd = TARGETS.find((t) => t.name.includes("Voice 正式"));
  check("名單含 Brain 正式", Boolean(brainProd));
  check("名單含 Voice 正式", Boolean(voiceProd));
  check("Brain 正式走 /healthz/＋要 ok=true", brainProd?.url.endsWith("/healthz/") && brainProd?.check === "json-ok" && JSON.stringify(brainProd?.expect) === "[200]");
  check("Voice 正式走根路徑、預期 200", voiceProd?.url.endsWith(".run.app/") && JSON.stringify(voiceProd?.expect) === "[200]");
  check("正式門牌不得指 staging", Boolean(brainProd && voiceProd) && !brainProd.url.includes("staging") && !voiceProd.url.includes("staging"));

  // 契約 2：Gateway 匿名 401＝活著（200 反而算異常＝門沒鎖）
  const gw = TARGETS.find((t) => t.name.includes("Gateway"));
  check("Gateway 預期 401", JSON.stringify(gw.expect) === "[401]");
  const gwOk = await checkTarget(gw, async () => fakeResponse(401), 0);
  check("Gateway 回 401→正常", gwOk.ok === true);
  check("成功探測含狀態／延遲／嘗試次數", gwOk.status === 401 && gwOk.latencyMs >= 0 && gwOk.attempts === 1);
  const gwOpen = await checkTarget(gw, async () => fakeResponse(200), 0);
  check("Gateway 回 200→異常（門沒鎖）", gwOpen.ok === false);

  // 契約 3：Brain 要 200＋JSON ok=true
  const brain = TARGETS.find((t) => t.name.includes("Brain 測試環境"));
  const brainOk = await checkTarget(brain, async () => fakeResponse(200, '{"ok": true}'), 0);
  check("Brain 200+ok=true→正常", brainOk.ok === true);
  const brainBad = await checkTarget(brain, async () => fakeResponse(200, '{"ok": false}'), 0);
  check("Brain ok=false→異常", brainBad.ok === false);
  const brainHtml = await checkTarget(brain, async () => fakeResponse(200, "<html>"), 0);
  check("Brain 回非 JSON→異常", brainHtml.ok === false);

  // 契約 4：第一次失敗、重試成功＝不誤報
  let calls = 0;
  const flaky = await checkTarget(brain, async () => (++calls === 1 ? fakeResponse(500) : fakeResponse(200, '{"ok": true}')), 0);
  check("單次抖動重試後→不誤報", flaky.ok === true && calls === 2);
  check("重試恢復有明確標記", flaky.recoveredAfterRetry === true && flaky.attempts === 2 && flaky.totalLatencyMs >= flaky.latencyMs);

  // 契約 5：連線炸掉（丟例外）也要變成失敗、不是整支掛掉
  const dead = await checkTarget(brain, async () => { throw new Error("ECONNREFUSED"); }, 0);
  check("連不上→判失敗不炸", dead.ok === false);

  // 契約 6：告警文字含倒掉的服務名與網址
  const results = await runChecks([brain, gw], async (url) => (url.includes("call-control") ? fakeResponse(401) : fakeResponse(503)), 0);
  const failures = results.filter((r) => !r.ok);
  check("巡邏結果只挑出倒的", failures.length === 1 && failures[0].name.includes("Brain"));
  const text = buildAlertText(failures);
  check("告警文字含服務名", text.includes("Brain 測試環境"));
  check("告警文字含網址", text.includes(brain.url));

  // 契約 7：發告警走 webhook POST；沒設 webhook 回 false 不炸
  let posted = null;
  const sent = await sendAlert("test", "https://hooks.example/x", async (url, opts) => { posted = { url, opts }; return { ok: true }; });
  check("告警 POST 到 webhook", sent === true && posted.opts.method === "POST" && posted.opts.body.includes("test"));
  const noHook = await sendAlert("test", "", async () => { throw new Error("should not be called"); });
  check("沒設 webhook→安靜回 false", noHook === false);

  // 契約 8：快照只有服務探測證據，不含 webhook、token 或回應本文
  const snapshot = buildSnapshot([gwOk, flaky, dead], "2026-07-19T00:00:00.000Z");
  const snapshotText = JSON.stringify(snapshot);
  check("快照 schema 與總數固定", snapshot.schema === "munea.service-watchdog.snapshot.v1" && snapshot.summary.targetCount === 3);
  check("快照統計重試恢復", snapshot.summary.recoveredAfterRetry === 1);
  check("快照不洩漏 webhook/token/body", !/webhook|token|ECONNREFUSED.*body/i.test(snapshotText));

  // 契約 9：7 日分母固定為 5 分鐘排程的 2,016 格；手動與未完成 run 不得灌水
  const { buildSevenDayReport } = await import("./service-slo-report.mjs");
  const from = "2026-07-12T00:00:00.000Z";
  const to = "2026-07-19T00:00:00.000Z";
  const startMs = new Date(from).getTime();
  const scheduledSuccesses = Array.from({ length: 2016 }, (_, index) => ({
    id: index + 1,
    event: "schedule",
    status: "completed",
    conclusion: "success",
    run_started_at: new Date(startMs + index * 5 * 60 * 1000).toISOString(),
  }));
  const perfect = buildSevenDayReport(scheduledSuccesses, { from, to });
  check("7 日 5 分鐘分母＝2016", perfect.denominator.expectedSlots === 2016);
  check("完整成功＝100% coverage/availability", perfect.metrics.coveragePct === 100 && perfect.metrics.conservativeAvailabilityPct === 100);
  check("完整 7 日證據可用", perfect.evidenceReady === true);

  const mixedRuns = [
    ...scheduledSuccesses.slice(0, 2000),
    { event: "workflow_dispatch", status: "completed", conclusion: "success", run_started_at: "2026-07-18T23:50:00.000Z" },
    { event: "schedule", status: "in_progress", conclusion: null, run_started_at: "2026-07-18T23:55:00.000Z" },
  ];
  mixedRuns[0] = { ...mixedRuns[0], conclusion: "failure" };
  const conservative = buildSevenDayReport(mixedRuns, { from, to });
  check("手動與未完成 run 不進完成分母", conservative.denominator.completedScheduledSlots === 2000);
  check("缺排程會降低保守可用率", conservative.metrics.observedSuccessPct > conservative.metrics.conservativeAvailabilityPct);
  check("缺 16 格被明確列出", conservative.denominator.missingScheduledSlots === 16);
  check("報表不保留 run 明細或 id", !Object.hasOwn(conservative, "runs") && !JSON.stringify(conservative).includes('"id"'));

  // 契約 10：每日證據 workflow 只能讀，事故快照仍要留下、最後仍須紅燈
  const workflow = readFileSync(".github/workflows/service-slo-report.yml", "utf8");
  check("證據 workflow 權限只有 read", /actions:\s*read/.test(workflow) && /contents:\s*read/.test(workflow) && !/^\s+\w+:\s*write\s*$/m.test(workflow));
  check("當下探測失敗仍繼續產報表", /id:\s*current[\s\S]*?continue-on-error:\s*true/.test(workflow));
  check("artifact 即使事故也會上傳", /Upload evidence artifact[\s\S]*?if:\s*always\(\)/.test(workflow));
  check("事故不會被 continue-on-error 吃掉", /Preserve current outage signal[\s\S]*?steps\.current\.outcome != 'success'/.test(workflow));

  // 契約 11：Cloud Monitoring manifest 與 watchdog 同一組 8 targets，且預設只能 plan
  const uptimeManifest = JSON.parse(readFileSync("deploy/monitoring/uptime-checks.json", "utf8"));
  check("Cloud uptime schema／project 固定", uptimeManifest.schema === "munea.cloud-monitoring.uptime.v1" && uptimeManifest.project === "gen-lang-client-0229303523");
  check("Cloud uptime 為 5 分鐘／三區／15 秒", uptimeManifest.periodMinutes === 5 && uptimeManifest.timeoutSeconds === 15 && uptimeManifest.regions.length === 3);
  check("Cloud uptime target id 唯一", new Set(uptimeManifest.targets.map((target) => target.id)).size === uptimeManifest.targets.length);
  const cloudTargets = uptimeManifest.targets.map((target) => ({
    url: `https://${target.host}${target.path}`,
    expect: target.statusCodes,
    check: target.jsonOk ? "json-ok" : undefined,
  }));
  const targetContract = (target) => `${target.url}|${target.expect.join(",")}|${target.check || ""}`;
  check("Cloud uptime 與 Node watchdog 8 targets 完全對齊", cloudTargets.length === 8 && JSON.stringify(cloudTargets.map(targetContract).sort()) === JSON.stringify(TARGETS.map(targetContract).sort()));
  const monthlyExecutions = cloudTargets.length * uptimeManifest.regions.length * (60 / uptimeManifest.periodMinutes) * 24 * 30;
  check("Cloud uptime 月執行數低於官方 100 萬免費額度", monthlyExecutions === 207360 && monthlyExecutions < 1000000);

  const uptimeScript = readFileSync("scripts/cloud-monitoring-uptime.ps1", "utf8");
  check("Cloud uptime apply 必須明確開關", /\[switch\]\$Apply/.test(uptimeScript) && /if \(\$Apply\)/.test(uptimeScript) && /PLAN ONLY: no Cloud Monitoring resources were changed/.test(uptimeScript));
  check("Cloud uptime project 釘死且不自動刪除", uptimeScript.includes("gen-lang-client-0229303523") && !/uptime[\"',\s]+delete/i.test(uptimeScript));
  check("Cloud uptime host drift 必須人工 migration", /Host drift[\s\S]*explicit reviewed migration/.test(uptimeScript));

  if (process.platform === "win32") {
    const fakeDir = mkdtempSync(join(tmpdir(), "munea-fake-gcloud-"));
    const fakeGcloud = join(fakeDir, "gcloud.ps1");
    try {
      writeFileSync(fakeGcloud, [
        "param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Remaining)",
        "if ($Remaining -contains 'list-configs') { Write-Output '[{\"name\":\"projects/test/uptimeCheckConfigs/fake-brain\",\"displayName\":\"Munea Brain prod health\",\"monitoredResource\":{\"labels\":{\"host\":\"munea-brain-491603544409.asia-east1.run.app\"}},\"userLabels\":{\"managed_by\":\"munea_repo\",\"component\":\"service_slo\",\"target_id\":\"brain-prod\"}}]'; exit 0 }",
        "if (($Remaining -contains 'update') -and -not ($Remaining -contains '--set-status-codes')) { [Console]::Error.WriteLine('update missing --set-status-codes'); exit 2 }",
        "if (($Remaining -contains 'update') -and ($Remaining -contains '--update-user-labels')) { [Console]::Error.WriteLine('update must preserve create-time user labels'); exit 2 }",
        "if (($Remaining -contains 'create') -and -not ($Remaining -contains '--status-codes')) { [Console]::Error.WriteLine('create missing --status-codes'); exit 2 }",
        "[Console]::Error.WriteLine('Created uptime fake-success')",
        "exit 0",
      ].join("\n"), "utf8");
      const fakeApply = spawnSync("powershell", [
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", "scripts/cloud-monitoring-uptime.ps1",
        "-GcloudPath", fakeGcloud,
        "-Apply",
      ], { cwd: process.cwd(), encoding: "utf8" });
      check("gcloud update 保留建立期 labels，create/update 旗標與成功 stderr 均可完成 apply", fakeApply.status === 0 && fakeApply.stdout.includes("ENSURE update brain-prod") && fakeApply.stdout.includes("APPLIED: ensured 8 uptime checks"));
    } finally {
      rmSync(fakeDir, { recursive: true, force: true });
    }
  }

  console.log();
  if (FAILS.length) {
    console.log(`❌ ${FAILS.length} 項未過：` + FAILS.join("、"));
    process.exit(1);
  }
  console.log("✅ 服務看門狗契約全過");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
