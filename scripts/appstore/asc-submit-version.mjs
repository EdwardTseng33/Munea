#!/usr/bin/env node
// 一鍵送審（2026-10-29）：建立／對齊 App Store 版本 -> 等 build 處理完成 -> 綁 build ->
// 四語 whatsNew -> 建立並送出 reviewSubmission。
'use strict';

import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');

function argValue(name, fallback) {
  const idx = process.argv.indexOf(name);
  return idx >= 0 && process.argv[idx + 1] !== undefined ? process.argv[idx + 1] : fallback;
}

const VERSION = argValue('--version');
const BUILD = argValue('--build');
const DRY_RUN = process.argv.includes('--dry-run');
const DO_SUBMIT = process.argv.includes('--submit');
const WHATS_NEW_DIR = argValue('--whats-new-dir', 'app-store/localizations');
const POLL_TIMEOUT_MINUTES = Number(argValue('--poll-timeout-minutes', '60'));
const POLL_INTERVAL_SECONDS = Number(argValue('--poll-interval-seconds', '30'));

const KEY_ID = process.env.ASC_KEY_ID;
const ISSUER_ID = process.env.ASC_ISSUER_ID;
const KEY_PATH = process.env.ASC_PRIVATE_KEY_PATH;
const APP_ID = process.env.ASC_APP_ID || '6788658125';

if (!VERSION || !/^\d+\.\d+\.\d+$/.test(VERSION)) {
  console.error('FAIL --version is required and must look like 1.0.70');
  process.exit(1);
}
if (!BUILD || !/^\d+$/.test(BUILD)) {
  console.error('FAIL --build is required and must be a plain integer, e.g. 541');
  process.exit(1);
}
if (!KEY_ID || !ISSUER_ID || !KEY_PATH) {
  console.error('FAIL ASC_KEY_ID / ASC_ISSUER_ID / ASC_PRIVATE_KEY_PATH must be set.');
  process.exit(1);
}

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

async function request(method, url, body) {
  const res = await fetch(`https://api.appstoreconnect.apple.com${url}`, {
    method,
    headers: {
      Authorization: `Bearer ${token()}`,
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`${method} ${url} -> ${res.status}\n${text.slice(0, 800)}`);
  return text ? JSON.parse(text) : null;
}

const get = (url) => request('GET', url);

async function write(method, url, body, describe) {
  console.log(`${DRY_RUN ? 'DRY-RUN would' : 'will'} ${method} ${url}${describe ? ` (${describe})` : ''}`);
  if (DRY_RUN) return null;
  return request(method, url, body);
}

function readLocaleManifest() {
  const manifestPath = path.join(ROOT, WHATS_NEW_DIR, 'manifest.json');
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  const resolved = [];
  for (const [key, entry] of Object.entries(manifest.locales || {})) {
    if (entry.appStoreLocale && entry.metadataFile) {
      resolved.push({ locale: entry.appStoreLocale, metadataFile: entry.metadataFile });
      continue;
    }
    if (entry.selectedVariants && entry.marketVariants) {
      for (const variant of entry.selectedVariants) {
        const variantEntry = entry.marketVariants[variant];
        if (variantEntry && variantEntry.metadataFile) {
          resolved.push({ locale: variant, metadataFile: variantEntry.metadataFile });
        }
      }
    }
  }
  return resolved;
}

function readWhatsNew(metadataFile) {
  const metaPath = path.join(ROOT, WHATS_NEW_DIR, metadataFile);
  const meta = JSON.parse(fs.readFileSync(metaPath, 'utf8'));
  if (!meta.whatsNew) throw new Error(`${metadataFile} is missing whatsNew`);
  return meta.whatsNew;
}

async function findAppStoreVersion() {
  const result = await get(
    `/v1/apps/${APP_ID}/appStoreVersions?filter[versionString]=${encodeURIComponent(VERSION)}` +
      '&limit=1&fields[appStoreVersions]=versionString,appStoreState',
  );
  return result.data[0] || null;
}

async function findBuild() {
  const result = await get(
    `/v1/builds?filter[app]=${APP_ID}&filter[version]=${encodeURIComponent(BUILD)}` +
      '&limit=1&fields[builds]=version,processingState,expired,uploadedDate',
  );
  return result.data[0] || null;
}

async function waitForValidBuild() {
  const deadline = Date.now() + POLL_TIMEOUT_MINUTES * 60 * 1000;
  for (;;) {
    const build = await findBuild();
    if (!build) {
      console.log(`Build ${BUILD} not uploaded yet.`);
    } else {
      console.log(`Build ${BUILD} processingState=${build.attributes.processingState}`);
      if (build.attributes.processingState === 'VALID') return build;
      if (build.attributes.processingState === 'FAILED' || build.attributes.processingState === 'INVALID') {
        throw new Error(`Build ${BUILD} processing ended in ${build.attributes.processingState}`);
      }
    }
    if (DRY_RUN) {
      console.log('DRY-RUN stop polling after one read-only check.');
      return build;
    }
    if (Date.now() > deadline) {
      throw new Error(`Build ${BUILD} did not become VALID within ${POLL_TIMEOUT_MINUTES} minutes.`);
    }
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_SECONDS * 1000));
  }
}

