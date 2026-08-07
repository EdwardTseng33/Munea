import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const target = process.env.B2B_CALL_URL || 'https://munea-b2b.vercel.app/call.html?debug=1';
const expectsMic = !new URL(target).searchParams.has('nomic');
const passphrase = process.env.B2B_DEMO_PASS;
const screenshotPath = process.env.B2B_CALL_SCREENSHOT || 'b2b-call-browser.png';
const helloScreenshotPath = process.env.B2B_CALL_HELLO_SCREENSHOT || '';
const callConfig = process.env.B2B_CALL_CONFIG_JSON ? JSON.parse(process.env.B2B_CALL_CONFIG_JSON) : null;
const localHtmlPath = process.env.B2B_LOCAL_HTML || '';
const testChar = process.env.B2B_TEST_CHAR || 'a05';
const captureIdle = process.env.B2B_CAPTURE_IDLE === '1';
const mockConnect = process.env.B2B_MOCK_CONNECT === '1';
const verifySustained = process.env.B2B_VERIFY_SUSTAINED === '1';
const verifyRelock = process.env.B2B_VERIFY_RELOCK === '1';
const fakeAudioFile = process.env.B2B_FAKE_AUDIO_FILE || '';
const viewport = {
  width: Number(process.env.B2B_VIEWPORT_WIDTH || 430),
  height: Number(process.env.B2B_VIEWPORT_HEIGHT || 932),
};

if (!passphrase) {
  throw new Error('B2B_DEMO_PASS is required');
}

const browser = await chromium.launch({
  executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  headless: process.env.B2B_HEADLESS !== '0',
  ignoreDefaultArgs: process.env.B2B_REAL_AUDIO === '1' ? ['--mute-audio'] : [],
  args: [
    '--autoplay-policy=no-user-gesture-required',
    '--use-fake-device-for-media-stream',
    '--use-fake-ui-for-media-stream',
    ...(fakeAudioFile ? [`--use-file-for-fake-audio-capture=${fakeAudioFile}`] : []),
  ],
});

