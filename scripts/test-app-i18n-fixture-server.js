'use strict';

const assert = require('node:assert/strict');
const http = require('node:http');
const {
  LOCAL_ONLY_CSP,
  createFixtureServer,
  injectPreviewBootstrap,
  listen,
  localAuthConfig,
  parsePort,
  stripExternalResources,
} = require('./app-i18n-fixture-server.js');

function request(port, pathname, method = 'GET') {
  return new Promise((resolve, reject) => {
    const req = http.request(
      {
        host: '127.0.0.1',
        port,
        path: pathname,
        method,
      },
      (res) => {
        const chunks = [];
        res.on('data', (chunk) => chunks.push(chunk));
        res.on('end', () => resolve({
          body: Buffer.concat(chunks).toString('utf8'),
          headers: res.headers,
          statusCode: res.statusCode,
        }));
      },
    );
    req.on('error', reject);
    req.end();
  });
}

async function main() {
  assert.equal(parsePort([]), 4177);
  assert.equal(parsePort(['--port', '4312']), 4312);
  assert.throws(() => parsePort(['--port', '80']), /between 1024 and 65535/);

  const html = [
    '<link rel="preconnect" href="https://fonts.googleapis.com">',
    '<link href="https://fonts.googleapis.com/css2?family=Poppins" rel="stylesheet">',
    '<main>Munea</main>',
  ].join('\n');
  const stripped = stripExternalResources(html);
  assert.ok(!stripped.includes('fonts.googleapis.com'));
  assert.ok(stripped.includes('<main>Munea</main>'));
  assert.ok(LOCAL_ONLY_CSP.includes("connect-src 'self'"));
  assert.ok(!LOCAL_ONLY_CSP.includes('https:'));

  const config = localAuthConfig(4312);
  assert.ok(config.includes("brainUrl: 'http://127.0.0.1:4312'"));
  assert.ok(config.includes("voiceUrl: 'ws://127.0.0.1:4312/local-voice-disabled'"));
  assert.ok(!config.includes('supabase.co'));
  assert.ok(!config.includes('run.app'));
  const preview = injectPreviewBootstrap(
    '<script src="src/i18n.js?v=1"></script>',
    4312,
    'ja',
  );
  assert.ok(preview.includes("i18nPreviewLocale: 'ja'"));
  assert.ok(
    preview.indexOf('i18nPreviewLocale') < preview.indexOf('src="src/i18n.js'),
  );
  assert.equal(
    injectPreviewBootstrap('<script src="src/i18n.js"></script>', 4312, 'fr'),
    '<script src="src/i18n.js"></script>',
  );

  const server = createFixtureServer({ port: 0 });
  await listen(server, 0);
  const port = server.address().port;
  try {
    const index = await request(port, '/');
    assert.equal(index.statusCode, 200);
    assert.equal(index.headers['x-munea-fixture'], 'app-i18n-local-only');
    assert.equal(index.headers['content-security-policy'], LOCAL_ONLY_CSP);
    assert.ok(!index.body.includes('https://fonts.googleapis.com'));
    assert.ok(index.body.includes('id="home"'));

    const localizedIndex = await request(port, '/?lang=es');
    assert.ok(localizedIndex.body.includes("i18nPreviewLocale: 'es'"));
    assert.ok(
      localizedIndex.body.indexOf('i18nPreviewLocale')
        < localizedIndex.body.indexOf('src="src/i18n.js'),
    );

    const qaPreview = await request(port, '/i18n-preview.html?locale=ja');
    assert.equal(qaPreview.statusCode, 200);
    assert.ok(qaPreview.body.includes('Munea local i18n QA'));
    assert.ok(qaPreview.body.includes('../web/src/i18n/app-renderer-copy.js'));
    const rendererCopy = await request(port, '/web/src/i18n/app-renderer-copy.js');
    assert.equal(rendererCopy.statusCode, 200);
    assert.ok(rendererCopy.body.includes('MuneaAppRendererCopy'));

    const authConfig = await request(port, '/src/auth-config.js');
    assert.equal(authConfig.statusCode, 200);
    assert.ok(authConfig.body.includes('Local i18n visual-QA fixture'));
    assert.ok(!authConfig.body.includes('SUPABASE'));

    const api = await request(port, '/person-profile', 'POST');
    assert.equal(api.statusCode, 200);
    assert.deepEqual(JSON.parse(api.body), {
      ok: true,
      fixture: true,
      items: [],
      members: [],
      reminders: [],
      events: [],
      data: [],
    });

    const traversal = await request(port, '/..%2Fpackage.json');
    assert.equal(traversal.statusCode, 404);
    assert.ok(!traversal.body.includes('"scripts"'));
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }

  process.stdout.write('App i18n fixture server contract passed.\n');
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