async function ensureAppStoreVersion(buildId) {
  let version = await findAppStoreVersion();
  if (version) {
    console.log(`Found existing appStoreVersion ${VERSION} (id=${version.id}, state=${version.attributes.appStoreState})`);
  } else {
    console.log(`No appStoreVersion ${VERSION} yet.`);
    const created = await write(
      'POST',
      '/v1/appStoreVersions',
      {
        data: {
          type: 'appStoreVersions',
          attributes: { platform: 'IOS', versionString: VERSION, releaseType: 'MANUAL' },
          relationships: {
            app: { data: { type: 'apps', id: APP_ID } },
            ...(buildId ? { build: { data: { type: 'builds', id: buildId } } } : {}),
          },
        },
      },
      `create appStoreVersion ${VERSION}`,
    );
    version = created ? created.data : { id: 'dry-run-unknown-id', attributes: { appStoreState: 'unknown' } };
  }
  if (buildId && version.id !== 'dry-run-unknown-id') {
    await write(
      'PATCH',
      `/v1/appStoreVersions/${version.id}/relationships/build`,
      { data: { type: 'builds', id: buildId } },
      `bind build ${BUILD} to version ${VERSION}`,
    );
  }
  return version;
}

async function syncLocalizations(appStoreVersionId) {
  const targets = readLocaleManifest();
  if (targets.length === 0) {
    console.warn('WARN no locales resolved from manifest; nothing to fill in for whatsNew.');
    return;
  }
  let existing = { data: [] };
  if (appStoreVersionId !== 'dry-run-unknown-id') {
    existing = await get(
      `/v1/appStoreVersions/${appStoreVersionId}/appStoreVersionLocalizations` +
        '?limit=50&fields[appStoreVersionLocalizations]=locale,whatsNew',
    );
  }
  for (const target of targets) {
    const whatsNew = readWhatsNew(target.metadataFile);
    const found = existing.data.find((item) => item.attributes.locale === target.locale);
    if (found) {
      await write(
        'PATCH',
        `/v1/appStoreVersionLocalizations/${found.id}`,
        { data: { type: 'appStoreVersionLocalizations', id: found.id, attributes: { whatsNew } } },
        `update whatsNew for ${target.locale}`,
      );
    } else {
      // 商店上還沒有這個語言：新增語言要整套描述／關鍵字／截圖，是另外的上架決定，
      // 只塞 whatsNew 會讓整個版本卡在「缺 description」送不了審（2026-10-29 es-ES 實際踩到）。
      console.warn(`SKIP ${target.locale}: not listed on the App Store yet; whatsNew not added.`);
    }
  }
}

async function findOpenReviewSubmission() {
  const result = await get(
    `/v1/apps/${APP_ID}/reviewSubmissions?filter[platform]=IOS&filter[state]=READY_FOR_REVIEW&limit=1`,
  );
  return result.data[0] || null;
}

async function versionAlreadyAttached(submissionId, appStoreVersionId) {
  const items = await get(`/v1/reviewSubmissions/${submissionId}/items?include=appStoreVersion&limit=50`);
  return items.data.some((item) => item.relationships?.appStoreVersion?.data?.id === appStoreVersionId);
}

async function createReviewSubmission(appStoreVersionId) {
  // 同一個 App 同時只能有一份還沒送出的審查單：上次中途失敗留下的就沿用，不再另開。
  const open = await findOpenReviewSubmission();
  let submissionId;
  if (open) {
    submissionId = open.id;
    console.log(`reuse open reviewSubmission ${submissionId}`);
  } else {
    const created = await write(
      'POST',
      '/v1/reviewSubmissions',
      { data: { type: 'reviewSubmissions', relationships: { app: { data: { type: 'apps', id: APP_ID } } } } },
      'create reviewSubmission',
    );
    submissionId = created ? created.data.id : 'dry-run-unknown-id';
  }

  const attached = open ? await versionAlreadyAttached(submissionId, appStoreVersionId) : false;
  if (attached) {
    console.log('appStoreVersion already attached to this reviewSubmission.');
  } else await write(
    'POST',
    '/v1/reviewSubmissionItems',
    {
      data: {
        type: 'reviewSubmissionItems',
        relationships: {
          reviewSubmission: { data: { type: 'reviewSubmissions', id: submissionId } },
          appStoreVersion: { data: { type: 'appStoreVersions', id: appStoreVersionId } },
        },
      },
    },
    'attach appStoreVersion to reviewSubmission',
  );

  if (DO_SUBMIT) {
    await write(
      'PATCH',
      `/v1/reviewSubmissions/${submissionId}`,
      { data: { type: 'reviewSubmissions', id: submissionId, attributes: { submitted: true } } },
      'SUBMIT for review (final, irreversible step)',
    );
  } else {
    console.log('--submit not set: reviewSubmission prepared but NOT submitted. Re-run with --submit to send it.');
  }
  return submissionId;
}

async function main() {
  console.log(`== asc-submit-version: version=${VERSION} build=${BUILD} dryRun=${DRY_RUN} submit=${DO_SUBMIT} ==`);
  const build = await waitForValidBuild();
  const buildId = build ? build.id : null;
  const version = await ensureAppStoreVersion(buildId);
  await syncLocalizations(version.id);
  await createReviewSubmission(version.id);
  console.log('Done.');
}

main().catch((error) => {
  console.error(`FAIL ${error.message}`);
  process.exitCode = 1;
});
