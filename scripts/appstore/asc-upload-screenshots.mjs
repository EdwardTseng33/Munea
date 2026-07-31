// 把各國商店截圖傳上 App Store Connect（2026-07-31 蘇菲）
//
// 為什麼要自己寫：瀏覽器那條路被檔案安全限制擋死（只認使用者直接貼進對話的檔案），
// E 槽、程式庫、暫存區全部拒絕。所以改走蘋果的接口。
//
// 蘋果傳圖是三步，缺一不可：
//   ① 先跟蘋果「登記」要傳一張多大的圖 → 它回一組上傳網址
//   ② 把檔案內容 PUT 到那些網址
//   ③ 再回頭「蓋章」說傳完了，並附上檔案指紋（md5）讓它核對
// 只做①②不做③，蘋果那邊會是一張永遠處於半成品狀態的圖。
//
// 跑法：
//   node asc-upload-screenshots.mjs <locale> <資料夾> [--dry-run]

import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

const KEY_ID = process.env.ASC_KEY_ID;
const ISSUER_ID = process.env.ASC_ISSUER_ID;
const KEY_PATH = process.env.ASC_PRIVATE_KEY_PATH;
const APP_ID = process.env.ASC_APP_ID || '6788658125';
const DISPLAY_TYPE = 'APP_IPHONE_65';

const [, , localeArg, dirArg, ...rest] = process.argv;
const DRY = rest.includes('--dry-run');

if (!KEY_ID || !ISSUER_ID || !KEY_PATH) {
  console.error('缺 ASC_KEY_ID / ASC_ISSUER_ID / ASC_PRIVATE_KEY_PATH');
  process.exit(1);
}
if (!localeArg || !dirArg) {
  console.error('用法：node asc-upload-screenshots.mjs <locale> <資料夾> [--dry-run]');
  process.exit(1);
}

const b64url = (buf) =>
  Buffer.from(buf).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

function makeToken() {
  const now = Math.floor(Date.now() / 1000);
  const header = b64url(JSON.stringify({ alg: 'ES256', kid: KEY_ID, typ: 'JWT' }));
  const payload = b64url(
    JSON.stringify({ iss: ISSUER_ID, iat: now, exp: now + 900, aud: 'appstoreconnect-v1' }),
  );
  const signer = crypto.createSign('SHA256');
  signer.update(`${header}.${payload}`);
  const der = signer.sign({ key: fs.readFileSync(KEY_PATH, 'utf8'), dsaEncoding: 'ieee-p1363' });
  return `${header}.${payload}.${b64url(der)}`;
}

let token = makeToken();

async function api(method, url, body) {
  const full = url.startsWith('http') ? url : `https://api.appstoreconnect.apple.com${url}`;
  const res = await fetch(full, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(`${method} ${full} -> ${res.status}\n${text.slice(0, 600)}`);
  }
  return text ? JSON.parse(text) : null;
}

// ── 找到「準備提交」那個版本 ─────────────────────────────
const versions = await api(
  'GET',
  `/v1/apps/${APP_ID}/appStoreVersions?filter[appStoreState]=PREPARE_FOR_SUBMISSION&limit=1`,
);
const version = versions.data[0];
if (!version) throw new Error('找不到「準備提交」狀態的版本');
console.log(`版本：${version.attributes.versionString}（${version.id}）`);

// ── 找到該語言的那一份 ──────────────────────────────────
const locs = await api(
  'GET',
  `/v1/appStoreVersions/${version.id}/appStoreVersionLocalizations?limit=50`,
);
const loc = locs.data.find((l) => l.attributes.locale === localeArg);
if (!loc) {
  console.error(`找不到語言 ${localeArg}。現有：${locs.data.map((l) => l.attributes.locale).join(', ')}`);
  process.exit(1);
}
console.log(`語言：${localeArg}（${loc.id}）`);

// ── 找或建 6.5 吋那組 ───────────────────────────────────
const sets = await api('GET', `/v1/appStoreVersionLocalizations/${loc.id}/appScreenshotSets?limit=50`);
let set = sets.data.find((s) => s.attributes.screenshotDisplayType === DISPLAY_TYPE);

const files = fs
  .readdirSync(dirArg)
  .filter((f) => f.toLowerCase().endsWith('.png'))
  .sort();
console.log(`要傳 ${files.length} 張：${files.join(', ')}`);

if (DRY) {
  console.log(`（乾跑）現有組別：${set ? set.id : '無、會新建'}`);
  process.exit(0);
}

if (set) {
  // 這個語言原本是「沿用主要語言的圖」或已有自己的圖——先清掉再放新的，避免混在一起
  const existing = await api('GET', `/v1/appScreenshotSets/${set.id}/appScreenshots?limit=50`);
  for (const shot of existing.data) {
    await api('DELETE', `/v1/appScreenshots/${shot.id}`);
    console.log(`  清掉舊圖 ${shot.attributes.fileName || shot.id}`);
  }
} else {
  const created = await api('POST', '/v1/appScreenshotSets', {
    data: {
      type: 'appScreenshotSets',
      attributes: { screenshotDisplayType: DISPLAY_TYPE },
      relationships: {
        appStoreVersionLocalization: {
          data: { type: 'appStoreVersionLocalizations', id: loc.id },
        },
      },
    },
  });
  set = created.data;
  console.log(`  新建組別 ${set.id}`);
}

// ── 逐張：登記 → 上傳 → 蓋章 ───────────────────────────
for (const name of files) {
  const full = path.join(dirArg, name);
  const bytes = fs.readFileSync(full);
  token = makeToken(); // 每張重新簽，避免大檔傳到一半通行證過期

  const reserved = await api('POST', '/v1/appScreenshots', {
    data: {
      type: 'appScreenshots',
      attributes: { fileSize: bytes.length, fileName: name },
      relationships: { appScreenshotSet: { data: { type: 'appScreenshotSets', id: set.id } } },
    },
  });

  const shotId = reserved.data.id;
  const ops = reserved.data.attributes.uploadOperations || [];
  for (const op of ops) {
    const headers = {};
    for (const h of op.requestHeaders || []) headers[h.name] = h.value;
    const chunk = bytes.subarray(op.offset, op.offset + op.length);
    const res = await fetch(op.url, { method: op.method, headers, body: chunk });
    if (!res.ok) throw new Error(`上傳 ${name} 失敗：${res.status} ${await res.text()}`);
  }

  const md5 = crypto.createHash('md5').update(bytes).digest('hex');
  await api('PATCH', `/v1/appScreenshots/${shotId}`, {
    data: { type: 'appScreenshots', id: shotId, attributes: { uploaded: true, sourceFileChecksum: md5 } },
  });
  console.log(`  ✅ ${name}（${(bytes.length / 1048576).toFixed(1)} MB）`);
}

console.log(`${localeArg} 完成，共 ${files.length} 張`);
