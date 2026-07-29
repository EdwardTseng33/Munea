'use strict';

const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const WEB_ROOT = path.join(ROOT, 'web');
const QA_PREVIEW_PATH = path.join(ROOT, 'tools', 'i18n-preview.html');
const LOOPBACK_HOST = '127.0.0.1';
const DEFAULT_PORT = 4177;
const PREVIEW_LOCALES = new Set(['zh-TW', 'en', 'ja', 'es']);

const CONTENT_TYPES = Object.freeze({
  '.css': 'text/css; charset=utf-8',
  '.gif': 'image/gif',
  '.html': 'text/html; charset=utf-8',
  '.ico': 'image/x-icon',
  '.jpeg': 'image/jpeg',
  '.jpg': 'image/jpeg',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.m4a': 'audio/mp4',
  '.mp3': 'audio/mpeg',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.wav': 'audio/wav',
  '.webp': 'image/webp',
  '.woff2': 'font/woff2',
});

const LOCAL_ONLY_CSP = [
  "default-src 'self' data: blob:",
  "connect-src 'self' ws://127.0.0.1:* ws://localhost:*",
  "font-src 'self' data:",
  "img-src 'self' data: blob:",
  "media-src 'self' data: blob:",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "worker-src 'self' blob:",
].join('; ');

function parsePort(argv = process.argv.slice(2)) {
  const index = argv.indexOf('--port');
  if (index < 0) return DEFAULT_PORT;
  const port = Number(argv[index + 1]);
  if (!Number.isInteger(port) || port < 1024 || port > 65535) {
    throw new Error('Fixture port must be an integer between 1024 and 65535');
  }
  return port;
}

