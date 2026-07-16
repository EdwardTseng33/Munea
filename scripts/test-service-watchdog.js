// 服務看門狗 · 契約測試（2026-07-16）
// 守的線：判定規則不被改壞——200/401 預期碼、json ok=true、逾時重試、告警文字含服務名。
// 跑法：node scripts/test-service-watchdog.js
const FAILS = [];

function check(name, cond) {
  console.log((cond ? "  OK  " : " FAIL ") + name);
  if (!cond) FAILS.push(name);
}

function fakeResponse(status, body) {
  return { status, ok: status >= 200 && status < 300, text: async () => body ?? "" };
}

async function main() {
  const mod = await import("./service-watchdog.mjs");
  const { TARGETS, checkTarget, runChecks, buildAlertText, sendAlert } = mod;

  // 契約 1：巡邏名單涵蓋現役後端服務＋公開網站
  const names = TARGETS.map((t) => t.name).join("|");
  check("名單含 Brain（現役後端）", names.includes("Brain 管家腦"));
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
  const gwOpen = await checkTarget(gw, async () => fakeResponse(200), 0);
  check("Gateway 回 200→異常（門沒鎖）", gwOpen.ok === false);

  // 契約 3：Brain 要 200＋JSON ok=true
  const brain = TARGETS.find((t) => t.name.includes("Brain 管家腦"));
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

  // 契約 5：連線炸掉（丟例外）也要變成失敗、不是整支掛掉
  const dead = await checkTarget(brain, async () => { throw new Error("ECONNREFUSED"); }, 0);
  check("連不上→判失敗不炸", dead.ok === false);

  // 契約 6：告警文字含倒掉的服務名與網址
  const results = await runChecks([brain, gw], async (url) => (url.includes("call-control") ? fakeResponse(401) : fakeResponse(503)), 0);
  const failures = results.filter((r) => !r.ok);
  check("巡邏結果只挑出倒的", failures.length === 1 && failures[0].name.includes("Brain"));
  const text = buildAlertText(failures);
  check("告警文字含服務名", text.includes("Brain 管家腦"));
  check("告警文字含網址", text.includes(brain.url));

  // 契約 7：發告警走 webhook POST；沒設 webhook 回 false 不炸
  let posted = null;
  const sent = await sendAlert("test", "https://hooks.example/x", async (url, opts) => { posted = { url, opts }; return { ok: true }; });
  check("告警 POST 到 webhook", sent === true && posted.opts.method === "POST" && posted.opts.body.includes("test"));
  const noHook = await sendAlert("test", "", async () => { throw new Error("should not be called"); });
  check("沒設 webhook→安靜回 false", noHook === false);

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
