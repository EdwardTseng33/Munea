(function installVoiceCallDiagnostics(global) {
  'use strict';

  const STORAGE_KEY = 'munea.voiceCallDiagnostics.v1';
  const MAX_HISTORY = 12;
  const MAX_STAGES = 80;
  const SECRET_KEY = /(token|secret|password|authorization|appkey|app_key|sdp|transcript|caption|reply|text)/i;
  let active = null;
  let reporter = null;
  const pendingReports = [];

  function wallNow() { return Date.now(); }
  function elapsedSince(startedAt) { return Math.max(0, wallNow() - Number(startedAt || wallNow())); }
  function makeId() {
    try { if (global.crypto && global.crypto.randomUUID) return global.crypto.randomUUID(); } catch (error) {}
    return 'voice-' + wallNow() + '-' + Math.random().toString(16).slice(2, 10);
  }
  function errorCode(error) {
    if (!error) return '';
    const raw = typeof error === 'string' ? error : (error.name || error.message || String(error));
    return String(raw).replace(/[?&#].*$/, '').replace(/\s+/g, '_').slice(0, 96);
  }
  function endpoint(value) {
    if (!value) return '';
    try {
      const parsed = new URL(String(value), global.location && global.location.href);
      return parsed.protocol + '//' + parsed.host + parsed.pathname.replace(/\/$/, '');
    } catch (error) {
      return String(value).split(/[?&#]/, 1)[0].slice(0, 160);
    }
  }
  function safeValue(key, value, depth) {
    if (SECRET_KEY.test(String(key || ''))) return undefined;
    if (value === null || typeof value === 'boolean' || typeof value === 'number') return value;
    if (typeof value === 'string') {
      if (/url|endpoint|host/i.test(String(key || ''))) return endpoint(value);
      return value.replace(/[?&#](key|token|secret|authorization)=[^\s&]*/ig, '').slice(0, 160);
    }
    if (depth >= 4) return undefined;
    if (Array.isArray(value)) return value.slice(0, 12).map((item, index) => safeValue(String(index), item, depth + 1)).filter(item => item !== undefined);
    if (value && typeof value === 'object') {
      const out = {};
      Object.keys(value).slice(0, 30).forEach(childKey => {
        const child = safeValue(childKey, value[childKey], depth + 1);
        if (child !== undefined) out[childKey] = child;
      });
      return out;
    }
    return undefined;
  }
  function safeDetails(details) { return safeValue('details', details || {}, 0) || {}; }
  function readHistory() {
    try {
      const value = JSON.parse(global.localStorage.getItem(STORAGE_KEY) || '[]');
      return Array.isArray(value) ? value.slice(-MAX_HISTORY) : [];
    } catch (error) { return []; }
  }
  function writeHistory(history) {
    try { global.localStorage.setItem(STORAGE_KEY, JSON.stringify(history.slice(-MAX_HISTORY))); } catch (error) {}
  }
  function persist(trace) {
    const history = readHistory().filter(item => item && item.callId !== trace.callId);
    history.push(trace);
    writeHistory(history);
  }
  function report(eventName, properties) {
    const payload = safeDetails(properties);
    try { global.console.info('[MuneaVoiceTrace]', JSON.stringify({ eventName, ...payload })); } catch (error) {}
    if (!reporter) {
      pendingReports.push({ eventName, properties: payload });
      if (pendingReports.length > 20) pendingReports.shift();
      return;
    }
    try {
      const result = reporter(eventName, payload);
      if (result && typeof result.catch === 'function') result.catch(() => {});
    } catch (error) {}
  }
  function publicSummary(trace) {
    const stages = (trace.stages || []).map(item => ({
      stage: item.stage,
      status: item.status,
      elapsedMs: item.elapsedMs,
      details: item.details,
    }));
    return {
      schemaVersion: 1,
      callId: trace.callId,
      outcome: trace.outcome || 'in_progress',
      reason: trace.reason || '',
      startedAt: trace.startedAt,
      endedAt: trace.endedAt || null,
      totalMs: trace.endedAt ? Math.max(0, trace.endedAt - trace.startedAt) : elapsedSince(trace.startedAt),
      lastSuccessfulStage: trace.lastSuccessfulStage || '',
      firstFailedStage: trace.firstFailedStage || '',
      context: trace.context || {},
      stages,
    };
  }
  function abandonPreviousTrace() {
    const history = readHistory();
    const previous = history[history.length - 1];
    if (!previous || previous.outcome !== 'in_progress') return;
    previous.outcome = 'abandoned';
    previous.reason = 'app_terminated_or_reloaded';
    previous.endedAt = wallNow();
    writeHistory(history);
    report('voice_call_diagnostic', publicSummary(previous));
  }
  function start(context) {
    if (active && active.outcome === 'in_progress') end('abandoned', { reason: 'new_call_started' });
    active = {
      schemaVersion: 1,
      callId: makeId(),
      outcome: 'in_progress',
      reason: '',
      startedAt: wallNow(),
      endedAt: null,
      lastSuccessfulStage: '',
      firstFailedStage: '',
      context: safeDetails(context),
      stages: [],
    };
    persist(active);
    mark('dial_tapped', 'pass', context);
    return active.callId;
  }
  function mark(stage, status, details) {
    if (!active || active.outcome !== 'in_progress') return null;
    const normalizedStatus = status === 'fail' || status === 'skip' ? status : 'pass';
    const item = {
      stage: String(stage || 'unknown').slice(0, 80),
      status: normalizedStatus,
      elapsedMs: elapsedSince(active.startedAt),
      details: safeDetails(details),
    };
    active.stages.push(item);
    if (active.stages.length > MAX_STAGES) active.stages.shift();
    if (normalizedStatus === 'pass') active.lastSuccessfulStage = item.stage;
    if (normalizedStatus === 'fail' && !active.firstFailedStage) active.firstFailedStage = item.stage;
    persist(active);
    const stagePayload = {
      callId: active.callId,
      stage: item.stage,
      status: item.status,
      elapsedMs: item.elapsedMs,
      lastSuccessfulStage: active.lastSuccessfulStage,
      firstFailedStage: active.firstFailedStage,
      ...item.details,
    };
    try { global.console.info('[MuneaVoiceStage]', JSON.stringify(stagePayload)); } catch (error) {}
    if (normalizedStatus === 'fail') report('voice_call_stage_failed', stagePayload);
    return item;
  }
  function fail(stage, error, details) {
    return mark(stage, 'fail', { errorCode: errorCode(error), ...(details || {}) });
  }
  function end(outcome, details) {
    if (!active || active.outcome !== 'in_progress') return active ? publicSummary(active) : null;
    const safe = safeDetails(details);
    const terminalOutcomes = new Set(['connected', 'completed', 'cancelled', 'abandoned', 'failed']);
    active.outcome = terminalOutcomes.has(outcome) ? outcome : 'failed';
    active.reason = String(safe.reason || outcome || '').slice(0, 96);
    active.endedAt = wallNow();
    persist(active);
    const summary = publicSummary(active);
    report('voice_call_diagnostic', summary);
    return summary;
  }
  function setReporter(nextReporter) {
    reporter = typeof nextReporter === 'function' ? nextReporter : null;
    if (!reporter) return;
    while (pendingReports.length) {
      const item = pendingReports.shift();
      report(item.eventName, item.properties);
    }
  }

  abandonPreviousTrace();
  global.MuneaVoiceDiagnostics = {
    start,
    mark,
    fail,
    end,
    setReporter,
    current: () => active ? publicSummary(active) : null,
    history: () => readHistory().map(publicSummary),
    endpoint,
  };
})(window);
