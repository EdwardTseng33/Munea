'use strict';

// 隱私文字不准說得比實際做得好（2026-11-17）
//
// 這支守的是「不要再寫回去」。下面每一句都是審查時對過程式、確定做不到的話：
//   · 「只有你授權的家人看得到」「由你決定分享範圍」——健康數字、心情、吃藥紀錄是推給整個健康圈，沒有逐人開關
//   · 「只在你使用期間保存」「保存一年、滿一年前會先問你」——資料是留到使用者自己刪除，沒有到期清除也沒有「先問你」
//   · 「不外流」——內容會送到 Google 的 AI，家人看得到心情，安全通知會通知緊急聯絡人
//   · 「Munea 的 AI 系統」——實際是 Google 的 Gemini，要點名
//   · 「刪除帳號時健康紀錄會一併刪除」——被邀進別人健康圈的人，留在圈裡的健康紀錄不會跟著刪
//   · 「你隨時能查看這部分怎麼被使用」——沒有這個畫面
//   · 「醫療級監測」——看不懂，而且對外不用「監測」
//
// 哪一天真的做出對應功能（例如逐人分享開關），把那一條從 BANNED 拿掉，並同步改文字。
// 四語文案、App 畫面底稿、隱私權政策／條款／支援頁、商店說明、iOS 權限說明都掃。

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');

