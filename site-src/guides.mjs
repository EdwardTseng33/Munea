/**
 * 沐寧官網 · 指南文章（site-src/guides/<語系>/<slug>.md → 網頁）
 * ------------------------------------------------------------------
 * 2026-11-18 新增。為什麼自己寫一個小轉換器、不裝套件：
 *   官網發佈流程只有 node，沒有 npm install 這一步；文章只用得到很小一組 Markdown，
 *   而且我們要「看到不支援的寫法就報錯」，不要像一般轉換器那樣默默吞掉。
 *
 * 支援：## ／### 標題、段落、- 清單、1. 清單、**粗體**、[文字](網址)、> 單段提醒、表格。
 * 檔頭（--- 之間）：title, description, slug, published, updated, readingMinutes, keywords, related。
 */
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const REQUIRED = ['title', 'description', 'slug', 'published', 'updated', 'readingMinutes'];

/* 紅線字：任何一篇出現就停止產生網站（2026-07-21 Edward 拍板「沐寧是陪伴，不是監控」） */
const RED_LINES = {
  zh: /追蹤|監測|監控/,
  ja: /監視|追跡|モニタリング/,
  en: /\b(track|tracks|tracked|tracking|monitor|monitors|monitored|monitoring|surveillance|spy)\b/i,
  es: /seguimiento|monitore|monitoriz|vigilancia|rastre/i,
};

const FAQ_HEADINGS = /^(常見問題|よくある質問|FAQ|Preguntas frecuentes)$/i;
const SOURCE_HEADINGS = /^(參考資料|参考資料|Sources|Fuentes)$/i;

export function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function inline(src, ctx) {
  if (/<[a-z/!]/i.test(src)) throw new Error(`${ctx}：內文不可以有 HTML 標籤 → ${src.slice(0, 60)}`);
  let t = esc(src);
  t = t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  t = t.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, txt, url) => {
    const ext = /^https?:\/\//.test(url);
    if (!ext && !url.startsWith('/') && !url.startsWith('#')) throw new Error(`${ctx}：連結要是 https:// 或 / 開頭 → ${url}`);
    return `<a href="${url}"${ext ? ' target="_blank" rel="noopener"' : ''}>${txt}</a>`;
  });
  if (/\*\*|\]\(/.test(t)) throw new Error(`${ctx}：粗體或連結沒有成對 → ${src.slice(0, 60)}`);
  return t;
}

const plain = (s) => s.replace(/\*\*(.+?)\*\*/g, '$1').replace(/\[([^\]]+)\]\([^)]+\)/g, '$1').trim();

function parseFrontMatter(raw, file) {
  const m = raw.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/);
  if (!m) throw new Error(`${file}：缺少 --- 檔頭`);
  const meta = {};
  for (const line of m[1].split(/\r?\n/)) {
    if (!line.trim()) continue;
    const i = line.indexOf(':');
    if (i < 0) throw new Error(`${file}：檔頭這行看不懂 → ${line}`);
    meta[line.slice(0, i).trim()] = line.slice(i + 1).trim();
  }
  for (const k of REQUIRED) if (!meta[k]) throw new Error(`${file}：檔頭少了 ${k}`);
  return { meta, body: m[2] };
}

