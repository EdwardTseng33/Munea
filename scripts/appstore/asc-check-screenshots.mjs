// 查各語言截圖在蘋果那邊的處理狀態與錯誤原因（2026-07-31 蘇菲）
import crypto from 'node:crypto';
import fs from 'node:fs';

const KEY_ID = process.env.ASC_KEY_ID;
const ISSUER_ID = process.env.ASC_ISSUER_ID;
const KEY_PATH = process.env.ASC_PRIVATE_KEY_PATH;
const APP_ID = process.env.ASC_APP_ID || '6788658125';

const b64url = (b) =>
  Buffer.from(b).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

function token() {
  const now = Math.floor(Date.now() / 1000);
  const h = b64url(JSON.stringify({ alg: 'ES256', kid: KEY_ID, typ: 'JWT' }));
  const p = b64url(
    JSON.stringify({ iss: ISSUER_ID, iat: now, exp: now + 900, aud: 'appstoreconnect-v1' }),
  );
  const s = crypto.createSign('SHA256');
  s.update(`${h}.${p}`);
  return `${h}.${p}.${b64url(s.sign({ key: fs.readFileSync(KEY_PATH, 'utf8'), dsaEncoding: 'ieee-p1363' }))}`;
}

async function api(url) {
  const res = await fetch(`https://api.appstoreconnect.apple.com${url}`, {
    headers: { Authorization: `Bearer ${token()}` },
  });
  const t = await res.text();
  if (!res.ok) throw new Error(`${url} -> ${res.status}\n${t.slice(0, 400)}`);
  return JSON.parse(t);
}

const v = await api(
  `/v1/apps/${APP_ID}/appStoreVersions?filter[appStoreState]=PREPARE_FOR_SUBMISSION&limit=1`,
);
const locs = await api(`/v1/appStoreVersions/${v.data[0].id}/appStoreVersionLocalizations?limit=50`);

for (const loc of locs.data) {
  const sets = await api(`/v1/appStoreVersionLocalizations/${loc.id}/appScreenshotSets?limit=10`);
  for (const set of sets.data) {
    const shots = await api(`/v1/appScreenshotSets/${set.id}/appScreenshots?limit=20`);
    console.log(`\n${loc.attributes.locale} · ${set.attributes.screenshotDisplayType} · ${shots.data.length} 張`);
    for (const s of shots.data) {
      const a = s.attributes;
      const st = a.assetDeliveryState || {};
      const errs = (st.errors || []).map((e) => `${e.code}: ${e.description}`).join(' / ');
      console.log(
        `  ${a.fileName} | 狀態=${st.state} | 尺寸=${a.imageAsset ? a.imageAsset.width + 'x' + a.imageAsset.height : '無'} ${errs ? '| ❌ ' + errs : ''}`,
      );
    }
  }
}
