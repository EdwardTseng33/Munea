import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const target = process.env.B2B_CALL_URL || 'https://munea-b2b.vercel.app/call.html?debug=1';
const passphrase = process.env.B2B_DEMO_PASS;
const screenshotPath = process.env.B2B_CALL_SCREENSHOT || 'b2b-call-browser.png';
const helloScreenshotPath = process.env.B2B_CALL_HELLO_SCREENSHOT || '';
const callConfig = process.env.B2B_CALL_CONFIG_JSON ? JSON.parse(process.env.B2B_CALL_CONFIG_JSON) : null;
const testChar = process.env.B2B_TEST_CHAR || 'a05';
const captureIdle = process.env.B2B_CAPTURE_IDLE === '1';
const viewport = {
  width: Number(process.env.B2B_VIEWPORT_WIDTH || 430),
  height: Number(process.env.B2B_VIEWPORT_HEIGHT || 932),
};

if (!passphrase) {
  throw new Error('B2B_DEMO_PASS is required');
}

const browser = await chromium.launch({
  executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  headless: true,
  args: [
    '--autoplay-policy=no-user-gesture-required',
    '--use-fake-device-for-media-stream',
    '--use-fake-ui-for-media-stream',
  ],
});

const context = await browser.newContext({
  viewport,
  permissions: ['microphone'],
});
const page = await context.newPage();
if (callConfig) {
  await page.route('**/api/call-key', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(callConfig),
  }));
}
const consoleLines = [];
page.on('console', message => {
  const line = `${message.type()}: ${message.text()}`;
  consoleLines.push(line);
  if (line.includes('[b2b-call]')) process.stdout.write(`${line}\n`);
});
page.on('pageerror', error => consoleLines.push(`pageerror: ${error.message}`));

let result;
let controlInteractions = null;
try {
  await page.goto(target, { waitUntil: 'domcontentloaded', timeout: 30_000 });
  const gate = page.locator('#gate');
  if (await gate.evaluate(node => node.classList.contains('show'))) {
    await page.locator('#gateInput').fill(passphrase);
    await page.locator('#gateBtn').click();
    await page.waitForFunction(() => !document.querySelector('#gate').classList.contains('show'), null, { timeout: 20_000 });
  }

  if (testChar === 'a06') await page.locator('#charA06').click();
  await page.waitForFunction(expected => typeof curChar !== 'undefined' && curChar === expected, testChar);

  if (captureIdle) {
    await page.waitForFunction(() => typeof IdleMotion !== 'undefined' && IdleMotion.active && IdleMotion.front && !IdleMotion.front.classList.contains('hide'));
    const helloSrc = await page.evaluate(() => IdleMotion.front.currentSrc);
    if (helloScreenshotPath) {
      await page.waitForTimeout(900);
      await page.screenshot({ path: helloScreenshotPath, fullPage: true });
    }
    await page.waitForFunction(() => typeof IdleMotion !== 'undefined' && IdleMotion.active && /-idle\.mp4(?:$|\?)/.test(IdleMotion.front.currentSrc), null, { timeout: 20_000 });
    const idleSrc = await page.evaluate(() => IdleMotion.front.currentSrc);
    await page.locator('#captionToggle').click();
    const captionOn = await page.locator('#captionToggle').evaluate(node => node.classList.contains('on'));
    await page.locator('#captionToggle').click();
    await page.locator('#micToggle').click();
    const micOff = await page.locator('#micToggle').evaluate(node => node.classList.contains('off'));
    await page.locator('#micToggle').click();
    controlInteractions = { captionOn, micOff, helloSrc, idleSrc };
  } else {
    await page.locator('#callBtn').click();
    await page.waitForFunction(() => {
      const logs = typeof DBGBUF === 'undefined' ? [] : DBGBUF;
      const connected = typeof Face !== 'undefined' && Face.pc?.connectionState === 'connected';
      const voiceReady = typeof Live !== 'undefined' && Live.ws?.readyState === WebSocket.OPEN && Live.mic;
      const frames = window.__flashheadStats?.vidFrames || 0;
      const backendReady = logs.some(line => line.includes('[voice] ready'));
      const online = document.querySelector('#statusBadge')?.textContent === '在線';
      const failed = logs.some(line => line.includes('[dial] attempt=2 failed'));
      return (connected && voiceReady && backendReady && online && frames > 0) || failed;
    }, null, { timeout: 150_000 });
  }

  result = await page.evaluate(() => ({
    status: document.querySelector('#statusBadge')?.textContent,
    selectedChar: typeof curChar === 'undefined' ? null : curChar,
    hint: document.querySelector('#hint')?.textContent,
    toast: document.querySelector('#toast')?.textContent,
    faceConnection: typeof Face === 'undefined' ? null : Face.pc?.connectionState,
    voiceState: typeof Live === 'undefined' ? null : Live.ws?.readyState,
    voiceReady: typeof DBGBUF !== 'undefined' && DBGBUF.some(line => line.includes('[voice] ready')),
    hasMic: typeof Live === 'undefined' ? false : Boolean(Live.mic),
    frames: window.__flashheadStats?.vidFrames || 0,
    idleMotionActive: typeof IdleMotion === 'undefined' ? null : IdleMotion.active,
    controls: ['captionToggle','micToggle','callBtn','closeBtn'].every(id => Boolean(document.getElementById(id))),
    attempts: typeof Face === 'undefined' ? [] : Face._diagAttempts,
    logs: typeof DBGBUF === 'undefined' ? [] : DBGBUF,
  }));
  result.controlInteractions = controlInteractions;
  await page.screenshot({ path: screenshotPath, fullPage: true });
} finally {
  await browser.close();
}

process.stdout.write(`${JSON.stringify({ target, result, consoleErrors: consoleLines.filter(line => /error|failed/i.test(line)) }, null, 2)}\n`);

const idleFailed = captureIdle && (!result || result.selectedChar !== testChar || result.status !== '未在線' || !result.controls || !result.controlInteractions?.captionOn || !result.controlInteractions?.micOff || !/-hello\.mp4(?:$|\?)/.test(result.controlInteractions?.helloSrc || '') || !/-idle\.mp4(?:$|\?)/.test(result.controlInteractions?.idleSrc || ''));
const callFailed = !captureIdle && (!result || result.selectedChar !== testChar || result.status !== '在線' || result.faceConnection !== 'connected' || result.voiceState !== 1 || !result.voiceReady || !result.hasMic || result.frames < 1 || result.idleMotionActive !== false);
if (idleFailed || callFailed) {
  process.exitCode = 1;
}
