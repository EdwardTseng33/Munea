const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'web', 'src', 'voice-call-diagnostics.js'), 'utf8');

function makeStorage(seed = {}) {
  const values = new Map(Object.entries(seed));
  return {
    getItem(key) { return values.has(key) ? values.get(key) : null; },
    setItem(key, value) { values.set(key, String(value)); },
    removeItem(key) { values.delete(key); },
    dump() { return Object.fromEntries(values); },
  };
}

function load(storage, reports) {
  const window = {
    crypto: { randomUUID: () => '11111111-2222-4333-8444-555555555555' },
    localStorage: storage,
    location: { href: 'https://app.munea.net/index.html' },
    console: { info() {} },
  };
  const context = vm.createContext({ window, URL, Date, Math, JSON, String, Number, Array, Object, RegExp });
  vm.runInContext(source, context, { filename: 'voice-call-diagnostics.js' });
  if (reports) window.MuneaVoiceDiagnostics.setReporter((eventName, properties) => reports.push({ eventName, properties }));
  return window.MuneaVoiceDiagnostics;
}

const storage = makeStorage();
const reports = [];
const diag = load(storage, reports);
diag.start({
  routeMode: 'gateway',
  voiceEndpoint: 'wss://voice.example/ws?token=do-not-store',
  avatarEndpoint: 'https://avatar.example/offer?key=do-not-store',
  transcript: 'private words',
});
diag.mark('gateway_assigned', 'pass', { gatewayCallId: 'call-123', token: 'secret-token' });
diag.mark('voice_socket_open', 'pass', { endpoint: 'wss://voice.example/ws?key=secret' });
diag.fail('voice_socket_closed', 'ws_4403', { closeCode: 4403, closeReason: 'call token required' });
const summary = diag.end('failed', { reason: 'voice_socket_closed' });

assert.strictEqual(summary.outcome, 'failed');
assert.strictEqual(summary.lastSuccessfulStage, 'voice_socket_open');
assert.strictEqual(summary.firstFailedStage, 'voice_socket_closed');
assert(summary.stages.some(stage => stage.stage === 'gateway_assigned'));
const serialized = JSON.stringify(storage.dump());
assert(!serialized.includes('do-not-store'));
assert(!serialized.includes('secret-token'));
assert(!serialized.includes('private words'));
assert(reports.some(item => item.eventName === 'voice_call_stage_failed'));
const terminal = reports.find(item => item.eventName === 'voice_call_diagnostic');
assert(terminal, 'terminal diagnostic summary must be reported');
assert(terminal.properties.stages.some(stage => stage.stage === 'voice_socket_open'));

diag.start({ appVersion: '1.0.18' });
const cancelled = diag.end('cancelled', { reason: 'user_cancelled' });
assert.strictEqual(cancelled.outcome, 'cancelled');

const abandonedStorage = makeStorage();
const firstLoad = load(abandonedStorage);
firstLoad.start({ routeMode: 'development_direct' });
firstLoad.mark('voice_socket_open', 'pass');
const recoveredReports = [];
load(abandonedStorage, recoveredReports);
const abandoned = recoveredReports.find(item => item.eventName === 'voice_call_diagnostic');
assert(abandoned, 'unfinished trace must be reported after the next launch');
assert.strictEqual(abandoned.properties.outcome, 'abandoned');
assert.strictEqual(abandoned.properties.reason, 'app_terminated_or_reloaded');

const appSource = fs.readFileSync(path.join(__dirname, '..', 'web', 'src', 'app.js'), 'utf8');
const indexSource = fs.readFileSync(path.join(__dirname, '..', 'web', 'index.html'), 'utf8');
assert(indexSource.indexOf('src/voice-call-diagnostics.js') < indexSource.indexOf('src/app.js'), 'diagnostics must load before the App module');
[
  'microphone_ready',
  'gateway_assigned',
  'voice_socket_open',
  'voice_ready',
  'avatar_offer_accepted',
  'avatar_first_frame',
  'opening_audio_ready',
  'voice_first_audio',
  'asr_first_caption',
  'call_connected',
].forEach(stage => assert(appSource.includes("'" + stage + "'"), 'missing App trace stage: ' + stage));
assert(source.includes("mark('dial_tapped'"), 'trace must start at the call button tap');
assert(appSource.includes('closeCode: event.code') && appSource.includes('closeReason: event.reason'), 'WebSocket close code and reason must be captured');

console.log('Voice call diagnostics contracts: PASS');