const context = await browser.newContext({
  viewport,
  permissions: ['microphone'],
});
const page = await context.newPage();
if (localHtmlPath) {
  const localHtml = readFileSync(localHtmlPath, 'utf8');
  await page.route('**/call.html*', route => route.fulfill({
    status: 200,
    contentType: 'text/html; charset=utf-8',
    body: localHtml,
  }));
}
if (callConfig) {
  await page.route('**/api/call-key', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(callConfig),
  }));
  if (mockConnect) {
    await page.route('**/health?token=*', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, engine: 'mock-avatar', uptime_s: 1 }),
    }));
  }
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

  if (mockConnect) {
    await page.evaluate(() => {
      const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
      window.__mockConnectTimeline = [];
      wakeAvatarService = async () => {
        window.__mockConnectTimeline.push({ event: 'wake_start', at: performance.now() });
        await wait(120);
        window.__mockConnectTimeline.push({ event: 'wake_ready', at: performance.now() });
        return true;
      };
      Live.start = async () => {
        window.__mockConnectTimeline.push({ event: 'voice_start', at: performance.now() });
        await wait(20);
        Live.on = true;
        Live.ws = { readyState: WebSocket.OPEN, send(){}, close(){} };
        dbgLine('[voice] ready mock');
        window.__mockConnectTimeline.push({ event: 'voice_ready', at: performance.now() });
        return true;
      };
      Face.start = async () => {
        window.__mockConnectTimeline.push({ event: 'face_start', at: performance.now() });
        await wait(160);
        Face.on = true;
        Face.ws = { readyState: WebSocket.OPEN, send(){}, close(){} };
        Face.pc = { connectionState: 'connected', close(){}, getStats: async () => new Map() };
        Face.transport = 'webrtc';
        Face._videoReady = true;
        Face._audioReceiver = {};
        window.__flashheadStats.vidFrames = 1;
        window.__mockConnectTimeline.push({ event: 'face_ready', at: performance.now() });
        return true;
      };
      Face.prepareOpeningPath = async () => {
        window.__mockConnectTimeline.push({ event: 'av_warmup_start', at: performance.now() });
        await wait(100);
        overlay.classList.add('on');
        IdleMotion.stop();
        window.__mockConnectTimeline.push({ event: 'av_warmup_ready', at: performance.now() });
        return true;
      };
    });
  }

  if (verifySustained) {
    await page.evaluate(() => {
      const originalActivate = Live.activate.bind(Live);
      Live.activate = function monitoredActivate(){
        const monitor = window.__avMonitor = { startedAt: performance.now(), audio: [], mouth: [], errors: [] };
        try {
          const video = document.querySelector('#faceVid');
          const audioTrack = Face._renderStream?.getAudioTracks()[0];
          if (audioTrack) {
            const ctx = new AudioContext();
            // Measure the synchronized media element output, not the raw
            // receiver track that can run ahead of browser playout.
            const source = ctx.createMediaElementSource(video);
            const analyser = ctx.createAnalyser();
            analyser.fftSize = 512;
            source.connect(analyser);
            // Keep the measurement path active without playing test audio over
            // the operator's speakers.
            const silentGain = ctx.createGain(); silentGain.gain.value = 0;
            analyser.connect(silentGain); silentGain.connect(ctx.destination);
            ctx.resume().catch(() => {});
            const data = new Uint8Array(analyser.fftSize);
            monitor.audioTimer = setInterval(() => {
              analyser.getByteTimeDomainData(data);
              let energy = 0;
              for (let i = 0; i < data.length; i++) { const v = (data[i] - 128) / 128; energy += v * v; }
              monitor.audio.push([performance.now() - monitor.startedAt, Math.sqrt(energy / data.length)]);
            }, 20);
            monitor.audioContext = ctx;
          }
          const canvas = document.createElement('canvas'); canvas.width = 192; canvas.height = 192;
          const context2d = canvas.getContext('2d', { willReadFrequently: true });
          let previous = null;
          const regionDiff = (a, b, x0, y0, x1, y1) => {
            let total = 0, count = 0;
            for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) {
              const p = (y * 192 + x) * 4;
              total += Math.abs(a[p] - b[p]) + Math.abs(a[p+1] - b[p+1]) + Math.abs(a[p+2] - b[p+2]);
              count += 3;
            }
            return count ? total / count : 0;
          };
          const sampleVideo = () => {
            if (!window.__avMonitor || video.readyState < 2) return;
            try {
              context2d.drawImage(video, 0, 0, 192, 192);
              const pixels = context2d.getImageData(0, 0, 192, 192).data;
              if (previous) {
                const mouth = regionDiff(previous, pixels, 63, 104, 129, 131);
                const upper = regionDiff(previous, pixels, 63, 54, 129, 88);
                monitor.mouth.push([performance.now() - monitor.startedAt, Math.max(0, mouth - 0.55 * upper)]);
              }
              previous = new Uint8ClampedArray(pixels);
            } catch (error) { monitor.errors.push(String(error && error.message || error)); }
            if (video.requestVideoFrameCallback) video.requestVideoFrameCallback(sampleVideo);
          };
          if (video.requestVideoFrameCallback) video.requestVideoFrameCallback(sampleVideo);
        } catch (error) { monitor.errors.push(String(error && error.message || error)); }
        return originalActivate();
      };
    });
  }

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
      const connected = typeof Face !== 'undefined' && (
        Face.pc?.connectionState === 'connected' ||
        (Face.transport === 'stream' && Face.on && Face.stream?.readyState === WebSocket.OPEN)
      );
      const micReady = (typeof nomic !== 'undefined' && nomic) || Boolean(Live.mic);
      const voiceReady = typeof Live !== 'undefined' && Live.ws?.readyState === WebSocket.OPEN && micReady;
      const frames = window.__flashheadStats?.vidFrames || 0;
      const backendReady = logs.some(line => line.includes('[voice] ready'));
      const online = document.querySelector('#statusBadge')?.textContent === '在線';
      const failed = logs.some(line => line.includes('[dial] attempt=2 failed'));
      return (connected && voiceReady && backendReady && online && frames > 0) || failed;
    }, null, { timeout: 150_000 });
    if (verifySustained) {
      await page.waitForFunction(() => {
        const stats = window.__flashheadStats || {};
        return stats.vidFrames >= 40 && stats.audioBytes > 0 &&
          typeof Face !== 'undefined' && Face.transport === 'webrtc' && Face.on &&
          Face._audioReceiver && Face._renderStream?.getAudioTracks().length > 0 &&
          document.querySelector('#faceVid')?.muted === false &&
          typeof Live !== 'undefined' && Live.playHead === 0;
      }, null, { timeout: 60_000 });
      await page.waitForTimeout(Number(process.env.B2B_POST_READY_MS || 8000));
    }
  }

  result = await page.evaluate(() => ({
    status: document.querySelector('#statusBadge')?.textContent,
    selectedChar: typeof curChar === 'undefined' ? null : curChar,
    hint: document.querySelector('#hint')?.textContent,
    toast: document.querySelector('#toast')?.textContent,
    faceConnection: typeof Face === 'undefined' ? null :
      (Face.transport === 'stream' && Face.on ? 'connected' : Face.pc?.connectionState),
    avatarTransport: typeof Face === 'undefined' ? null : Face.transport,
    voiceState: typeof Live === 'undefined' ? null : Live.ws?.readyState,
    voiceReady: typeof DBGBUF !== 'undefined' && DBGBUF.some(line => line.includes('[voice] ready')),
    hasMic: typeof Live === 'undefined' ? false : Boolean(Live.mic),
    frames: window.__flashheadStats?.vidFrames || 0,
    audioBytes: window.__flashheadStats?.audioBytes || 0,
    playbackState: typeof Live === 'undefined' ? null : Live.playCtx?.state,
    playbackScheduledUntil: typeof Live === 'undefined' ? 0 : Live.playHead,
    tapPlayVisible: document.querySelector('#tapplay')?.classList.contains('show') || false,
    faceVideoMuted: document.querySelector('#faceVid')?.muted,
    renderAudioTracks: typeof Face === 'undefined' ? 0 : (Face._renderStream?.getAudioTracks().length || 0),
    audioReceiverAttached: typeof Face === 'undefined' ? false : Boolean(Face._audioReceiver),
    avMonitor: (() => {
      const monitor = window.__avMonitor;
      if (!monitor) return null;
      const median = values => {
        if (!values.length) return 0;
        const sorted = [...values].sort((a,b) => a-b);
        return sorted[Math.floor(sorted.length / 2)];
      };
      const threshold = (values, floor, sigma) => {
        const med = median(values);
        const mad = median(values.map(value => Math.abs(value - med)));
        return Math.max(floor, med + sigma * 1.4826 * mad);
      };
      const sustained = (samples, limit, count, spanMs) => {
        let run = [];
        for (const sample of samples) {
          if (sample[1] > limit) {
            run.push(sample);
            if (run.length >= count && run[run.length - 1][0] - run[run.length - count][0] <= spanMs) return run[run.length - count][0];
          } else run = [];
        }
        return null;
      };
      const audioThreshold = threshold(monitor.audio.filter(v => v[0] < 1500).map(v => v[1]), .008, 8);
      const mouthThreshold = threshold(monitor.mouth.filter(v => v[0] < 1500).map(v => v[1]), 1.15, 7);
      const audioOnMs = sustained(monitor.audio, audioThreshold, 3, 120);
      const mouthOnMs = sustained(monitor.mouth, mouthThreshold, 3, 180);
      const videoGaps = monitor.mouth.slice(1).map((v, i) => v[0] - monitor.mouth[i][0]);
      const nearest = (samples, target) => {
        let low = 0, high = samples.length - 1;
        while (low < high) {
          const middle = Math.floor((low + high) / 2);
          if (samples[middle][0] < target) low = middle + 1; else high = middle;
        }
        const left = Math.max(0, low - 1);
        return Math.abs(samples[left][0] - target) < Math.abs(samples[low][0] - target) ? samples[left][1] : samples[low][1];
      };
      let correlationOffsetMs = null, correlation = -2;
      if (audioOnMs != null && monitor.audio.length && monitor.mouth.length) {
        for (let lag = -1200; lag <= 1200; lag += 40) {
          const xs = [], ys = [];
          for (let t = audioOnMs; t <= audioOnMs + 4000; t += 40) {
            xs.push(nearest(monitor.audio, t));
            ys.push(nearest(monitor.mouth, t + lag));
          }
          const mx = xs.reduce((a,b) => a+b, 0) / xs.length;
          const my = ys.reduce((a,b) => a+b, 0) / ys.length;
          let top = 0, xx = 0, yy = 0;
          for (let i = 0; i < xs.length; i++) { const x = xs[i]-mx, y=ys[i]-my; top += x*y; xx += x*x; yy += y*y; }
          const score = top / Math.sqrt(Math.max(1e-12, xx * yy));
          if (score > correlation) { correlation = score; correlationOffsetMs = lag; }
        }
      }
      return {
        audioOnMs, mouthOnMs,
        avOffsetMs: audioOnMs != null && mouthOnMs != null ? mouthOnMs - audioOnMs : null,
        audioThreshold, mouthThreshold,
        videoSamples: monitor.mouth.length,
        longestVideoGapMs: videoGaps.length ? Math.max(...videoGaps) : null,
        correlationOffsetMs,
        correlation,
        errors: monitor.errors,
      };
    })(),
    idleMotionActive: typeof IdleMotion === 'undefined' ? null : IdleMotion.active,
    avatarRenderContract: typeof avatarRenderContract === 'undefined' ? null : avatarRenderContract,
    voiceActivated: typeof Live === 'undefined' ? null : Live._activated,
    mockConnectTimeline: window.__mockConnectTimeline || null,
    controls: ['captionToggle','micToggle','callBtn','closeBtn'].every(id => Boolean(document.getElementById(id))),
    overlayGeometry: (() => {
      const frame = document.getElementById('frame')?.getBoundingClientRect();
      const box = document.getElementById('overlay')?.getBoundingClientRect();
      const video = document.getElementById('faceVid');
      if (!frame || !box || !video) return null;
      return {
        topPct: ((box.top - frame.top) / frame.height) * 100,
        heightPct: (box.height / frame.height) * 100,
        objectFit: getComputedStyle(video).objectFit,
      };
    })(),
    attempts: typeof Face === 'undefined' ? [] : Face._diagAttempts,
    logs: typeof DBGBUF === 'undefined' ? [] : DBGBUF,
  }));
  if (verifyRelock && !captureIdle) {
    await page.locator('#callBtn').click();
    await page.waitForFunction(() => document.querySelector('#gate')?.classList.contains('show'));
    result.relock = await page.evaluate(() => ({
      gateVisible: document.querySelector('#gate')?.classList.contains('show') || false,
      passwordBlank: document.querySelector('#gateInput')?.value === '',
      avatarTokenCleared: typeof AVATAR_TOKEN !== 'undefined' && AVATAR_TOKEN === null,
      voiceKeyCleared: typeof VOICE_KEY !== 'undefined' && VOICE_KEY === null,
      avatarUrlCleared: typeof AVATAR_HTTP !== 'undefined' && AVATAR_HTTP === null,
      voiceUrlCleared: typeof VOICE_WS_BASE !== 'undefined' && VOICE_WS_BASE === null,
      prewarmCleared: typeof avatarPrewarmPromise !== 'undefined' && avatarPrewarmPromise === null,
      legacyPasswordCleared: sessionStorage.getItem('munea_pass') === null,
      legacyUnlockCleared: sessionStorage.getItem('munea_demo_unlocked') === null,
    }));
    // 模擬 1.0.2 曾留下的同分頁資料，再重新整理；新版仍必須回到密語門。
    await page.evaluate(() => {
      sessionStorage.setItem('munea_pass', 'legacy-value');
      sessionStorage.setItem('munea_demo_unlocked', '1');
    });
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => document.querySelector('#gate')?.classList.contains('show'));
    result.reloadRelock = await page.evaluate(() => ({
      gateVisible: document.querySelector('#gate')?.classList.contains('show') || false,
      passwordBlank: document.querySelector('#gateInput')?.value === '',
      legacyPasswordCleared: sessionStorage.getItem('munea_pass') === null,
      legacyUnlockCleared: sessionStorage.getItem('munea_demo_unlocked') === null,
    }));
  }
  result.controlInteractions = controlInteractions;
  await page.screenshot({ path: screenshotPath, fullPage: true });
} finally {
  await browser.close();
}

