#!/usr/bin/env node
/**
 * 把官網最新產出搬到「正門」munea.net 的發佈資料夾
 * ------------------------------------------------------------------
 * 為什麼要這支：同一份網站住在兩個地方——
 *   app.munea.net → Firebase（合併到 main 就自動發佈）
 *   munea.net     → Vercel  （手動發佈，內容放在 E:\Claude\careon-site）
 * 沒有這支小工具，兩邊就會慢慢走鐘：改了文案只有一邊更新。
 *
 * 用法：
 *   node scripts/sync-front-door.mjs          搬過去
 *   node scripts/sync-front-door.mjs --check  只比對、不搬（看兩邊有沒有不一樣）
 *
 * 搬完之後要發佈：
 *   cd E:/Claude/careon-site && npx vercel deploy --prod --yes
 */
import { readdirSync, statSync, mkdirSync, copyFileSync, rmSync, existsSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execSync } from 'node:child_process';

const REPO = join(dirname(fileURLToPath(import.meta.url)), '..');
const SRC = join(REPO, 'app-site');
const DEST = process.env.MUNEA_FRONT_DOOR_DIR || 'E:/Claude/careon-site';

/** 這些是正門獨有的，搬檔時不能被蓋掉或刪掉 */
const KEEP = new Set(['solutions.html', 'vercel.json', 'README.md', '.vercel', '.git', '.gitignore', '.claude', 'favicon.svg']);

const checkOnly = process.argv.includes('--check');

if (!existsSync(DEST)) {
  console.error(`✗ 找不到正門資料夾：${DEST}`);
  console.error('  （若位置不同，用 MUNEA_FRONT_DOOR_DIR 環境變數指定）');
  process.exit(1);
}

// 先確保產出是最新的
if (!checkOnly) {
  execSync('node site-src/build.mjs', { cwd: REPO, stdio: 'inherit' });
}

function walk(dir, base = '') {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const rel = base ? `${base}/${name}` : name;
    if (statSync(p).isDirectory()) out.push(...walk(p, rel));
    else out.push(rel);
  }
  return out;
}

const srcFiles = walk(SRC);
let copied = 0;
const differences = [];

for (const rel of srcFiles) {
  const from = join(SRC, rel);
  const to = join(DEST, rel);
  const same = existsSync(to) && readFileSync(from).equals(readFileSync(to));
  if (same) continue;
  differences.push(rel);
  if (!checkOnly) {
    mkdirSync(dirname(to), { recursive: true });
    copyFileSync(from, to);
    copied++;
  }
}

// 產出裡沒有、正門卻有的檔＝上一版留下的殘骸，清掉（KEEP 名單除外）
const srcSet = new Set(srcFiles);
const stale = [];
for (const rel of walk(DEST)) {
  const top = rel.split('/')[0];
  if (KEEP.has(top) || KEEP.has(rel)) continue;
  if (!srcSet.has(rel)) {
    stale.push(rel);
    if (!checkOnly) rmSync(join(DEST, rel), { force: true });
  }
}

if (checkOnly) {
  if (!differences.length && !stale.length) {
    console.log('✓ 兩邊一致，不必搬');
  } else {
    console.log(`⚠ 兩邊不一樣：${differences.length} 個檔要更新、${stale.length} 個舊檔要清`);
    [...differences.slice(0, 10), ...stale.slice(0, 5)].forEach((f) => console.log('   ' + f));
    process.exitCode = 1;
  }
} else {
  console.log(`\n✓ 搬好了：更新 ${copied} 個檔、清掉 ${stale.length} 個舊檔`);
  console.log(`  保留未動：${[...KEEP].filter((k) => existsSync(join(DEST, k))).join('、')}`);
  console.log(`\n  接著發佈：cd ${DEST} && npx vercel deploy --prod --yes\n`);
}
