import assert from 'node:assert/strict';
import fs from 'node:fs';

const index = fs.readFileSync(new URL('./index.html', import.meta.url), 'utf8');
const demoManager = fs.readFileSync(new URL('../deploy/glows/manage-shared-demo.sh', import.meta.url), 'utf8');
const demoDeploy = fs.readFileSync(new URL('../deploy/glows/shared-card-demo.ps1', import.meta.url), 'utf8');

function parseInlineScripts(html, label) {
  const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)];
  assert.ok(scripts.length > 0, `${label} should include inline scripts`);
  scripts.forEach((match, i) => {
    assert.doesNotThrow(() => new Function(match[1]), `${label} inline script ${i + 1} should parse`);
  });
}

parseInlineScripts(index, 'index.html');

assert.match(index, /2–4 週場域試辦/);
assert.doesNotMatch(index, /4–8 週/);
assert.match(index, /10–20 位/);
assert.match(index, /達標轉正式/);
// 2026-11-05 Edward 拍板：網頁試打通話整套移除，改引導下載 App 直接試用。
for (const gone of ['./call.html', './api/call-key.js', './test-call-browser.mjs', './flashhead']) {
  assert.ok(!fs.existsSync(new URL(gone, import.meta.url)), `${gone} should stay deleted`);
}
assert.doesNotMatch(index, /\/call\.html|\/api\/call-key|munea_pass|demoPass/);
assert.match(index, /id="try-app"/);
assert.match(index, /href="https:\/\/apps\.apple\.com\/tw\/app\/id6788658125"/);
assert.doesNotMatch(index, /\/api\/chat|speechSynthesis|chatTxt|文字聊聊/);
assert.doesNotMatch(index, /台灣首創|這個領域的.{0,4}領先者|150 小時/);

// Demo deployment must stay process-, path-, and port-isolated from the App.
assert.match(demoManager, /ROOT="\$\{MUNEA_DEMO_ROOT:-\/home\/glows\/munea-demo\}"/);
assert.match(demoManager, /APP="\$\{ROOT\}\/flashhead_server\.py"/);
assert.match(demoManager, /refusing to signal pid \$\{pid\}: it is not the Demo process/);
assert.doesNotMatch(demoManager, /\b(?:pkill|killall)\b/i);
assert.match(demoDeploy, /\$RemoteRoot = '\/home\/glows\/munea-demo'/);
assert.match(demoDeploy, /MUNEA_FACE_PORT=8188/);
assert.match(demoDeploy, /MUNEA_FH_ALLOWED_CHARS=a05d,a06d/);
assert.doesNotMatch(demoDeploy, /\b(?:kill|pkill|killall|Stop-Process)\b/i);

console.log('PASS munea-b2b static pre-sales contracts (no web call demo)');