// 每一條：pattern＝不准再出現的寫法；sample＝改掉之前的原句（證明這條 pattern 真的抓得到，不是空守門）
const BANNED = [
  // ── 中文 ──
  { why: '家人可見範圍沒有逐人開關', pattern: /授權的家人/, sample: '健康資料只有你授權的家人看得到。' },
  { why: '家人可見範圍沒有逐人開關', pattern: /你授權的(近況|狀態|照護狀態)/, sample: '由你決定分享範圍，家人只看得到你授權的近況' },
  { why: '家人可見範圍沒有逐人開關', pattern: /由你決定分享範圍/, sample: '由你決定分享範圍，家人只看得到你授權的近況' },
  { why: '家人可見範圍沒有逐人開關', pattern: /你同意分享的健康狀態/, sample: '家人只會看到你同意分享的健康狀態與關懷摘要。' },
  { why: '家人可見範圍沒有逐人開關', pattern: /以本人同意的範圍為準/, sample: '每位成員能看到的內容，以本人同意的範圍為準。' },
  { why: '家人可見範圍沒有逐人開關', pattern: /在你設定的範圍內/, sample: '以及（在你設定的範圍內）讓家人照護圈看到需要留意的變化。' },
  { why: '家人可見範圍沒有逐人開關', pattern: /以同意與權限控管家人可見範圍/, sample: '並以同意與權限控管家人可見範圍。' },
  { why: '家人可見範圍沒有逐人開關', pattern: /家庭分享依你的同意與權限/, sample: '家庭分享依你的同意與權限設定進行。' },
  { why: '資料是留到使用者自己刪除', pattern: /只在你?使用期間/, sample: '資料由沐寧（Munea）保管，只在你使用期間保存' },
  { why: '沒有滿一年清除，也沒有「先問你」', pattern: /保存一年/, sample: '保存一年；滿一年前寧寧會先問你要不要留下來。' },
  { why: '沒有滿一年清除，也沒有「先問你」', pattern: /滿一年前.{0,16}先問你/, sample: '保存一年；滿一年前{companion}會先問你要不要留下來。' },
  { why: '內容會送到 Google、家人看得到心情', pattern: /不外流/, sample: '不外流、不販售、不做廣告' },
  { why: 'AI 是 Google 的 Gemini，要點名', pattern: /Munea 的 AI 系統/, sample: '語音與文字會由 Munea 的 AI 系統處理，部分服務位於境外。' },
  { why: '被邀進別人健康圈的人刪不乾淨', pattern: /健康紀錄會一併刪除/, sample: '刪除帳號時，雲端保存的健康紀錄會一併刪除。' },
  { why: '沒有這個畫面', pattern: /隨時能查看這部分怎麼被使用/, sample: '不做其他辨識用途，你隨時能查看這部分怎麼被使用' },
  { why: '看不懂，而且對外不用「監測」', pattern: /醫療級監測/, sample: '這不是即時或醫療級監測。' },
  { why: '程式沒有年齡檢查', pattern: /(不能|無法)自行註冊獨立帳號/, sample: '未成年人僅能由家長（或監護人）從家庭圈邀請加入使用，無法自行註冊獨立帳號' },
  // ── English ──
  { why: 'no per-person sharing switch', pattern: /family( members)? you (allow|authorize)/i, sample: 'Only family members you allow can see your health information.' },
  { why: 'no per-person sharing switch', pattern: /(status|summaries)[^.]{0,40}you authorize/i, sample: 'Family members see only the health status and care summaries you authorize.' },
  { why: 'no per-person sharing switch', pattern: /you have chosen to share with your family/i, sample: 'changes you have chosen to share with your family care circle.' },
  { why: 'no per-person sharing switch', pattern: /limited by the account holder['’]s consent/i, sample: "Each member's access is limited by the account holder's consent and assigned permissions." },
  { why: 'no per-person sharing switch', pattern: /only authorized status and care summaries/i, sample: 'only authorized status and care summaries are shared.' },
  { why: 'kept until the user deletes it', pattern: /only while you use/i, sample: 'Your data is kept by Munea only while you use the service' },
  { why: 'no one-year purge or prompt', pattern: /before the year is up/i, sample: 'Kept for one year. Before the year is up, {companion} will ask if you’d like to keep it.' },
  { why: 'no one-year purge or prompt', pattern: /kept for one year/i, sample: 'Records are kept for one year — there\'s nothing further back' },
  { why: 'content goes to Google; family sees mood', pattern: /never shared, sold/i, sample: 'You can view it anytime — never shared, sold, or used for ads' },
  { why: 'the AI is Google Gemini; name it', pattern: /Munea['’]s AI systems/i, sample: "Your voice and text are processed by Munea's AI systems, some of which operate outside your country." },
  { why: 'invited members are not fully deleted', pattern: /cloud health records are deleted when your Munea account is deleted/i, sample: 'cloud health records are deleted when your Munea account is deleted, subject to limited records we must retain by law.' },
  { why: 'no such screen', pattern: /always see how this is used/i, sample: 'No other recognition uses — you can always see how this is used' },
  { why: 'jargon', pattern: /medical-grade monitoring/i, sample: 'This is not real-time or medical-grade monitoring.' },
  { why: 'no age check in code', pattern: /cannot independently register/i, sample: 'and cannot independently register a separate account.' },
  // ── 日本語 ──
  { why: '家族ごとの共有設定はない', pattern: /許可した(ご)?家族だけ/, sample: '健康情報は、あなたが許可したご家族だけが見られます。' },
  { why: '家族ごとの共有設定はない', pattern: /本人が許可した健康状態/, sample: 'ご家族が見られるのは、本人が許可した健康状態とケアの要約だけです。' },
  { why: '家族ごとの共有設定はない', pattern: /本人の同意と設定された権限/, sample: '各参加者が閲覧できる範囲は、本人の同意と設定された権限に限られます。' },
  { why: '家族ごとの共有設定はない', pattern: /設定した範囲で/, sample: 'および設定した範囲でファミリーケアサークルに注意すべき変化を共有するために使用します。' },
  { why: '削除するまで保存される', pattern: /ご利用の間だけ/, sample: 'データはMuneaが、ご利用の間だけお預かりします。' },
  { why: '1年での削除も確認もない', pattern: /1年になる前に/, sample: '保存は1年です。1年になる前に{companion}が残すかどうかを確認します。' },
  { why: '1年での削除も確認もない', pattern: /保存は1年/, sample: '記録の保存は1年間です。それより前はありません' },
  { why: '内容はGoogleに送られる', pattern: /外部提供・販売/, sample: '外部提供・販売・広告利用はしません' },
  { why: 'AIはGoogleのGemini', pattern: /MuneaのAIシステム/, sample: '音声と会話の文字データは、MuneaのAIシステムで処理されます。' },
  { why: 'その画面はない', pattern: /使われ方はいつでも確認できます/, sample: 'ほかの目的での識別には使いません。使われ方はいつでも確認できます' },
  // ── Español ──
  { why: 'no hay ajuste por persona', pattern: /(familiares?|familia)[^.]{0,12} que autorices/i, sample: 'Solo los familiares que autorices pueden ver la información de salud.' },
  { why: 'no hay ajuste por persona', pattern: /resúmenes[^.]{0,30}que autorices/i, sample: 'Los familiares solo ven el estado de salud y los resúmenes de cuidados que autorices.' },
  { why: 'no hay ajuste por persona', pattern: /consentimiento de la persona titular/i, sample: 'El acceso de cada integrante se limita al consentimiento de la persona titular y a los permisos asignados.' },
  { why: 'se conserva hasta que se borre', pattern: /solo mientras usas/i, sample: 'Munea guarda tus datos solo mientras usas el servicio' },
  { why: 'no hay borrado al año ni pregunta', pattern: /antes de cumplirse/i, sample: 'Se guarda un año; antes de cumplirse, {companion} te preguntará si quieres conservarlo.' },
  { why: 'no hay borrado al año ni pregunta', pattern: /se guardan? un año/i, sample: 'Los registros se guardan un año; no hay nada anterior' },
  { why: 'el contenido va a Google', pattern: /nunca se filtra/i, sample: 'Nunca se filtra, se vende ni se usa para publicidad' },
  { why: 'la IA es Gemini de Google', pattern: /sistemas de IA de Munea/i, sample: 'Los sistemas de IA de Munea procesan tu voz y tus textos' },
  { why: 'no existe esa pantalla', pattern: /siempre puedes ver cómo se emplea/i, sample: 'Sin otros usos de reconocimiento; siempre puedes ver cómo se emplea' },
];

// 1) 每一條 pattern 都要真的抓得到它要擋的原句——不然就是空守門
for (const rule of BANNED) {
  assert.ok(rule.pattern.test(rule.sample), `守門規則抓不到自己的原句：${rule.pattern} ← 「${rule.sample}」`);
}

// 2) 要掃的檔案
function listFiles(dir, predicate) {
  const out = [];
  const walk = (current) => {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === 'assets' || entry.name === 'node_modules') continue;
        walk(full);
      } else if (predicate(full)) {
        out.push(full);
      }
    }
  };
  walk(path.join(ROOT, dir));
  return out;
}

const files = [
  ...['zh-TW', 'en', 'ja', 'es'].map((l) => path.join(ROOT, 'web/src/i18n', `${l}.json`)),
  path.join(ROOT, 'web/index.html'),
  path.join(ROOT, 'web/src/app.js'),
  path.join(ROOT, 'web/privacy.html'),
  path.join(ROOT, 'web/terms.html'),
  path.join(ROOT, 'web/support.html'),
  ...listFiles('web/legal', (f) => f.endsWith('.html')),
  ...listFiles('app-site', (f) => /\.(html|json|txt)$/.test(f)),
  ...listFiles('app-store/localizations', (f) => f.endsWith('.json')),
  path.join(ROOT, 'ios/App/App/Info.plist'),
  ...['zh-Hant', 'en', 'ja', 'es'].map((l) => path.join(ROOT, 'ios/App/App', `${l}.lproj`, 'InfoPlist.strings')),
];
assert.ok(files.length >= 40, `要掃的檔案數量不對（${files.length}）——路徑是不是搬家了`);

const hits = [];
for (const file of files) {
  assert.ok(fs.existsSync(file), `要掃的檔案不見了：${path.relative(ROOT, file)}`);
  const lines = fs.readFileSync(file, 'utf8').split('\n');
  lines.forEach((line, index) => {
    for (const rule of BANNED) {
      if (rule.pattern.test(line)) {
        hits.push(`${path.relative(ROOT, file).replace(/\\/g, '/')}:${index + 1} 命中 ${rule.pattern}（${rule.why}）`);
      }
    }
  });
}
assert.deepEqual(hits, [], `這些地方又寫回做不到的話：\n${hits.join('\n')}`);

// 3) 該講的要講：登入頁與同意畫面四語都要點名 Google、講到健康數字和心情也會給 AI 參考
const catalogs = Object.fromEntries(
  ['zh-TW', 'en', 'ja', 'es'].map((l) => [l, JSON.parse(fs.readFileSync(path.join(ROOT, 'web/src/i18n', `${l}.json`), 'utf8'))]),
);
const HEALTH_TO_AI = {
  'zh-TW': /健康數字和心情.{0,6}給 AI 參考/,
  en: /health numbers and mood are also given to the AI/i,
  ja: /健康の数値と気分も、AIが参考にします/,
  es: /datos de salud y tu estado de ánimo también se comparten con la IA/i,
};
for (const [locale, catalog] of Object.entries(catalogs)) {
  for (const key of ['auth.aiProcessingDisclosure', 'consent.point1Title', 'consent.cloudProcessingTitle']) {
    assert.match(catalog[key], /Google/, `${locale}:${key} 必須點名 Google`);
  }
  for (const key of ['consent.point1Body', 'consent.cloudProcessingBody']) {
    assert.match(catalog[key], HEALTH_TO_AI[locale], `${locale}:${key} 必須講健康數字和心情也會給 AI 參考`);
  }
}

// 4) 四語隱私權政策都要有「誰看得到什麼」和服務供應商（Google 的 AI、資料庫在東京）
const POLICY_MUST = {
  'web/privacy.html': [/誰看得到什麼/, /Gemini/, /日本東京/, /通話時，你的健康數字和心情也會給 AI 參考/, /想撤回同意/, /替家人設定時/],
  'app-site/privacy.html': [/誰看得到什麼/, /Gemini/, /日本東京/, /通話時，你的健康數字和心情也會給 AI 參考/, /想撤回同意/, /替家人設定時/],
  'web/legal/en/privacy.html': [/Who can see what/, /Gemini/, /Tokyo, Japan/, /health numbers and mood are also given to the AI/, /withdraw consent/i, /set Munea up for a family member/],
  'web/legal/ja/privacy.html': [/誰が何を見られるか/, /Gemini/, /日本・東京/, /健康の数値と気分もAIが参考にします/, /同意を撤回/, /ご家族の代わりに設定するとき/],
  'web/legal/es/privacy.html': [/Quién puede ver qué/, /Gemini/, /Tokio, Japón/, /también se comparten con la IA/, /retirar tu consentimiento/i, /configuras Munea para un familiar/],
};
for (const [file, patterns] of Object.entries(POLICY_MUST)) {
  const text = fs.readFileSync(path.join(ROOT, file), 'utf8');
  for (const pattern of patterns) assert.match(text, pattern, `${file} 少了 ${pattern}`);
}

// 5) iOS 隱私清單：縣市會跟個人資料一起存雲端 → 粗略位置必須宣告「與身分連結」
const privacyManifest = fs.readFileSync(path.join(ROOT, 'ios/App/App/PrivacyInfo.xcprivacy'), 'utf8');
const coarse = privacyManifest.match(/NSPrivacyCollectedDataTypeCoarseLocation<\/string>\s*<key>NSPrivacyCollectedDataTypeLinked<\/key><(true|false)\/>/);
assert.ok(coarse, 'PrivacyInfo.xcprivacy 找不到粗略位置那一項');
assert.equal(coarse[1], 'true', 'PrivacyInfo.xcprivacy：粗略位置（縣市）必須宣告與身分連結');

console.log(`PASS: 隱私文字誠實守門（${BANNED.length} 條禁用寫法 × ${files.length} 個檔案，加上該講的四語都有講）`);