function stripExternalResources(html) {
  return html
    .replace(
      /<link\b[^>]*href=["']https:\/\/fonts\.(?:googleapis|gstatic)\.com[^>]*>\s*/gi,
      '',
    )
    .replace(
      /<link\b[^>]*rel=["']preconnect["'][^>]*href=["']https:\/\/fonts\.(?:googleapis|gstatic)\.com[^>]*>\s*/gi,
      '',
    );
}

function localAuthConfig(port, previewLocale = null) {
  const origin = `http://${LOOPBACK_HOST}:${port}`;
  const lines = [
    '// Local i18n visual-QA fixture. No Supabase or production endpoint is configured.',
    "try { localStorage.setItem('munea.avatarUrl', ''); } catch (error) {}",
    'window.MUNEA_DEV_CONFIG = {',
    '  enabled: true,',
    '  autoSignIn: false,',
    '  skipOnboarding: true,',
    '  seedFixtures: true,',
    '  resetFixturesOnLaunch: true,',
    "  fixtureVersion: 'i18n-local-v1',",
    "  profileName: 'Munea QA',",
    "  plan: 'pro',",
    '  purchasedPoints: 700,',
    '  bypassCallControl: false,',
    '  analyticsExcluded: true,',
    `  brainUrl: '${origin}',`,
    `  callControlUrl: '${origin}',`,
    `  voiceUrl: 'ws://${LOOPBACK_HOST}:${port}/local-voice-disabled',`,
  ];
  if (PREVIEW_LOCALES.has(previewLocale)) {
    lines.push(`  i18nPreviewLocale: '${previewLocale}',`);
  }
  return [...lines, '};', ''].join('\n');
}

function injectPreviewBootstrap(html, port, previewLocale) {
  if (!PREVIEW_LOCALES.has(previewLocale)) return html;
  const marker = '<script src="src/i18n.js';
  const index = html.indexOf(marker);
  if (index < 0) throw new Error('App index is missing the i18n bootstrap script');
  const bootstrap = `<script>${localAuthConfig(port, previewLocale)}</script>\n  `;
  return `${html.slice(0, index)}${bootstrap}${html.slice(index)}`;
}

function fixturePayload(pathname) {
  if (pathname === '/health') {
    return { ok: true, environment: 'local-i18n-fixture' };
  }
  if (pathname === '/version') {
    return {
      schema: 'munea.service-release.v1',
      service: 'local-i18n-fixture',
      environment: 'local',
      commit: 'local-only',
      revision: 'local-only',
    };
  }
  if (pathname === '/auth-status') {
    return { ok: false, authenticated: false, fixture: true };
  }
  return {
    ok: true,
    fixture: true,
    items: [],
    members: [],
    reminders: [],
    events: [],
    data: [],
  };
}

function responseHeaders(contentType) {
  return {
    'cache-control': 'no-store',
    'content-security-policy': LOCAL_ONLY_CSP,
    'content-type': contentType,
    'x-content-type-options': 'nosniff',
    'x-munea-fixture': 'app-i18n-local-only',
  };
}

function safeStaticPath(pathname) {
  let decoded;
  try {
    decoded = decodeURIComponent(pathname);
  } catch {
    return null;
  }
  const relative = decoded === '/'
    ? 'index.html'
    : (
      decoded.startsWith('/web/')
        ? decoded.slice('/web/'.length)
        : decoded.replace(/^\/+/, '')
    );
  const target = path.resolve(WEB_ROOT, relative);
  const prefix = WEB_ROOT.endsWith(path.sep) ? WEB_ROOT : `${WEB_ROOT}${path.sep}`;
  return target === WEB_ROOT || target.startsWith(prefix) ? target : null;
}

function createFixtureServer({ port = DEFAULT_PORT } = {}) {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url || '/', `http://${LOOPBACK_HOST}:${port}`);
    const pathname = url.pathname;

    if (pathname === '/src/auth-config.js') {
      res.writeHead(200, responseHeaders('text/javascript; charset=utf-8'));
      res.end(localAuthConfig(port));
      return;
    }

    if (req.method !== 'GET' && req.method !== 'HEAD') {
      res.writeHead(200, responseHeaders('application/json; charset=utf-8'));
      res.end(JSON.stringify(fixturePayload(pathname)));
      return;
    }

    const target = pathname === '/i18n-preview.html'
      ? QA_PREVIEW_PATH
      : safeStaticPath(pathname);
    if (!target || !fs.existsSync(target) || !fs.statSync(target).isFile()) {
      if (!path.extname(pathname)) {
        res.writeHead(200, responseHeaders('application/json; charset=utf-8'));
        res.end(JSON.stringify(fixturePayload(pathname)));
      } else {
        res.writeHead(404, responseHeaders('application/json; charset=utf-8'));
        res.end(JSON.stringify({ ok: false, fixture: true, error: 'not_found' }));
      }
      return;
    }

    const extension = path.extname(target).toLowerCase();
    const contentType = CONTENT_TYPES[extension] || 'application/octet-stream';
    let body = fs.readFileSync(target);
    if (extension === '.html') {
      const previewLocale = url.searchParams.get('lang');
      const html = injectPreviewBootstrap(
        stripExternalResources(body.toString('utf8')),
        port,
        previewLocale,
      );
      body = Buffer.from(html, 'utf8');
    }
    res.writeHead(200, responseHeaders(contentType));
    if (req.method === 'HEAD') {
      res.end();
      return;
    }
    res.end(body);
  });
  return server;
}

function listen(server, port = DEFAULT_PORT) {
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, LOOPBACK_HOST, () => {
      server.removeListener('error', reject);
      resolve(server);
    });
  });
}

if (require.main === module) {
  const port = parsePort();
  const server = createFixtureServer({ port });
  listen(server, port)
    .then(() => {
      process.stdout.write(
        `Munea App i18n fixture listening on http://${LOOPBACK_HOST}:${port}\n`,
      );
    })
    .catch((error) => {
      process.stderr.write(`${error.stack || error}\n`);
      process.exitCode = 1;
    });
}

module.exports = {
  DEFAULT_PORT,
  LOCAL_ONLY_CSP,
  LOOPBACK_HOST,
  createFixtureServer,
  fixturePayload,
  injectPreviewBootstrap,
  listen,
  localAuthConfig,
  parsePort,
  safeStaticPath,
  stripExternalResources,
};
