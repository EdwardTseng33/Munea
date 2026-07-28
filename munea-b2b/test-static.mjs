import assert from 'node:assert/strict';
import fs from 'node:fs';

const index = fs.readFileSync(new URL('./index.html', import.meta.url), 'utf8');
const call = fs.readFileSync(new URL('./call.html', import.meta.url), 'utf8');
const callKey = fs.readFileSync(new URL('./api/call-key.js', import.meta.url), 'utf8');
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
parseInlineScripts(call, 'call.html');

assert.match(index, /2–4 週場域試辦/);
assert.doesNotMatch(index, /4–8 週/);
assert.match(index, /10–20 位/);
assert.match(index, /達標轉正式/);
assert.match(index, /全程只用麥克風與聲音互動/);
assert.doesNotMatch(index, /\/api\/chat|speechSynthesis|chatTxt|文字聊聊/);
assert.doesNotMatch(index, /台灣首創|這個領域的.{0,4}領先者|150 小時/);

assert.match(call, /&demo=1&key=/);
assert.match(call, />DEMO 1\.0\.4<\/div>/);
assert.match(call, /id="gateInput" type="password"/);
assert.doesNotMatch(call, /sessionStorage\.setItem\(['"]munea_(?:pass|demo_unlocked)/);
// 2026-07-21 auto-unlock: call.html reads the pass saved by index.html so the
// visitor types the passphrase once, not twice. The backend still validates it.
assert.match(call, /sessionStorage\.getItem\(['"]munea_pass/);
assert.match(call, /function lockDemoAccess\(showGate=true\)[\s\S]*AVATAR_TOKEN = null;[\s\S]*VOICE_KEY = null;[\s\S]*avatarPrewarmPromise = null;/);
assert.match(call, /function hangup\(preserveMessage=false\)[\s\S]*lockDemoAccess\(true\);/);
assert.match(call, /window\.addEventListener\('pagehide', \(\)=> lockDemoAccess\(true\)\)/);
assert.match(call, /avatarToken/);
assert.match(call, /\/offer\?token=/);
assert.match(call, /\/audio\?token=/);
assert.match(call, /if \(qs\.has\('stream'\)\) return this\.startStream/);
assert.match(call, /transition:opacity \.18s linear/);
assert.match(call, /frameWidth: r\.frameWidth, frameHeight: r\.frameHeight/);
assert.match(call, /bytesReceived: r\.bytesReceived, totalDecodeTime: r\.totalDecodeTime/);
assert.match(call, /frames - baseline >= 18/);
assert.match(call, /waitForStableFrames\(pc, 1600\)/);
assert.match(call, /this\._renderStream = new MediaStream\(\)/);
assert.match(call, /this\._renderStream\.addTrack\(e\.track\)/);
assert.match(call, /relayFirst = showDbg && qs\.has\('relay'\)/);
assert.match(call, /msg\.type === 'playout_start'/);
assert.doesNotMatch(call, /Live\.releaseLocalPlayout\(\)/);
assert.match(call, /faceVid\.muted = false/);
assert.match(call, /WebRTC owns both A\/V tracks/);
assert.match(call, /if \(e\.track\.kind === 'audio'\) this\._audioReceiver = e\.receiver/);
assert.match(call, /Face\.prepareOpeningPath = async function/);
assert.match(call, /this\.feed\(new Int16Array\(24000\)\.buffer\)/);
assert.match(call, /setTimeout\(resolve, 3200\)/);
assert.match(call, /await Face\.prepareOpeningPath\(\)[\s\S]*Live\.activate\(\)/);
assert.match(call, /--box-top:9\.895833%/);
assert.match(call, /--box-height:56\.25%/);
assert.match(call, /source_crop: \{ x: 0, y: 190, width: 1080, height: 1080 \}/);
assert.match(call, /source_crop: \{ x: 0, y: 209, width: 1080, height: 1080 \}/);
assert.match(call, /model_input: \{ width: 768, height: 768 \}/);
assert.match(call, /demo-flashhead-square-768-v2/);
assert.match(call, /id="faceCanvas" width="768" height="768"/);
assert.match(call, /faceCode: 'a05d'/);
assert.match(call, /faceCode: 'a06d'/);
// PR #226: fill stretched the 768x768 face; cover keeps the aspect ratio.
assert.match(call, /object-fit:cover !important/);
assert.doesNotMatch(call, /object-fit:fill !important/);
assert.match(call, /let CAP_SECONDS = 180/);
assert.match(callKey, /\/demo\/session/);
assert.match(callKey, /avatarToken/);
assert.doesNotMatch(callKey, /DEMO_AVATAR_KEY/);
assert.doesNotMatch(call, /cap_rem=1|cap_evt=1/);

// Demo deployment must stay process-, path-, and port-isolated from the App.
assert.match(demoManager, /ROOT="\$\{MUNEA_DEMO_ROOT:-\/home\/glows\/munea-demo\}"/);
assert.match(demoManager, /APP="\$\{ROOT\}\/flashhead_server\.py"/);
assert.match(demoManager, /refusing to signal pid \$\{pid\}: it is not the Demo process/);
assert.doesNotMatch(demoManager, /\b(?:pkill|killall)\b/i);
assert.match(demoDeploy, /\$RemoteRoot = '\/home\/glows\/munea-demo'/);
assert.match(demoDeploy, /MUNEA_FACE_PORT=8188/);
assert.match(demoDeploy, /MUNEA_FH_ALLOWED_CHARS=a05d,a06d/);
assert.doesNotMatch(demoDeploy, /\b(?:kill|pkill|killall|Stop-Process)\b/i);

assert.match(call, /class="charbar"[\s\S]*bg-a05\.webp[\s\S]*bg-a06\.webp/);
assert.match(call, /waitForFirstFrame/);
assert.match(call, /Live\.primeMic\(\)/);
assert.match(call, /first video frame=/);
assert.match(call, /id="captionToggle"/);
assert.match(call, /id="micToggle"/);
assert.match(call, /id="closeBtn"/);
assert.match(call, /id="callTimer">00:00/);
assert.doesNotMatch(call, /寧寧 · 擬真女|阿原 · 擬真男|回 Munea 合作介紹頁/);

assert.match(call, /id="coverVid"/);
assert.match(call, /id="coverVidNext"/);
assert.match(call, /assets\/nening-hello\.mp4/);
assert.match(call, /assets\/nening-idle\.mp4/);
assert.match(call, /assets\/ahong-hello\.mp4/);
assert.match(call, /assets\/ahong-idle\.mp4/);
assert.match(call, /hello -> idle char=/);
for (const asset of ['nening-hello.mp4', 'nening-idle.mp4', 'ahong-hello.mp4', 'ahong-idle.mp4']) {
  assert.ok(fs.existsSync(new URL(`./assets/${asset}`, import.meta.url)), `${asset} should be shipped`);
}

console.log('PASS munea-b2b static pre-sales and voice-only contracts');