process.stdout.write(`${JSON.stringify({ target, result, consoleErrors: consoleLines.filter(line => /error|failed/i.test(line)) }, null, 2)}\n`);

const idleFailed = captureIdle && (!result || result.selectedChar !== testChar || result.status !== '未在線' || !result.controls || !result.controlInteractions?.captionOn || !result.controlInteractions?.micOff || !/-hello\.mp4(?:$|\?)/.test(result.controlInteractions?.helloSrc || '') || !/-idle\.mp4(?:$|\?)/.test(result.controlInteractions?.idleSrc || ''));
// 展示間走自己的實驗格（demo-*），不再跟正式 App 的 a05/a06 共用約定——2026-07-21 分家。
const geometryFailed = !result?.overlayGeometry || result?.avatarRenderContract?.version !== 'demo-flashhead-portrait-v1' || Math.abs(result.overlayGeometry.topPct - 7.291667) > 0.1 || Math.abs(result.overlayGeometry.heightPct - 75) > 0.1 || result.overlayGeometry.objectFit !== 'fill';
const timeline = result?.mockConnectTimeline || [];
const at = event => timeline.find(item => item.event === event)?.at;
const parallelFailed = mockConnect && (!(at('wake_ready') <= at('voice_start')) || !(at('wake_ready') <= at('face_start')) || Math.abs(at('voice_start') - at('face_start')) > 100 || !(at('voice_ready') <= at('av_warmup_start')) || !(at('face_ready') <= at('av_warmup_start')) || !(at('av_warmup_start') < at('av_warmup_ready')) || result?.voiceActivated !== true);
const sustainedFailed = verifySustained && (!result || result.frames < 40 || result.audioBytes < 1 || !result.audioReceiverAttached || result.renderAudioTracks < 1 || !result.faceVideoMuted || result.playbackScheduledUntil <= 0 || result.tapPlayVisible);
const relockFailed = verifyRelock && (
  !result?.relock || Object.values(result.relock).some(value => value !== true) ||
  !result?.reloadRelock || Object.values(result.reloadRelock).some(value => value !== true)
);
const callFailed = !captureIdle && (!result || result.selectedChar !== testChar || result.status !== '在線' || result.faceConnection !== 'connected' || result.voiceState !== 1 || !result.voiceReady || (expectsMic && !result.hasMic) || result.frames < 1 || result.idleMotionActive !== false || geometryFailed || parallelFailed || sustainedFailed);
if (idleFailed || callFailed || relockFailed) {
  process.exitCode = 1;
}