/** 把一篇文章的 Markdown 轉成 HTML，順便取出目錄與常見問題 */
function renderBody(md, locale, file) {
  const joiner = locale === 'zh' || locale === 'ja' ? '' : ' ';
  const lines = md.replace(/\r\n/g, '\n').split('\n');
  const out = [];
  const toc = [];
  const faq = [];
  let para = [];
  let list = null; // { tag, items }
  let section = '';
  let h2n = 0;
  let faqQ = null;

  const flushPara = () => {
    if (!para.length) return;
    const text = para.join(joiner);
    out.push(`<p>${inline(text, file)}</p>`);
    if (faqQ) { faqQ.a.push(plain(text)); }
    para = [];
  };
  const flushList = () => {
    if (!list) return;
    out.push(`<${list.tag}>${list.items.map((x) => `<li>${inline(x, file)}</li>`).join('')}</${list.tag}>`);
    list = null;
  };
  const flushAll = () => { flushPara(); flushList(); };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const t = line.trim();
    if (!t) { flushAll(); continue; }
    if (/^#\s/.test(t)) throw new Error(`${file}：內文不要用 # 一級標題（標題放檔頭 title）`);
    if (/^```|^!\[|^<\w/.test(t)) throw new Error(`${file}：不支援的寫法 → ${t.slice(0, 40)}`);
    let m;
    if ((m = t.match(/^##\s+(.+)$/)) && !t.startsWith('###')) {
      flushAll();
      faqQ = null;
      section = plain(m[1]);
      h2n++;
      const id = `s${h2n}`;
      out.push(`<h2 id="${id}">${inline(m[1], file)}</h2>`);
      if (!FAQ_HEADINGS.test(section) && !SOURCE_HEADINGS.test(section)) toc.push({ id, text: plain(m[1]) });
      continue;
    }
    if ((m = t.match(/^###\s+(.+)$/))) {
      flushAll();
      out.push(`<h3>${inline(m[1], file)}</h3>`);
      if (FAQ_HEADINGS.test(section)) { faqQ = { q: plain(m[1]), a: [] }; faq.push(faqQ); }
      continue;
    }
    if (t.startsWith('|')) {
      flushAll();
      const rows = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) { rows.push(lines[i].trim()); i++; }
      i--;
      if (rows.length < 2 || !/^\|[\s:|-]+\|$/.test(rows[1])) throw new Error(`${file}：表格第二行要是 |---|---|`);
      const cells = (r) => r.replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
      const head = cells(rows[0]);
      const body = rows.slice(2).map(cells);
      for (const r of body) if (r.length !== head.length) throw new Error(`${file}：表格欄數不一致 → ${r.join(' | ').slice(0, 60)}`);
      out.push(`<div class="g-table" role="region" tabindex="0" aria-label="${esc(head.join(' / '))}"><table><thead><tr>${head.map((c) => `<th scope="col">${inline(c, file)}</th>`).join('')}</tr></thead><tbody>${body.map((r) => `<tr>${r.map((c) => `<td>${inline(c, file)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`);
      continue;
    }
    if ((m = t.match(/^>\s?(.*)$/))) {
      flushAll();
      const q = [m[1]];
      while (i + 1 < lines.length && /^>\s?/.test(lines[i + 1].trim())) { i++; q.push(lines[i].trim().replace(/^>\s?/, '')); }
      out.push(`<blockquote><p>${inline(q.filter(Boolean).join(joiner), file)}</p></blockquote>`);
      continue;
    }
    if ((m = t.match(/^[-*]\s+(.+)$/))) {
      flushPara();
      if (list && list.tag !== 'ul') flushList();
      if (!list) list = { tag: 'ul', items: [] };
      list.items.push(m[1]);
      continue;
    }
    if ((m = t.match(/^\d+[.)]\s+(.+)$/))) {
      flushPara();
      if (list && list.tag !== 'ol') flushList();
      if (!list) list = { tag: 'ol', items: [] };
      list.items.push(m[1]);
      continue;
    }
    if (/^\s{2,}[-*\d]/.test(line)) throw new Error(`${file}：不支援多層清單 → ${t.slice(0, 40)}`);
    if (list) {
      // 清單項目換行續寫
      list.items[list.items.length - 1] += joiner + t;
      continue;
    }
    para.push(t);
  }
  flushAll();
  return { html: out.join('\n'), toc, faq: faq.filter((f) => f.a.length) };
}

/** 讀一個語系的全部文章（照 published 新到舊、同日照檔名） */
export function loadGuides(srcDir, locale) {
  const dir = join(srcDir, 'guides', locale);
  if (!existsSync(dir)) return [];
  const files = readdirSync(dir).filter((f) => f.endsWith('.md')).sort();
  const guides = files.map((f) => {
    const file = `guides/${locale}/${f}`;
    const raw = readFileSync(join(dir, f), 'utf8');
    const { meta, body } = parseFrontMatter(raw, file);
    if (meta.slug + '.md' !== f) throw new Error(`${file}：slug 要跟檔名一樣（${meta.slug}）`);
    if (!/^[a-z0-9-]+$/.test(meta.slug)) throw new Error(`${file}：slug 只能用小寫英文、數字、連字號`);
    const red = RED_LINES[locale];
    if (red && red.test(raw)) throw new Error(`${file}：出現紅線字 ${raw.match(red)[0]}（不准用來形容沐寧，也不要用來形容別家）`);
    const { html, toc, faq } = renderBody(body, locale, file);
    return {
      ...meta,
      locale,
      readingMinutes: Number(meta.readingMinutes),
      related: (meta.related || '').split(',').map((s) => s.trim()).filter(Boolean),
      html, toc, faq,
    };
  });
  const slugs = new Set(guides.map((g) => g.slug));
  for (const g of guides) {
    g.related = g.related.filter((r) => slugs.has(r) && r !== g.slug);
  }
  return guides.sort((a, b) => (a.published < b.published ? 1 : a.published > b.published ? -1 : a.slug.localeCompare(b.slug)));
}
