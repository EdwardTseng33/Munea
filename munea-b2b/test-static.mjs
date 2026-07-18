import assert from 'node:assert/strict';
import fs from 'node:fs';

const index = fs.readFileSync(new URL('./index.html', import.meta.url), 'utf8');
const call = fs.readFileSync(new URL('./call.html', import.meta.url), 'utf8');

function parseInlineScripts(html, label) {
  const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)];
  assert.ok(scripts.length > 0, `${label} should include inline scripts`);
  scripts.forEach((match, i) => {
    assert.doesNotThrow(() => new Function(match[1]), `${label} inline script ${i + 1} should parse`);
  });
}

parseInlineScripts(index, 'index.html');
parseInlineScripts(call, 'call.html');

assert.match(index, /4–8 週試辦/);
assert.match(index, /10–20 位/);
assert.match(index, /通話完成率/);
assert.match(index, /全程只用麥克風與聲音互動/);
assert.doesNotMatch(index, /\/api\/chat|speechSynthesis|chatTxt|文字聊聊/);
assert.doesNotMatch(index, /台灣首創|這個領域的.{0,4}領先者|150 小時/);

assert.match(call, /&demo=1&key=/);
assert.doesNotMatch(call, /cap_rem=1|cap_evt=1/);
assert.match(call, /class="charbar"[\s\S]*bg-a05\.png[\s\S]*bg-a06\.png/);
assert.match(call, /waitForFirstFrame/);
assert.match(call, /Live\.primeMic\(\)/);
assert.match(call, /first video frame=/);
assert.match(call, /id="captionToggle"/);
assert.match(call, /id="micToggle"/);
assert.match(call, /id="closeBtn"/);
assert.match(call, /id="callTimer">00:00/);
assert.doesNotMatch(call, /寧寧 · 擬真女|阿原 · 擬真男|回 Munea 合作介紹頁/);

console.log('PASS munea-b2b static pre-sales and voice-only contracts');
