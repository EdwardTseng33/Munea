// 唯讀：問蘋果「現在到底是哪一版、哪個 Build、什麼狀態」（2026-08-06）
// 版號回寫缺口一再發生，不要再用估的——直接問權威來源。
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

const versions = await api(
  `/v1/apps/${APP_ID}/appStoreVersions?limit=6&fields[appStoreVersions]=versionString,appStoreState,createdDate,releaseType`,
);
console.log('== 蘋果那邊的版本 ==');
for (const v of versions.data) {
  const a = v.attributes;
  const selected = await api(
    `/v1/appStoreVersions/${v.id}/build?fields[builds]=version,uploadedDate,processingState`,
  );
  const selectedPrerelease = selected.data
    ? await api(`/v1/builds/${selected.data.id}/preReleaseVersion?fields[preReleaseVersions]=version`)
    : null;
  const selectedLabel = selected.data
    ? `  選用=App ${selectedPrerelease?.data?.attributes?.version || 'unknown'} Build ${selected.data.attributes.version}`
    : '  選用=尚未選 Build';
  console.log(
    `  ${a.versionString}  狀態=${a.appStoreState}  建立=${(a.createdDate || '').slice(0, 16)}${selectedLabel}`,
  );
}

const builds = await api(
  `/v1/builds?filter[app]=${APP_ID}&limit=8&sort=-version`
    + '&fields[builds]=version,uploadedDate,processingState,expired,preReleaseVersion'
    + '&fields[preReleaseVersions]=version&include=preReleaseVersion',
);
const prereleaseVersions = new Map(
  (builds.included || [])
    .filter((item) => item.type === 'preReleaseVersions')
    .map((item) => [item.id, item.attributes.version]),
);
console.log('\n== 上傳過的 Build（新到舊）==');
for (const b of builds.data) {
  const a = b.attributes;
  const prereleaseId = b.relationships?.preReleaseVersion?.data?.id;
  const appVersion = prereleaseVersions.get(prereleaseId) || 'unknown';
  console.log(
    `  App ${appVersion}  Build ${a.version}  ${a.processingState}  上傳=${(a.uploadedDate || '').slice(0, 16)}${a.expired ? '  [已過期]' : ''}`,
  );
}
