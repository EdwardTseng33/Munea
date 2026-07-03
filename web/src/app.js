/* Munea 沐寧 — 原型互動
 * 落實 Claude Design「沐寧 沐寧 配色」+ Elfie 融入（安心存摺 / 今天一起完成 / 家人互動）
 * 標 [ENGINE] 處正式版接 castle-voice-engine（中文〔台灣〕優先、英文第二 + 三顆腦 + 擬真 avatar；台語先不承諾）。 */

const $  = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

const OVERLAYS = ['med', 'connect'];
const AVATAR_ENGINE_MODES = Object.freeze({
  STATIC_CSS: 'static-css',
  TWO_D_VISEME: '2d-viseme',
  DITTO: 'ditto',
  LIVE_AVATAR: 'liveavatar',
});
const VOICE_PROVIDER_MODES = Object.freeze({
  STATIC_FALLBACK: 'static-fallback',
  STT_CHAT_TTS: 'stt-chat-tts',
  GEMINI_LIVE: 'gemini-live',
  INTERACTIONS: 'interactions',
});
const TWO_D_AVATARS = new Set(['munea-2d-xiaoyun', 'munea-2d-ayuan', 'munea-2d-mimi', 'munea-2d-wangcai']);

/* ===== [ENGINE] 角色模板 vs 使用者命名：模板決定外觀/聲音/人格，名字由使用者取 ===== */
const CompanionProfile = window.MuneaCompanionProfile;
const CHARACTER_TEMPLATES = CompanionProfile.templates;
let savedCompanionProfile = CompanionProfile.loadProfile();
let currentAvatarId = savedCompanionProfile.templateId;
let companionDisplayName = savedCompanionProfile.displayName;
let companionNameTouched = savedCompanionProfile.nameTouched;
let currentChar = CompanionProfile.templateFor(currentAvatarId).backendChar; // 後端角色模板，決定腦＋聲音
let chatHistory = [];            // 多輪對話脈絡
let chatOpened = false;          // 這次進聊聊她有沒有先開過口
let chatAudio = null;
let companionBackendSyncing = false;
let accountBootstrapSyncing = false;
let activeChatSessionId = null;
let activeChatStartedAt = 0;
let activeChatTurnCount = 0;
let latestAiContext = null;
let latestAiContextSource = 'not loaded';
let latestRelationshipState = null;
const ACCOUNT_BOOTSTRAP_KEY = 'munea.accountBootstrapped.v1';
const ONBOARDING_COMPLETED_KEY = 'munea.onboardingCompleted.v1';
const AI_PROVIDER_CONSENT_KEY = 'munea.aiProviderConsent.v1';
const AI_PROVIDER_CONSENT_VERSION = '2026-07-02-ai-provider-v1';

/* ===== AvatarRuntime：先把即時 avatar 的共用合約立起來 =====
 * mode=static-css 先用靜態圖 + CSS 呼吸/眨眼/聲波；之後 Ditto / LiveAvatar 只要接這層。 */
let speakTimer = null;
let visemeTimer = null;
let avatarSession = null;
const avatarRuntime = {
  modes: AVATAR_ENGINE_MODES,
  mode: AVATAR_ENGINE_MODES.STATIC_CSS,
  decision: null,
  state: 'idle',
  viseme: 'rest',
  character: currentChar,
  resolveMode(avatarId = currentAvatarId) {
    const forced = new URLSearchParams(location.search).get('avatar');
    if (forced === '2d') return AVATAR_ENGINE_MODES.TWO_D_VISEME;
    if (forced === 'static') return AVATAR_ENGINE_MODES.STATIC_CSS;
    if (Object.values(AVATAR_ENGINE_MODES).includes(forced)) return forced;
    return TWO_D_AVATARS.has(avatarId) ? AVATAR_ENGINE_MODES.TWO_D_VISEME : AVATAR_ENGINE_MODES.STATIC_CSS;
  },
  setMode(mode) {
    const valid = Object.values(AVATAR_ENGINE_MODES).includes(mode);
    this.mode = valid ? mode : AVATAR_ENGINE_MODES.STATIC_CSS;
    const sc = $('#chat');
    if (sc) sc.dataset.avatarMode = this.mode;
  },
  setDecision(decision) {
    this.decision = decision || null;
    if (this.decision && this.decision.selectedMode) this.setMode(this.decision.selectedMode);
  },
  setViseme(shape) {
    this.viseme = shape || 'rest';
    const sc = $('#chat');
    if (sc) sc.dataset.avatarViseme = this.viseme;
  },
  setState(st) {
    this.state = st;
    const sc = $('#chat');
    if (sc) {
      sc.dataset.state = st;
      sc.dataset.avatarMode = this.mode;
      sc.dataset.avatarViseme = this.viseme;
    }
    if (st !== 'speaking') this.stopMockViseme();
  },
  setCharacter(name, avatarId) {
    this.character = name;
    if (avatarId) currentAvatarId = avatarId;
    this.setMode(this.resolveMode(avatarId));
    this.setViseme('rest');
    const nm = $('#chatName'); if (nm) nm.textContent = name;
    const fimg = $('#faceImg');
    if (fimg && avatarId) {
      const template = templateFor(avatarId);
      fimg.src = template.fullAsset || ('avatars/' + avatarId + '.png');
      fimg.classList.toggle('sq', !template.fullAsset);
    }
  },
  startMockViseme(ms) {
    this.stopMockViseme();
    if (this.mode !== AVATAR_ENGINE_MODES.TWO_D_VISEME) return;
    const shapes = ['open', 'wide', 'round', 'smile', 'open', 'rest'];
    let i = 0;
    this.setViseme(shapes[i]);
    visemeTimer = setInterval(() => {
      i = (i + 1) % shapes.length;
      this.setViseme(shapes[i]);
    }, 120);
    setTimeout(() => this.stopMockViseme(), ms);
  },
  stopMockViseme() {
    clearInterval(visemeTimer);
    visemeTimer = null;
    this.setViseme('rest');
  },
  speak(text, audioMs = 0) {
    this.setState('speaking');
    clearTimeout(speakTimer);
    const ms = audioMs || Math.min(8000, Math.max(2200, (text ? text.length : 8) * 165));
    this.startMockViseme(ms);
    speakTimer = setTimeout(() => {
      if (this.state === 'speaking') {
        this.setState('idle');
        setCallHint('直接說，我在這裡');
      }
    }, ms);
    return ms;
  },
  onAudioEnd() {
    if (this.state === 'speaking') {
      this.setState('idle');
      setCallHint('直接說，我在這裡');
    }
  },
};
window.MuneaAvatarRuntime = avatarRuntime;

function setFaceState(st) { avatarRuntime.setState(st); }
function faceSpeak(text, audioMs = 0) {
  const ms = avatarRuntime.speak(text, audioMs);
  recordAvatarUsage(text, ms);
  return ms;
}
function setCallHint(text) {
  const cap = $('#chatCaption');
  if (cap) cap.textContent = text;
}
function templateFor(avatarId = currentAvatarId) {
  return CompanionProfile.templateFor(avatarId);
}
function persistCompanionProfile() {
  savedCompanionProfile = CompanionProfile.saveProfile({
    templateId: currentAvatarId,
    displayName: companionDisplayName.trim() || templateFor().defaultName,
    nameTouched: companionNameTouched,
  });
}
function isStaticPreview() {
  return location.port === '8135' || location.protocol === 'file:';
}
async function muneaAuthHeaders(base = {}) {
  const headers = { ...base };
  const auth = window.MuneaAuth;
  if (auth && typeof auth.getAccessToken === 'function') {
    const token = await auth.getAccessToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}
async function companionProfileApi(action, profile) {
  if (isStaticPreview()) return null;
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), 2500);
  try {
    const r = await fetch('/companion-profile', {
      method: 'POST',
      headers: await muneaAuthHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ action, profile }),
      signal: ctrl.signal,
    });
    if (!r.ok) return null;
    return await r.json();
  } catch (e) {
    return null;
  } finally {
    clearTimeout(to);
  }
}
function applyCompanionProfile(profile, options = {}) {
  const normalized = CompanionProfile.normalizeProfile(profile);
  currentAvatarId = normalized.templateId;
  companionDisplayName = normalized.displayName;
  companionNameTouched = normalized.nameTouched;
  currentChar = templateFor(currentAvatarId).backendChar;
  if (options.persist !== false) persistCompanionProfile();
  syncCompanionUI();
}
async function loadCompanionProfileFromBackend() {
  const r = await companionProfileApi('load');
  if (r && r.ok && r.profile) applyCompanionProfile(r.profile);
}
async function saveCompanionProfileToBackend() {
  if (companionBackendSyncing) return;
  companionBackendSyncing = true;
  try {
    await companionProfileApi('save', savedCompanionProfile);
  } finally {
    companionBackendSyncing = false;
  }
}
function storageGet(key) {
  try { return localStorage.getItem(key); } catch (e) { return null; }
}
function storageSet(key, value) {
  try { localStorage.setItem(key, value); } catch (e) {}
}
function readAiProviderConsent() {
  try {
    const raw = localStorage.getItem(AI_PROVIDER_CONSENT_KEY);
    if (!raw) return { agreed: false, version: AI_PROVIDER_CONSENT_VERSION };
    const parsed = JSON.parse(raw);
    return {
      agreed: parsed && parsed.agreed === true,
      version: parsed && parsed.version ? parsed.version : AI_PROVIDER_CONSENT_VERSION,
      agreedAt: parsed && parsed.agreedAt ? parsed.agreedAt : '',
      source: parsed && parsed.source ? parsed.source : 'unknown',
    };
  } catch (e) {
    return { agreed: false, version: AI_PROVIDER_CONSENT_VERSION };
  }
}
function saveAiProviderConsent(agreed, source = 'settings') {
  const payload = {
    agreed: agreed === true,
    version: AI_PROVIDER_CONSENT_VERSION,
    source,
    agreedAt: agreed === true ? new Date().toISOString() : '',
    updatedAt: new Date().toISOString(),
  };
  storageSet(AI_PROVIDER_CONSENT_KEY, JSON.stringify(payload));
  updateAiProviderConsentUI();
  trackProductEvent('ai_provider_consent_updated', {
    agreed: payload.agreed,
    source,
    consentVersion: AI_PROVIDER_CONSENT_VERSION,
  });
  return payload;
}
function updateAiProviderConsentUI() {
  const consent = readAiProviderConsent();
  window.MuneaAiProviderConsentState = consent;
}
function setupAiProviderConsentControls() {
  updateAiProviderConsentUI();
}
window.MuneaAiProviderConsent = {
  key: AI_PROVIDER_CONSENT_KEY,
  version: AI_PROVIDER_CONSENT_VERSION,
  read: readAiProviderConsent,
  save: saveAiProviderConsent,
};
function currentAuthUserId() {
  const auth = window.MuneaAuth || {};
  if (typeof auth.state === 'function') {
    const state = auth.state() || {};
    if (state.authUserId || state.userId) return state.authUserId || state.userId;
  }
  const user = auth.user || auth.currentUser || {};
  return auth.userId || auth.authUserId || user.id || user.userId || null;
}
function accountBootstrapPayload(action = 'create', extra = {}) {
  const authUserId = currentAuthUserId();
  const payload = {
    action,
    displayName: companionDisplayName.trim() || templateFor().defaultName,
    companionProfile: savedCompanionProfile,
    locale: 'zh-TW',
    timezone: 'Asia/Taipei',
    preferredLanguages: ['zh-TW', 'en'],
    source: 'web-prototype',
    ...extra,
  };
  if (authUserId) payload.authUserId = authUserId;
  return payload;
}
async function syncAccountBootstrap(action = 'create', extra = {}) {
  if (isStaticPreview() || accountBootstrapSyncing) return null;
  if (action !== 'preview' && storageGet(ACCOUNT_BOOTSTRAP_KEY) === 'true' && !extra.force) return null;
  accountBootstrapSyncing = true;
  try {
    const response = await brainPost('/account-bootstrap', accountBootstrapPayload(action, extra));
    if (response && response.ok) {
      storageSet(ACCOUNT_BOOTSTRAP_KEY, 'true');
      if (response.activeCompanionProfile) applyCompanionProfile(response.activeCompanionProfile);
      trackProductEvent('onboarding_completed', {
        bootstrapReason: extra.reason || action,
        bootstrapBackend: response.backend && response.backend.provider ? response.backend.provider : 'json',
      });
    } else if (response && response.error && response.error.code === 'auth_user_required') {
      storageSet(ACCOUNT_BOOTSTRAP_KEY, 'pending-auth');
    }
    return response;
  } finally {
    accountBootstrapSyncing = false;
  }
}
function syncCompanionUI() {
  const t = templateFor();
  const display = companionDisplayName.trim() || t.defaultName;
  const src = 'avatars/' + currentAvatarId + '.png';
  const thumbSrc = t.thumbAsset || src;
  const homeSrc = t.homeAsset || thumbSrc;
  const fullSrc = t.fullAsset || homeSrc;
  const homeName = $('#companionHomeName'); if (homeName) homeName.textContent = display;
  const chatName = $('#chatName'); if (chatName) chatName.textContent = display;
  const summary = $('#companionSummary'); if (summary) summary.textContent = `AI 健康照護 · 陪伴角色：${display}`;
  const settingName = $('#settingsCompanionName'); if (settingName) settingName.textContent = display;
  const settingLabel = $('#settingsTemplateLabel'); if (settingLabel) settingLabel.textContent = t.templateLabel;
  const settingImg = $('#settingsCompanionImg'); if (settingImg) settingImg.src = thumbSrc;
  const nameInput = $('#companionNameInput');
  if (nameInput && document.activeElement !== nameInput && nameInput.value !== display) nameInput.value = display;
  const fimg = $('#faceImg'); if (fimg) { fimg.src = fullSrc; fimg.classList.toggle('sq', !t.fullAsset); }
  $$('.bc-avatar img').forEach(i => { i.src = homeSrc; });
  $$('.cname').forEach(el => { el.textContent = display; });
  $$('#avatarPick .avo').forEach(o => o.classList.toggle('on', o.dataset.ava === currentAvatarId));
  avatarRuntime.setCharacter(display, currentAvatarId);
  renderAiDiagnostics();
}
function setCompanionName(name, opts) {
  companionDisplayName = (name || '').slice(0, 12);
  companionNameTouched = companionDisplayName.trim().length > 0;
  persistCompanionProfile();
  syncCompanionUI();
  if (!(opts && opts.skipBackend)) saveCompanionProfileToBackend();
}
function setCompanionTemplate(avatarId) {
  const templateId = CompanionProfile.normalizeTemplateId(avatarId);
  const t = templateFor(templateId);
  currentAvatarId = templateId;
  currentChar = t.backendChar;
  if (!companionNameTouched) companionDisplayName = t.defaultName;
  persistCompanionProfile();
  chatHistory = [];
  chatOpened = false;
  voiceProvider.close();
  syncCompanionUI();
  saveCompanionProfileToBackend();
  syncAccountBootstrap('create', { reason: 'companion_template_updated' });
  const cap = $('#chatCaption');
  if (cap) cap.textContent = '直接說，我在這裡';
}

function playB64(b64) {
  try {
    if (chatAudio) chatAudio.pause();
    chatAudio = new Audio('data:audio/wav;base64,' + b64);
    chatAudio.onended = () => avatarRuntime.onAudioEnd();
    chatAudio.play();
  } catch (e) {}
}
// 跟真腦講話；沒有伺服器（純靜態 demo）就回 null、讓畫面自己退回規則版
async function brainPost(url, body) {
  if (isStaticPreview()) return null;
  // 加超時護欄：語音腦連不上時，不卡死畫面（§6.5 降級鐵律：對話不斷、老實退回）
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), 6000);
  try {
    const r = await fetch(url, { method: 'POST', headers: await muneaAuthHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify(body), signal: ctrl.signal });
    if (!r.ok) return null;
    return await r.json();
  } catch (e) { return null; }
  finally { clearTimeout(to); }
}

/* ===== VoiceProvider：先立合約，之後可換 Gemini Live / Interactions，不綁死 App 核心 ===== */
function makeSessionId(prefix = 'session') {
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
}
function developerConfig() {
  return window.MUNEA_DEV_CONFIG || {};
}
function isLocalDevHost() {
  return ['localhost', '127.0.0.1', ''].includes(location.hostname) || location.protocol === 'file:';
}
function isDeveloperBypassAllowed() {
  const cfg = developerConfig();
  return cfg.enabled === true && (cfg.allowNonLocalhost === true || isLocalDevHost());
}
function applyDeveloperBypass() {
  const cfg = developerConfig();
  if (!isDeveloperBypassAllowed()) return;
  if (cfg.skipOnboarding === true) storageSet(ONBOARDING_COMPLETED_KEY, 'true');
}
function authAnalyticsContext() {
  const auth = window.MuneaAuth;
  const state = auth && typeof auth.state === 'function' ? auth.state() : {};
  const cfg = developerConfig();
  const devBypass = isDeveloperBypassAllowed();
  const excluded = !!(state.developerMode || (devBypass && (cfg.analyticsExcluded === true || cfg.excludeAnalytics === true)));
  return {
    authProvider: state.provider || 'guest',
    developerMode: !!state.developerMode,
    analyticsExcluded: excluded,
    accountType: excluded ? 'developer' : 'user',
  };
}
function isAiDevDiagnosticsEnabled() {
  const debug = new URLSearchParams(location.search).get('debug');
  const auth = window.MuneaAuth;
  const state = auth && typeof auth.state === 'function' ? auth.state() : {};
  const cfg = developerConfig();
  return debug === 'ai' || debug === 'all' || state.developerMode || (isDeveloperBypassAllowed() && cfg.showAiDiagnostics !== false);
}
function compactList(value) {
  if (!value) return '-';
  if (Array.isArray(value)) return value.length ? value.join(', ') : '-';
  return String(value || '-');
}
function renderAiDiagnostics() {
  const panel = $('#aiDevPanel');
  if (!panel) return;
  const enabled = isAiDevDiagnosticsEnabled();
  panel.hidden = !enabled;
  if (!enabled) return;
  const ctx = latestAiContext || {};
  const persona = ctx.personaLayer || {};
  const relationship = ctx.relationship || {};
  const guardian = ctx.guardian || {};
  const perception = ctx.perception || {};
  const memory = ctx.memory || {};
  const setText = (id, value) => { const el = $(id); if (el) el.textContent = value == null || value === '' ? '-' : String(value); };
  setText('#aiDevPersona', persona.templateId || currentAvatarId);
  setText('#aiDevRapport', relationship.rapportLevel || (latestRelationshipState && latestRelationshipState.rapportLevel) || 'new');
  setText('#aiDevGuardian', guardian.riskLevel || 'none');
  setText('#aiDevMemory', memory.count == null ? '-' : memory.count);
  setText('#aiDevSource', latestAiContextSource);
  setText('#aiDevPerception', compactList(perception.domains));
  setText('#aiDevTone', compactList(relationship.toneOverrideKeys || (latestRelationshipState && Object.keys(latestRelationshipState.toneOverrides || {}))));
  const json = $('#aiDevJson');
  if (json) {
    json.textContent = JSON.stringify({
      aiContext: latestAiContext,
      relationshipState: latestRelationshipState,
      voiceProvider: voiceProvider.mode,
      avatarMode: avatarRuntime.mode,
      analytics: authAnalyticsContext(),
    }, null, 2);
  }
}
function setLatestAiContext(context, source, relationshipState) {
  if (context) latestAiContext = context;
  if (relationshipState) latestRelationshipState = relationshipState;
  if (source) latestAiContextSource = source;
  renderAiDiagnostics();
}
async function refreshAiDiagnostics() {
  const panel = $('#aiDevPanel');
  if (!panel || panel.hidden) return null;
  const button = $('#aiDevRefresh');
  if (button) button.textContent = 'Loading';
  try {
    const response = await brainPost('/persona/context', {
      companionProfile: savedCompanionProfile,
      char: currentChar,
      text: 'developer diagnostics refresh',
      ...authAnalyticsContext(),
    });
    if (response) {
      latestRelationshipState = response.relationshipState || latestRelationshipState;
      setLatestAiContext({
        personaLayer: {
          templateId: response.templateId,
          displayName: response.displayName,
          personaArchetype: response.persona && response.persona.personaArchetype,
        },
        relationship: {
          rapportLevel: response.relationshipState && response.relationshipState.rapportLevel,
          hasRelationshipMemory: !!(response.relationshipState && response.relationshipState.relationshipMemory),
          toneOverrideKeys: Object.keys((response.relationshipState && response.relationshipState.toneOverrides) || {}),
        },
        guardian: {
          riskLevel: response.safety && response.safety.riskLevel,
          action: response.safety && response.safety.forceSafetyBoundary ? 'boundary' : 'allow',
        },
        perception: { domains: [], needsCurrentFacts: false },
        memory: { count: 0 },
      }, 'persona-context refresh', response.relationshipState);
    } else if (!latestAiContext) {
      setLatestAiContext(null, isStaticPreview() ? 'static preview' : 'refresh unavailable');
    }
    return response;
  } finally {
    if (button) button.textContent = 'Refresh';
  }
}
function analyticsContext(extra = {}) {
  return {
    templateId: currentAvatarId,
    avatarMode: avatarRuntime.mode,
    voiceProvider: voiceProvider.mode,
    voiceState: voiceProvider.state,
    companionTemplate: currentAvatarId,
    ...authAnalyticsContext(),
    ...extra,
  };
}
function trackProductEvent(eventName, properties = {}) {
  if (!eventName || isStaticPreview()) return Promise.resolve(null);
  const safeProperties = analyticsContext(properties);
  delete safeProperties.text;
  delete safeProperties.transcript;
  delete safeProperties.reply;
  return brainPost('/product-event', {
    eventName,
    sessionId: activeChatSessionId,
    source: 'web-prototype',
    properties: safeProperties,
  });
}
function postTurnReview() {
  if (isStaticPreview() || !chatHistory.length) return Promise.resolve(null);
  return brainPost('/butler/post-turn', {
    history: chatHistory.slice(-12),
    char: currentChar,
    companionProfile: savedCompanionProfile,
    sessionId: activeChatSessionId,
    ...authAnalyticsContext(),
  }).then(response => {
    if (response) setLatestAiContext(response.aiContext, 'butler post-turn', response.relationshipState);
    return response;
  });
}

function isAvatarDebug() {
  return new URLSearchParams(location.search).get('debug') === 'avatar';
}
function requestedAvatarMode() {
  return avatarRuntime.resolveMode(currentAvatarId);
}
function premiumAvatarMode(mode = avatarRuntime.mode) {
  return mode === AVATAR_ENGINE_MODES.DITTO || mode === AVATAR_ENGINE_MODES.LIVE_AVATAR;
}
function avatarSessionPayload(action = 'start', extra = {}) {
  const mode = extra.mode || requestedAvatarMode();
  return {
    action,
    mode,
    requestedMode: mode,
    templateId: currentAvatarId,
    char: currentChar,
    displayName: companionDisplayName.trim() || templateFor().defaultName,
    ...extra,
  };
}
function updateAvatarDiagnostics(response) {
  const el = $('#avatarDiagnostics');
  if (!el) return;
  if (!isAvatarDebug()) {
    el.hidden = true;
    return;
  }
  const session = response && response.session ? response.session : avatarSession;
  if (!session) {
    el.hidden = false;
    el.textContent = 'avatar: local preview';
    return;
  }
  const fallback = session.fallbackReason ? ` / ${session.fallbackReason}` : '';
  el.hidden = false;
  el.textContent = `avatar: ${session.selectedMode} via ${session.provider || 'local-browser'}${fallback}`;
}
function applyAvatarSessionDecision(response) {
  if (!response || !response.ok || !response.session) {
    updateAvatarDiagnostics(response);
    return null;
  }
  avatarSession = response.session;
  avatarRuntime.setDecision(avatarSession);
  const sc = $('#chat');
  if (sc) {
    sc.dataset.avatarProvider = avatarSession.provider || 'local-browser';
    sc.dataset.avatarFallbackReason = avatarSession.fallbackReason || '';
  }
  updateAvatarDiagnostics(response);
  return avatarSession;
}
async function avatarSessionApi(action = 'start', extra = {}) {
  if (isStaticPreview()) {
    updateAvatarDiagnostics(null);
    return null;
  }
  return brainPost('/avatar-session', avatarSessionPayload(action, extra));
}
async function prepareAvatarSession(extra = {}) {
  avatarRuntime.setMode(requestedAvatarMode());
  const response = await avatarSessionApi('start', extra);
  const session = applyAvatarSessionDecision(response);
  trackProductEvent('avatar_session_started', {
    requestedMode: requestedAvatarMode(),
    selectedMode: session ? session.selectedMode : avatarRuntime.mode,
    provider: session ? session.provider : 'local-browser',
    fallbackReason: session ? session.fallbackReason : '',
  });
  return response;
}
async function recordAvatarUsage(text, audioMs = 0) {
  if (!premiumAvatarMode()) return;
  const durationMs = audioMs || Math.min(8000, Math.max(2200, (text ? text.length : 8) * 165));
  const response = await avatarSessionApi('complete', {
    mode: avatarRuntime.mode,
    selectedMode: avatarRuntime.mode,
    durationMs,
    estimatedDurationMs: durationMs,
  });
  const session = applyAvatarSessionDecision(response);
  trackProductEvent('avatar_session_completed', {
    durationMs,
    selectedMode: session ? session.selectedMode : avatarRuntime.mode,
    usageCommitted: !!(session && session.usageCommitted),
  });
}

const voiceProvider = {
  modes: VOICE_PROVIDER_MODES,
  mode: VOICE_PROVIDER_MODES.STT_CHAT_TTS,
  state: 'idle',
  session: null,
  setState(st) {
    this.state = st;
    const sc = $('#chat');
    if (sc) sc.dataset.voiceState = st;
  },
  async connect(context = {}) {
    this.setState('connecting');
    const session = await brainPost('/voice-session', {
      char: currentChar,
      companionProfile: savedCompanionProfile,
      locale: 'zh-TW',
      fallback: VOICE_PROVIDER_MODES.STT_CHAT_TTS,
      ...context,
    });
    this.session = session || {
      ok: false,
      provider: VOICE_PROVIDER_MODES.STATIC_FALLBACK,
      fallback: VOICE_PROVIDER_MODES.STT_CHAT_TTS,
      locale: 'zh-TW',
    };
    this.mode = this.session.provider || this.session.fallback || VOICE_PROVIDER_MODES.STT_CHAT_TTS;
    setLatestAiContext(this.session.aiContext, 'voice-session', this.session.relationshipState);
    this.setState('idle');
    return this.session;
  },
  async open(char) {
    if (!this.session) await this.connect({ char });
    return brainPost('/open', { char });
  },
  async sendText({ history, char }) {
    this.setState('thinking');
    try {
      const response = await brainPost('/chat', { history, char, companionProfile: savedCompanionProfile });
      if (response) setLatestAiContext(response.aiContext, 'chat response', response.relationshipState);
      return response;
    } finally {
      this.setState('idle');
    }
  },
  async sendVoiceNote({ audio, mime, durationMs, char }) {
    this.setState('uploading');
    try {
      const response = await brainPost('/voice-note', { char, audio, mime, durationMs, provider: this.mode });
      if (response) setLatestAiContext(response.aiContext, 'voice-note', response.relationshipState);
      return response;
    } finally {
      this.setState('idle');
    }
  },
  close() {
    this.session = null;
    this.setState('idle');
  },
};
window.MuneaVoiceProvider = voiceProvider;
// 進聊聊頁：她像朋友一樣「主動先開口」（帶記憶＋今日狀態）
let callConnected = false;
function setCallToggle(connected) {
  callConnected = connected;
  const b = $('#callToggle');
  if (!b) return;
  b.classList.toggle('start', !connected);
  b.classList.toggle('end', connected);
  const pts = document.querySelector('.hud-pill.pts');
  if (pts) pts.style.display = connected ? 'none' : '';
  const lbl = $('#callToggleLabel');
  if (lbl) lbl.textContent = connected ? '結束通話' : '開始通話';
}

async function enterChat() {
  setCallToggle(false);
  const box = document.querySelector('.face-caption-box');
  if (box) box.style.display = 'none';
  setFaceState('idle');
}

async function openVoiceSession() {
  if (chatOpened) return;
  chatOpened = true;
  activeChatSessionId = makeSessionId('voice');
  activeChatStartedAt = Date.now();
  activeChatTurnCount = 0;
  setFaceState('idle');
  setCallHint('正在連線...');
  await prepareAvatarSession();
  trackProductEvent('voice_session_started', {
    locale: 'zh-TW',
    requestedAvatarMode: requestedAvatarMode(),
  });
  const r = await voiceProvider.open(currentChar);
  if (r && r.reply) {
    setCallHint('正在說話');
    chatHistory.push({ role: 'model', text: r.reply });
    if (r.audio) playB64(r.audio); else speakChat(r.reply);
    faceSpeak(r.reply);
  } else {
    const fallback = '我在這裡，今天過得好嗎？想聊什麼都可以。';
    setCallHint('直接說，我在這裡');
    faceSpeak(fallback);
  }
}

function completeChatSession(reason = 'ended') {
  if (_callSec > 3) {
    const mins = Math.max(1, Math.round(_callSec / 60));
    POINTS.used = Math.min(POINTS.total, POINTS.used + mins * 10);
    renderPoints();
  updateMedCount();
    toast('今天聊得真開心，下次見！');
  }
  stopCallTimer();
  if (!activeChatSessionId || !activeChatStartedAt) return;
  const durationMs = Math.max(0, Date.now() - activeChatStartedAt);
  trackProductEvent('voice_session_completed', {
    reason,
    durationMs,
    turnCount: activeChatTurnCount,
    meaningful: durationMs >= 60000 || activeChatTurnCount >= 3,
  });
  activeChatSessionId = null;
  activeChatStartedAt = 0;
  activeChatTurnCount = 0;
}

function showView(id) {
  const t = $('#toast'); if (t) t.classList.remove('show');
  $$('.modal-mask.show').forEach(m => m.classList.remove('show'));
  if (id === 'status') {
    const segBtns = document.querySelectorAll('#statusSeg .seg-btn');
    if (segBtns.length) {
      segBtns.forEach(x => x.classList.toggle('on', x.dataset.v === 'today'));
      const m = { today: $('#statusToday'), week: $('#statusWeek'), month: $('#statusMonth') };
      Object.entries(m).forEach(([k, el]) => { if (el) el.style.display = k === 'today' ? '' : 'none'; });
      if ($('#statusTitle')) $('#statusTitle').textContent = '今天的狀態';
    }
  }
  if (id === 'family') {
    const va = $('#viewAll');
    if (va && !va.classList.contains('active')) {
      $$('#family .fam-view').forEach(v => v.classList.remove('active'));
      va.classList.add('active');
    }
  }
  $$('.screen').forEach(s => s.classList.toggle('active', s.id === id));
  setTimeout(refreshHscrollHints, 60); // 分頁切換後重算「右邊還有」提示
  const overlay = OVERLAYS.includes(id);
  $('#tabBar').classList.toggle('hidden', overlay);
  $$('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.view === id));
  const el = $('#' + id); if (el) el.scrollTop = 0;
  if (id === 'chat') enterChat();
}

function authState() {
  const auth = window.MuneaAuth;
  return auth && typeof auth.state === 'function' ? auth.state() : { status: 'guest' };
}
function authProviderLabel(provider) {
  const key = String(provider || '').toLowerCase();
  if (key === 'apple') return 'Apple';
  if (key === 'google') return 'Google';
  if (key === 'email' || key === 'email_otp') return 'Email';
  if (key === 'dev-bypass') return 'Developer';
  return 'Munea';
}
function setAuthMessage(text = '', type = '') {
  const el = $('#authMessage');
  if (!el) return;
  el.textContent = text;
  el.classList.toggle('is-error', type === 'error');
  el.classList.toggle('is-ok', type === 'ok');
}
function openAuthSheet() {
  const sheet = $('#authSheet');
  if (!sheet) return;
  sheet.classList.add('show');
  sheet.setAttribute('aria-hidden', 'false');
  setAuthMessage('');
  const devBtn = $('#authDeveloperBtn');
  if (devBtn) devBtn.hidden = !isDeveloperBypassAllowed();
  const input = $('#authEmailInput');
  if (input) setTimeout(() => input.focus(), 180);
}
function closeAuthSheet() {
  const sheet = $('#authSheet');
  if (!sheet) return;
  sheet.classList.remove('show');
  sheet.setAttribute('aria-hidden', 'true');
}
function demoAuthOn() {
  try { return (localStorage.getItem('munea.demoAuth') || 'in') === 'in'; } catch (e) { return true; }
}
function updateAuthUI() {
  const state = authState();
  let signedIn = state.status === 'signed-in';
  // 示範機：未接雲端時，以「陳秀英 · 家庭成員」的已登入狀態展示（登出可切回訪客）
  if (!signedIn && demoAuthOn()) {
    const card0 = $('#authCard');
    if (card0) card0.dataset.authState = 'signed-in';
    if ($('#authStatusText')) $('#authStatusText').textContent = '陳秀英';
    if ($('#authProviderText')) $('#authProviderText').textContent = '我的帳號 · 資料已同步';
    if ($('#authEmailText')) $('#authEmailText').textContent = '';
    if ($('#authSignInBtn')) $('#authSignInBtn').hidden = true;
    if ($('#authSignOutBtn')) $('#authSignOutBtn').hidden = false;
    if ($('#authDevBadge')) $('#authDevBadge').hidden = true;
    if ($('#authAvatar')) $('#authAvatar').classList.remove('guest');
    renderAiDiagnostics();
    return;
  }
  if ($('#authAvatar')) $('#authAvatar').classList.toggle('guest', !signedIn);
  const card = $('#authCard');
  if (card) card.dataset.authState = signedIn ? 'signed-in' : 'guest';
  const status = $('#authStatusText');
  if (status) status.textContent = signedIn ? '已登入' : '訪客模式';
  const provider = $('#authProviderText');
  if (provider) {
    if (signedIn && state.developerMode) provider.textContent = '開發測試帳號，數據不列入營運統計';
    else if (signedIn) provider.textContent = `${authProviderLabel(state.provider)} 帳號同步中`;
    else provider.textContent = state.configured === false ? '登入尚未連到雲端設定' : '登入後同步家人、提醒與訂閱';
  }
  const email = $('#authEmailText');
  if (email) email.textContent = signedIn && state.email ? state.email : '';
  const signIn = $('#authSignInBtn');
  if (signIn) signIn.hidden = signedIn;
  const signOut = $('#authSignOutBtn');
  if (signOut) signOut.hidden = !signedIn;
  const devBadge = $('#authDevBadge');
  if (devBadge) devBadge.hidden = !(signedIn && state.developerMode);
  renderAiDiagnostics();
}
async function signInWithAuthProvider(provider) {
  if (isStaticPreview() || authState().configured === false) {
    try { localStorage.setItem('munea.demoAuth', 'in'); } catch (e) {}
    closeAuthSheet();
    updateAuthUI();
    toast('歡迎回來，陳秀英');
    return;
  }
  const auth = window.MuneaAuth;
  if (!auth) return setAuthMessage('登入模組尚未載入', 'error');
  setAuthMessage('正在前往登入...', 'ok');
  trackProductEvent('auth_sign_in_started', { provider });
  const method = provider === 'apple' ? auth.signInWithApple : auth.signInWithGoogle;
  const result = method ? await method() : { ok: false, error: { code: 'unsupported_provider' } };
  if (result && result.ok) return setAuthMessage('請在瀏覽器或系統視窗完成登入', 'ok');
  setAuthMessage(result && result.error && result.error.code === 'auth_not_configured' ? '尚未連接 Supabase 登入設定' : '登入暫時無法啟動', 'error');
}
async function signInWithEmailLink() {
  const input = $('#authEmailInput');
  const email = input ? input.value.trim() : '';
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return setAuthMessage('請輸入有效 email', 'error');
  const auth = window.MuneaAuth;
  if (!auth || typeof auth.signInWithEmail !== 'function') return setAuthMessage('Email 登入尚未啟用', 'error');
  setAuthMessage('正在寄送登入連結...', 'ok');
  trackProductEvent('auth_sign_in_started', { provider: 'email_otp' });
  const result = await auth.signInWithEmail(email);
  if (result && result.ok) return setAuthMessage('登入連結已寄出', 'ok');
  setAuthMessage(result && result.error && result.error.code === 'auth_not_configured' ? '尚未連接 Supabase 登入設定' : '登入連結暫時無法寄送', 'error');
}
async function signInDeveloperMode() {
  const auth = window.MuneaAuth;
  if (!auth || typeof auth.signInAsDeveloper !== 'function') return setAuthMessage('開發者模式尚未啟用', 'error');
  const result = await auth.signInAsDeveloper({ reason: 'settings_auth_sheet' });
  if (result && result.ok) {
    trackProductEvent('auth_developer_signed_in', { provider: 'dev-bypass' });
    updateAuthUI();
    closeAuthSheet();
    return;
  }
  setAuthMessage('此環境不可使用開發者模式', 'error');
}
async function signOutAuth() {
  const auth = window.MuneaAuth;
  if (!auth || typeof auth.signOut !== 'function') return;
  await auth.signOut();
  trackProductEvent('auth_signed_out', {});
  updateAuthUI();
}
function setupAuthControls() {
  if ($('#authSignInBtn')) $('#authSignInBtn').addEventListener('click', openAuthSheet);
  if ($('#authSignOutBtn')) $('#authSignOutBtn').addEventListener('click', async () => {
    const state = authState();
    if (state.status === 'signed-in') { await signOutAuth(); return; }
    try { localStorage.setItem('munea.demoAuth', 'out'); } catch (e) {}
    updateAuthUI();
    toast('已登出，資料還安全放著；再登入就接回來');
  });
  if ($('#authCloseBtn')) $('#authCloseBtn').addEventListener('click', closeAuthSheet);
  if ($('#authAppleBtn')) $('#authAppleBtn').addEventListener('click', () => signInWithAuthProvider('apple'));
  if ($('#authGoogleBtn')) $('#authGoogleBtn').addEventListener('click', () => signInWithAuthProvider('google'));
  if ($('#authEmailBtn')) $('#authEmailBtn').addEventListener('click', signInWithEmailLink);
  if ($('#authDeveloperBtn')) $('#authDeveloperBtn').addEventListener('click', signInDeveloperMode);
  const email = $('#authEmailInput');
  if (email) email.addEventListener('keydown', e => { if (e.key === 'Enter') signInWithEmailLink(); });
  const sheet = $('#authSheet');
  if (sheet) sheet.addEventListener('click', e => { if (e.target === sheet) closeAuthSheet(); });
  updateAuthUI();
}

(function homeGreeting() {
  const now = new Date();
  (function fixDemoEventDate() {
    const chip = document.getElementById('demoEventDate');
    if (!chip) return;
    const d = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    d.setDate(d.getDate() + (((6 - d.getDay() + 7) % 7) || 7));
    chip.textContent = (d.getMonth() + 1) + '/' + d.getDate() + '（週六）傍晚';
  })();
  const h = now.getHours();
  const dayN = Math.max(1, now.getDate() - 1);
  const ws = $('#wsText');
  if (ws) ws.innerHTML = `這個月你有 <b>${dayN} 天</b>準時吃藥，很穩，繼續保持。`;
  const chip = $('#bcChip');
  if (chip) {
    const sun = '<svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4 12H2M22 12h-2M6 6 4.5 4.5M19.5 19.5 18 18M6 18l-1.5 1.5M19.5 4.5 18 6"/></svg>';
    const moon = '<svg class="ic" viewBox="0 0 24 24"><path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/></svg>';
    let icon = sun, text = '<b>晴 26°</b>，下午去公園正好';
    if (h >= 18 || h < 5) { icon = moon; text = '睡前 10 分鐘，說說今天的事'; }
    else if (h >= 5 && h < 11) { text = '<b>晴 26°</b>，早上出門走走正好'; }
    else if (h >= 14) { text = '<b>晴 26°</b>，傍晚去公園正好'; }
    chip.innerHTML = icon + text;
  }
  const stat = $('#bcStatus');
  if (stat) stat.textContent = '記得你昨天說，孫子快要畢業了';
  const wd = ['日','一','二','三','四','五','六'][now.getDay()];
  const meta = $('#metaDate');
  if (meta) meta.textContent = `${now.getMonth() + 1}月${now.getDate()}日 週${wd}`;
  const kick = $('#greetKicker'), big = $('#greetBig');
  let k = '你好', b = '今天還好嗎？';
  if (h >= 5 && h < 11) { k = '早安'; b = '昨晚睡得還好嗎？'; }
  else if (h >= 11 && h < 14) { k = '午安'; b = '吃飽了嗎？'; }
  else if (h >= 14 && h < 18) { k = '午安'; b = '下午了，休息一下吧'; }
  else if (h >= 18 && h < 22) { k = '晚上好'; b = '今天過得怎麼樣？'; }
  else { k = '夜深了'; b = '早點休息，別撐太晚'; }
  if (kick) kick.textContent = k;
  if (big) big.textContent = b;
})();

function loadMeds() {
  try { return JSON.parse(localStorage.getItem('munea.meds')) || [
    { name: '脈優 Amlodipine', time: '午餐後', days: '長期', by: '美華' },
    { name: '維他命 D', time: '早餐後', days: '30 天', by: '阿嬤' }]; } catch (e) { return []; }
}
function updateMedCount() {
  const n = loadMeds().length + ' 種藥';
  const el = $('#medCountLabel');
  if (el) el.textContent = n;
  const el2 = $('#medCountSettings');
  if (el2) el2.textContent = n;
}
function renderMedList() {
  const box = $('#medList');
  if (!box) return;
  box.innerHTML = loadMeds().map(m =>
    '<div class="med-row"><div><b>' + m.name + '</b><span>' + m.time + ' · ' + m.days + '</span></div></div>').join('');
}

const POINTS = { total: 400, used: 160,
  get bought() { try { return +localStorage.getItem('munea.ptsBought') || 0; } catch (e) { return 0; } } };
function renderPoints() {
  const left = POINTS.total - POINTS.used + POINTS.bought;
  const hud = document.querySelector('.hud-pill.pts');
  if (hud) hud.textContent = '剩 ' + left + ' 點';
  if ($('#ptsLeft')) $('#ptsLeft').textContent = left;
  if ($('#ptsUsed')) $('#ptsUsed').textContent = POINTS.used;
  if ($('#ptsBar')) $('#ptsBar').style.width = Math.round(POINTS.used / POINTS.total * 100) + '%';
}

let _callTimerInt = null, _callSec = 0;
function startCallTimer() {
  stopCallTimer(); _callSec = 0;
  const el = $('#callTimer');
  _callTimerInt = setInterval(() => {
    _callSec++;
    const m = String(Math.floor(_callSec / 60)).padStart(2, '0');
    const s = String(_callSec % 60).padStart(2, '0');
    if (el) el.textContent = m + ':' + s;
  }, 1000);
}
function stopCallTimer() { if (_callTimerInt) { clearInterval(_callTimerInt); _callTimerInt = null; } const el = $('#callTimer'); if (el) el.textContent = '00:00'; }
function setCaption(text, hint) {
  let box = document.querySelector('.face-caption-box');
  if (!box) {
    box = document.createElement('div');
    box.className = 'face-caption-box';
    document.getElementById('chat')?.appendChild(box);
  }
  box.innerHTML = text + (hint ? '<small>' + hint + '</small>' : '');
}

let _toastTimer = null;
function syncPush(key, value) {
  try {
    fetch('/family/state', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'save', key, value }) }).catch(() => {});
  } catch (e) {}
}
async function syncPullAll() {
  try {
    const r = await fetch('/family/state', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'load' }) });
    if (!r.ok) return;
    const st = (await r.json()).state || {};
    const map = { activities: 'munea.activities', familyFeed: 'munea.familyFeed2', meds: 'munea.meds', visit: 'munea.visit', routine: 'munea.routine' };
    for (const k in map) {
      if (st[k] !== undefined && st[k] !== null) {
        try { localStorage.setItem(map[k], JSON.stringify(st[k])); } catch (e) {}
      }
    }
    if (typeof updateMedCount === 'function') updateMedCount();
    const peek = document.querySelector('.fam-peek .fp-text');
    const feed = st.familyFeed;
    if (peek && Array.isArray(feed) && feed.length) peek.innerHTML = feed[0];
  } catch (e) {}
}
function loadFeed() {
  try { const a = JSON.parse(localStorage.getItem('munea.familyFeed2')) || []; return Array.isArray(a) ? a : []; } catch (e) { return []; }
}
function pushFamilyFeed(text) {
  const a = loadFeed();
  a.unshift(text);
  while (a.length > 3) a.pop();
  try { localStorage.setItem('munea.familyFeed2', JSON.stringify(a)); } catch (e) {}
  syncPush('familyFeed', a);
  const peek = $('.fam-peek .fp-text');
  if (peek) peek.innerHTML = text;
}
function restoreFamilyFeed() {
  const a = loadFeed();
  if (a.length) { const peek = $('.fam-peek .fp-text'); if (peek) peek.innerHTML = a[0]; }
}

function toast(text) {
  const t = $('#toast');
  if (!t) return;
  t.textContent = text;
  t.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => t.classList.remove('show'), 2600);
}

// [ENGINE] 原型用瀏覽器內建語音；正式版換中文（台灣）/英文語音接點
function cname() {
  try { return (companionDisplayName || '寧寧').trim() || '寧寧'; } catch (e) { return '寧寧'; }
}
function hint(text) {
  // 聊聊以外不出聲（只出文字提示，禁止在此接語音）（2026-07-03 Edward 拍板）：只顯示提示
  toast(text);
}
function speakChat(text) {
  // 只給聊聊頁用：正式版是寧寧本人的聲音，這裡是開發用的代打
  toast(text);
  if (!('speechSynthesis' in window)) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = 'zh-TW'; u.rate = 0.92;
  const v = speechSynthesis.getVoices();
  const zh = v.find(x => /zh[-_]?TW/i.test(x.lang)) || v.find(x => /zh/i.test(x.lang));
  if (zh) u.voice = zh;
  speechSynthesis.speak(u);
}

// 今天一起完成：打勾 → 寧寧鼓勵（不是賺幣，是被看見）
const CHEERS = {
  pill: '藥吃了，你真棒，我幫你記到存摺裡，美華也看得到。',
  walk: '出去走走最好了，回來記得喝口水。',
  chat: '謝謝你跟我說這些，我都記下來了。',
};
function refreshTaskProgress() {
  const items = $$('#taskCard .task-item');
  const done = items.filter(i => i.classList.contains('done')).length;
  if (done === items.length && items.length && !window.__celebrated) {
    window.__celebrated = true;
    setTimeout(() => toast('今天三件都完成了，我跟家人說一聲'), 250);
    if (typeof pushFamilyFeed === 'function') pushFamilyFeed('<b>阿嬤</b>今天把三件事都完成了，給她一個讚');
  }
  const pillTask = document.querySelector('.task-item[data-task="pill"]');
  const pv = $('#statPillVal');
  if (pv && pillTask) pv.innerHTML = (pillTask.classList.contains('done') ? '3' : '2') + '<small>/3</small>';
  const prog = $('.task-progress');
  if (!prog) return;
  const label = prog.childNodes[prog.childNodes.length - 1];
  if (label) label.textContent = ` ${done} / ${items.length}`;
  const bar = prog.querySelector('.bar i');
  if (bar) bar.style.width = items.length ? `${Math.round(done / items.length * 100)}%` : '0%';
}

let _uncheckArm = null;
function toggleTask(item) {
  if (item.classList.contains('done')) {
    // 防手抖：取消「已完成」要按兩次（第一次只提示、3 秒內再按才真的取消）
    if (_uncheckArm === item) {
      _uncheckArm = null;
      item.classList.remove('done');
      refreshTaskProgress();
      toast('好，先取消這筆，等等再完成也可以。');
    } else {
      _uncheckArm = item;
      toast('這件已經完成了，再按一次才會取消。');
      setTimeout(() => { if (_uncheckArm === item) _uncheckArm = null; }, 3000);
    }
    return;
  }
  item.classList.add('done');
  refreshTaskProgress();
  hint(CHEERS[item.dataset.task] || '做得很好。');
}

// 心情圖譜 v2（六類）；之後接 /wellbeing/trend 真資料
const MOODS = {
  happy:  { label: '開心', bg: '#FBE7D2', fg: '#C25716', face: 'M9 10h.01M15 10h.01M8 14s1.5 2.5 4 2.5 4-2.5 4-2.5' },
  glad:   { label: '愉快', bg: '#F6ECD4', fg: '#9A6E14', face: 'M9 10h.01M15 10h.01M8.5 14.5s1.2 1.8 3.5 1.8 3.5-1.8 3.5-1.8' },
  calm:   { label: '平穩', bg: '#E8F2EE', fg: '#1E7169', face: 'M9 10h.01M15 10h.01M9 15h6' },
  tired:  { label: '疲累', bg: '#EEEFEA', fg: '#5F6A61', face: 'M9 10h.01M15 10h.01M9.5 15.5h5' },
  down:   { label: '低落', bg: '#E4EBF3', fg: '#3F5F80', face: 'M9 10h.01M15 10h.01M8.5 15.5s1.2-1.8 3.5-1.8 3.5 1.8 3.5 1.8' },
  upset:  { label: '煩躁', bg: '#ECE1F0', fg: '#6E4488', face: 'M8.5 9.5l2 1M15.5 9.5l-2 1M8.5 15.5s1.2-1.5 3.5-1.5 3.5 1.5 3.5 1.5' },
};
const MOOD_WEEK_DEMO = [
  { d: '五', mood: 'happy', chats: [{ m: 'happy', t: '聊到孫子回來，笑聲不斷' }] },
  { d: '六', mood: 'glad',  chats: [{ m: 'glad', t: '天氣好，去公園走了一圈回來心情不錯' }] },
  { d: '日', mood: 'calm',  chats: [{ m: 'calm', t: '平常的一天，聊了午餐吃什麼' }] },
  { d: '一', mood: 'down',  chats: [{ m: 'down', t: '翻到老伴的照片，聊著聊著有點想念' }] },
  { d: '二', mood: 'tired', chats: [{ m: 'tired', t: '昨晚沒睡好，講話比較沒力氣' }] },
  { d: '三', mood: 'glad',  chats: [{ m: 'glad', t: '韓劇大結局，聊得很起勁' }] },
  { d: '今天', mood: 'happy', mixed: true, chats: [
    { m: 'upset', t: '早上：推銷電話一直來，有點火氣，寧寧陪她抱怨了一會兒' },
    { m: 'happy', t: '傍晚：小寶來電話說畢業了，笑得合不攏嘴' } ] },
];
let MOOD_WEEK = MOOD_WEEK_DEMO;
const MOOD_ZH2KEY = { '開心': 'happy', '愉快': 'glad', '平穩': 'calm', '疲累': 'tired', '低落': 'down', '煩躁': 'upset' };
async function loadMoodWeekReal() {
  try {
    const r = await fetch('/wellbeing/trend', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ days: 7 }) });
    if (!r.ok) return null;
    const d = await r.json();
    const daily = d.daily || [];
    if (!daily.length) return null;
    const wd = ['日', '一', '二', '三', '四', '五', '六'];
    const now = new Date();
    const todayIso = now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0') + '-' + String(now.getDate()).padStart(2, '0');
    return daily.map(x => ({
      d: x.date === todayIso ? '今天' : wd[new Date(x.date + 'T00:00').getDay()],
      mood: MOOD_ZH2KEY[x.mood] || 'calm',
      mixed: !!x.mixed,
      chats: (x.signals || []).map(s => ({ m: MOOD_ZH2KEY[s.mood] || 'calm', t: s.oneLine || '' })).filter(c => c.t),
    })).filter(x => x.chats.length);
  } catch (e) { return null; }
}
function moodFaceSvg(key, size) {
  const m = MOODS[key] || MOODS.calm;
  return '<svg class="ic" viewBox="0 0 24 24" style="color:' + m.fg + ';width:' + size + 'px;height:' + size + 'px"><circle cx="12" cy="12" r="9"/><path d="' + m.face + '"/></svg>';
}
function renderMoodWeek() {
  const wrap = $('#moodWeek');
  if (!wrap) return;
  wrap.innerHTML = MOOD_WEEK.map((day, i) => {
    const m = MOODS[day.mood];
    const today = day.d === '今天';
    return '<button class="md' + (today ? ' today' : '') + '" data-i="' + i + '">' +
      '<span class="mcirc" style="background:' + m.bg + '">' + moodFaceSvg(day.mood, 22) +
      (day.mixed ? '<span class="mixdot"></span>' : '') + '</span>' +
      '<span class="mday">' + day.d + '</span></button>';
  }).join('');
  wrap.querySelectorAll('.md').forEach(b => b.addEventListener('click', () => showMoodDay(+b.dataset.i)));
  showMoodDay(MOOD_WEEK.length - 1);
  if (!window.__moodFetched) {
    window.__moodFetched = true;
    loadMoodWeekReal().then(real => {
      if (real && real.length >= 3) { MOOD_WEEK = real; renderMoodWeek(); }
    });
  }
}
function showMoodDay(i) {
  const day = MOOD_WEEK[i];
  const box = $('#moodDayDetail');
  if (!box || !day) return;
  box.innerHTML = '<div class="dd-date">' + (day.d === '今天' ? '今天' : '週' + day.d) + ' · 聊了 ' + day.chats.length + ' 次</div>' +
    day.chats.map(c => '<div class="dd-row">' + moodFaceSvg(c.m, 19) + '<span>' + c.t + '</span></div>').join('');
}
const MOOD_DAY_LINES = {
  happy: '那天聊得很開心，聲音都亮亮的',
  glad: '心情不錯，話匣子開著',
  calm: '平平穩穩的一天',
  tired: '有點累，講話比較小聲',
  down: '悶悶的，寧寧多陪了一會兒',
  upset: '有點火氣，抱怨完就好多了',
};
function renderMoodMonth() {
  const wrap = $('#moodMonth');
  if (!wrap || wrap.childElementCount) return;
  const seq = ['calm','glad','happy','calm','tired','glad','calm','down','calm','glad','happy','glad','calm','calm','tired','glad','calm','happy','glad','calm','down','tired','glad','calm','happy','glad','calm','happy'];
  const now = new Date();
  const daysInM = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
  const todayD = now.getDate();
  let html = '';
  for (let i = 0; i < daysInM; i++) {
    const day = i + 1;
    if (day > todayD) { html += '<span class="mm-cell future"></span>'; continue; }
    const k = seq[i % seq.length];
    html += '<button class="mm-cell" data-k="' + k + '" data-d="' + day + '" style="background:' + MOODS[k].bg + ';color:' + MOODS[k].fg + '">' + day + '</button>';
  }
  wrap.innerHTML = html + '<div class="mm-note">記到今天（' + (now.getMonth() + 1) + '/' + todayD + '）為止</div>';
  wrap.addEventListener('click', e => {
    const c = e.target.closest('.mm-cell');
    if (!c) return;
    wrap.querySelectorAll('.mm-cell').forEach(x => x.classList.remove('on'));
    c.classList.add('on');
    const box = $('#moodDayDetail');
    if (box) box.innerHTML = '<div class="dd-date">' + (now.getMonth() + 1) + '/' + c.dataset.d + ' · ' + MOODS[c.dataset.k].label + '</div>' +
      '<div class="dd-row">' + moodFaceSvg(c.dataset.k, 19) + '<span>' + (MOOD_DAY_LINES[c.dataset.k] || '') + '</span></div>';
    $('#moodDayDetail').style.display = '';
  });
}

const _hscrollUpdaters = [];
function refreshHscrollHints() { _hscrollUpdaters.forEach(u => u()); }
function setupHscrollHints() {
  $$('.hscroll-wrap').forEach(w => {
    const sc = w.querySelector('.fam-switch, .avatar-pick');
    if (!sc) return;
    const update = () => {
      if (!sc.clientWidth) return; // 分頁隱藏中不判定
      const atEnd = sc.scrollLeft + sc.clientWidth >= sc.scrollWidth - 8;
      w.classList.toggle('at-end', atEnd);
    };
    sc.addEventListener('scroll', update, { passive: true });
    _hscrollUpdaters.push(update);
    update();
  });
  window.addEventListener('resize', refreshHscrollHints);
}

function connectCall() {
  setCallToggle(true);
  startCallTimer();
  const capOff = $('#captionToggle') && $('#captionToggle').classList.contains('off');
  const box = document.querySelector('.face-caption-box');
  if (box) box.style.display = capOff ? 'none' : '';
  setCaption('接通了，直接說話就可以', '想到什麼就說，我在聽');
  openVoiceSession();
  setTimeout(() => { if (window.__muneaStartListen) window.__muneaStartListen(); }, 400);
}

function init() {
  syncPullAll();
  document.querySelectorAll('#taskCard svg').forEach(s2 => s2.setAttribute('aria-hidden', 'true'));
  document.querySelectorAll('#taskCard .task-check').forEach(s2 => s2.setAttribute('aria-label', '完成打勾'));
  if (location.hash === '#med') setTimeout(() => showView('med'), 300);
  syncCompanionUI();
  setupHscrollHints();
  renderPoints();
  updateMedCount();
  if ($('#callToggle')) $('#callToggle').addEventListener('click', () => {
    if (!callConnected) { connectCall(); }
    else { completeChatSession('user_ended'); chatOpened = false; setCallToggle(false); if (window.__muneaStopListen) window.__muneaStopListen(); }
  });
  if ($('#captionToggle')) $('#captionToggle').addEventListener('click', () => {
    const b = $('#captionToggle');
    const box = document.querySelector('.face-caption-box');
    const off = b.classList.toggle('off');
    if (box) box.style.display = off ? 'none' : '';
    toast(off ? '字幕已關閉' : '字幕已開啟');
  });
  refreshTaskProgress();
  restoreFamilyFeed();
  applyDeveloperBypass();
  setupAuthControls();
  setupAiProviderConsentControls();
  if (window.MuneaAuth && typeof window.MuneaAuth.init === 'function') {
    const authInit = window.MuneaAuth.init();
    if (authInit && typeof authInit.then === 'function') authInit.then(updateAuthUI).catch(updateAuthUI);
  }
  window.addEventListener('munea:auth-state', e => {
    const detail = e.detail || {};
    updateAuthUI();
    if (detail.status === 'signed-in') closeAuthSheet();
    if (detail.status === 'signed-in' && storageGet(ONBOARDING_COMPLETED_KEY) === 'true') {
      syncAccountBootstrap('create', { reason: 'auth_signed_in', force: true });
    }
  });
  loadCompanionProfileFromBackend().finally(() => {
    if (storageGet(ONBOARDING_COMPLETED_KEY) === 'true' || storageGet(ACCOUNT_BOOTSTRAP_KEY) === 'pending-auth') {
      syncAccountBootstrap('create', { reason: 'app_init' });
    }
  });
  avatarRuntime.setState('idle');
  $('#tabBar').addEventListener('click', e => { const b = e.target.closest('.tab-btn'); if (b) showView(b.dataset.view); });
  renderAiDiagnostics();
  if ($('#aiDevRefresh')) $('#aiDevRefresh').addEventListener('click', () => refreshAiDiagnostics());

  // 首頁「跟寧寧聊聊」＝ 進同一個全屏臉（不再有獨立視訊頁）
  if ($('#startCall')) $('#startCall').addEventListener('click', () => {
    showView('chat');
    setTimeout(() => { if (!callConnected) connectCall(); }, 350);
  });
  // 用藥服務窗（獨立功能、保留）
  if ($('#medTaken')) $('#medTaken').addEventListener('click', () => {
    trackProductEvent('routine_reminder_completed', { reminderType: 'medication' });
    hint('好，記下來了，連續六天，你真棒。');
    showView('home');
  });
  if ($('#medSnooze')) $('#medSnooze').addEventListener('click', () => showView('home'));

  // 連接裝置（狀態頁資料條 / 設定裝置區 → 串接三方裝置引導）
  if ($('#srcStrip')) $('#srcStrip').addEventListener('click', () => { window.__connectFrom = 'status'; showView('connect'); });
  if ($('#setDevices')) $('#setDevices').addEventListener('click', () => { window.__connectFrom = 'settings'; showView('connect'); });
  if ($('#companionRow')) $('#companionRow').addEventListener('click', () => $('#companionSheet').classList.add('show'));
  if ($('#companionCloseBtn')) $('#companionCloseBtn').addEventListener('click', () => $('#companionSheet').classList.remove('show'));
  if ($('#quizCloseX')) $('#quizCloseX').addEventListener('click', () => $('#quizModal').classList.remove('show'));
  if ($('#companionSheet')) $('#companionSheet').addEventListener('click', e => { if (e.target === $('#companionSheet')) $('#companionSheet').classList.remove('show'); });
  const RT_DEF = { b: '07:30', l: '12:00', d: '18:00', s: '22:00' };
  const RT_LABEL = { b: '早餐', l: '午餐', d: '晚餐', s: '就寢' };
  function loadRoutine() { try { return Object.assign({}, RT_DEF, JSON.parse(localStorage.getItem('munea.routine') || '{}')); } catch (e) { return Object.assign({}, RT_DEF); } }
  function saveRoutine(rt) { try { localStorage.setItem('munea.routine', JSON.stringify(rt)); } catch (e) {} syncPush('routine', rt); }
  function shiftTime(t, mins) {
    let [h, m] = t.split(':').map(Number);
    let total = (h * 60 + m + mins + 1440) % 1440;
    return String(Math.floor(total / 60)).padStart(2, '0') + ':' + String(total % 60).padStart(2, '0');
  }
  function renderRoutine() {
    const box = $('#rtList');
    if (!box) return;
    const rt = loadRoutine();
    box.innerHTML = ['b', 'l', 'd', 's'].map(k =>
      '<div class="rt-row"><span class="rt-name">' + RT_LABEL[k] + '</span>' +
      '<button class="rt-btn" data-k="' + k + '" data-m="-30">−</button>' +
      '<b class="rt-time">' + rt[k] + '</b>' +
      '<button class="rt-btn" data-k="' + k + '" data-m="30">＋</button></div>').join('');
  }
  if ($('#rtList')) $('#rtList').addEventListener('click', e => {
    const b = e.target.closest('.rt-btn');
    if (!b) return;
    const rt = loadRoutine();
    rt[b.dataset.k] = shiftTime(rt[b.dataset.k], +b.dataset.m);
    saveRoutine(rt);
    renderRoutine();
  });
  if ($('#profileRow')) $('#profileRow').addEventListener('click', () => { renderRoutine(); $('#profileModal').classList.add('show'); });
  if ($('#profileClose')) $('#profileClose').addEventListener('click', () => { $('#profileModal').classList.remove('show'); toast('作息記好了，提醒會照這份時間走'); });
  if ($('#profileModal')) $('#profileModal').addEventListener('click', e => { if (e.target === $('#profileModal')) $('#profileModal').classList.remove('show'); });
  // 家庭照護圈
  if ($('#famCircleRow')) $('#famCircleRow').addEventListener('click', () => $('#famCircleModal').classList.add('show'));
  if ($('#famCircleClose')) $('#famCircleClose').addEventListener('click', () => $('#famCircleModal').classList.remove('show'));
  if ($('#famCircleModal')) $('#famCircleModal').addEventListener('click', e => { if (e.target === $('#famCircleModal')) $('#famCircleModal').classList.remove('show'); });
  if ($('#fcInviteBtn')) $('#fcInviteBtn').addEventListener('click', () => { $('#famCircleModal').classList.remove('show'); toast('邀請連結準備好了，用訊息傳給家人就能加入'); });
  if ($('#connectBack')) $('#connectBack').addEventListener('click', () => showView(window.__connectFrom || 'status'));
  $$('#connect .cn-btn').forEach(b => b.addEventListener('click', () => {
    const on = b.classList.toggle('done');
    b.textContent = on ? '✓ 已連接' : (b.dataset.label || '連接');
    if (on) hint('好，連上了，之後健康資料我會自動留意。');
  }));

  // 今天一起完成（任務打勾）
  $('#taskCard').addEventListener('click', e => { const it = e.target.closest('.task-item'); if (it) toggleTask(it); });

  // 家人互動回應（親情循環）
  const reactRow = $('#reactRow');
  if (reactRow) reactRow.addEventListener('click', e => {
    const b = e.target.closest('.react-btn');
    if (!b || b.classList.contains('sent')) return;
    reactRow.querySelectorAll('.react-btn.sent').forEach(x => x.classList.remove('sent'));
    b.classList.add('sent');
    hint(`好，寧寧會幫你轉達，你${b.dataset.react}。`);
    const who = document.getElementById('ptName')?.textContent || '家人';
    pushFamilyFeed(`<b>你</b>剛剛給${who}${b.dataset.react || '送上心意'}，寧寧下次聊天會親口告訴${['阿嬤','美華'].includes(who) ? '她' : '他'}`);
  });

  // 全家健康圈：切換成員看健康
  const PERSON_STATS = {
    '阿嬤': [
      { ic: 'bp', val: '128/82', label: '早上 8:12 量 · 手環' },
      { ic: 'walk', val: '3,850<small> 步</small>', label: '今日活動' },
      { ic: 'sleep', val: '7.5<small> 小時</small>', label: '昨晚睡眠' },
      { ic: 'pill', val: '2<small>/3</small>', label: '今天用藥' }],
    '美華': [
      { ic: 'walk', val: '8,900<small> 步</small>', label: '今日活動' },
      { ic: 'sleep', val: '6.2<small> 小時</small>', label: '昨晚睡眠（偏少）' }],
    '志明': [
      { ic: 'walk', val: '7,400<small> 步</small>', label: '今日活動' },
      { ic: 'sleep', val: '7.1<small> 小時</small>', label: '昨晚睡眠' }],
    '小寶': [
      { ic: 'walk', val: '11,200<small> 步</small>', label: '今日活動' },
      { ic: 'sleep', val: '8.8<small> 小時</small>', label: '昨晚睡眠' }],
  };
  const STAT_ICONS = {
    bp: '<path d="M19 14c1.5-1.5 3-3.2 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.8 0-3 .5-4.5 2-1.5-1.5-2.7-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4 3 5.5l7 7Z"/><path d="M3.2 12H9l.5-1 2 4.5 2-7 1.5 3.5h5.3"/>',
    walk: '<path d="M4 16v-2.4c0-2.1-1-3.1-1-5.6 0-2.7 1.5-6 4.5-6C9.4 2 10 3.8 10 5.5c0 3.1-2 5.7-2 8.7V16a2 2 0 1 1-4 0Z"/><path d="M20 20v-2.4c0-2.1 1-3.1 1-5.6 0-2.7-1.5-6-4.5-6C14.6 6 14 7.8 14 9.5c0 3.1 2 5.7 2 8.7V20a2 2 0 1 0 4 0Z"/>',
    sleep: '<path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/>',
    pill: '<path d="M10.5 20.5 3.5 13.5a5 5 0 0 1 7-7l7 7a5 5 0 0 1-7 7z"/><path d="M8.5 8.5l7 7"/>',
  };
  function renderPersonStats(p) {
    const grid = $('#personGrid');
    if (!grid) return;
    const stats = PERSON_STATS[p] || PERSON_STATS['阿嬤'];
    grid.innerHTML = stats.map(t =>
      '<div class="stat-tile"><span class="st-ico"><svg class="ic" viewBox="0 0 24 24">' + STAT_ICONS[t.ic] + '</svg></span>' +
      '<div class="st-val">' + t.val + '</div><div class="st-label">' + t.label + '</div></div>').join('');
  }

  const FAM_ORDER = ['阿嬤', '美華', '志明', '小寶'];
  let currentPerson = '阿嬤';
  const FAM_ACT = { '阿嬤': 48, '美華': 74, '志明': 62, '小寶': 93 };
  (function famRings() {
    document.querySelectorAll('.fam-switch-item').forEach(it => {
      const name = it.dataset.person;
      const av = it.querySelector('.init-ava');
      if (!name || !av || !(name in FAM_ACT) || av.closest('.fam-ring')) return;
      const ring = document.createElement('span');
      ring.className = 'fam-ring';
      ring.style.setProperty('--p', FAM_ACT[name]);
      av.parentNode.insertBefore(ring, av);
      ring.appendChild(av);
      it.title = name + ' 今天活動量約 ' + FAM_ACT[name] + '%';
    });
  })();
  function famItemOf(name) {
    return [...document.querySelectorAll('.fam-switch-item')].find(x => x.dataset.person === name);
  }
  function renderFamDots() {
    const box = $('#famDots');
    if (!box) return;
    box.innerHTML = FAM_ORDER.map(n => '<i class="' + (n === currentPerson ? 'on' : '') + '"></i>').join('');
  }
  function switchPerson(delta) {
    const idx = FAM_ORDER.indexOf(currentPerson);
    const next = FAM_ORDER[idx + delta];
    if (!next) return; // 到邊了
    const b = famItemOf(next);
    if (!b) return;
    const v = $('#viewPerson');
    if (v) { v.classList.remove('slide-l', 'slide-r'); void v.offsetWidth; v.classList.add(delta > 0 ? 'slide-l' : 'slide-r'); }
    showFamPerson(next, b.dataset.rel, b.dataset.init, b.dataset.tint);
    b.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
  }

  function showFamPerson(p, rel, init, tint) {
    currentPerson = p;
    renderFamDots();
    $('#viewAll').classList.remove('active');
    $('#viewPerson').classList.add('active');
    if ($('#ptName')) $('#ptName').textContent = p;
    if ($('#personNavTitle')) $('#personNavTitle').textContent = p;
    renderPersonStats(p);
    if ($('#moodToday')) $('#moodToday').style.display = (p === '阿嬤') ? '' : 'none';
    if ($('#ptRel')) $('#ptRel').textContent = rel || '';
    const pa = $('#ptAv');
    if (pa) { pa.textContent = init || (p || '')[0] || ''; pa.className = 'init-ava init-ava-lg ' + (tint || ''); }
    $$('.fam-switch-item').forEach(b => b.classList.toggle('active', b.dataset.person === p));
    const v = $('#viewPerson'); if (v) v.scrollIntoView({ block: 'start' });
  }
  function showFamAll() {
    $('#viewPerson').classList.remove('active');
    $('#viewAll').classList.add('active');
    $$('.fam-switch-item').forEach(b => b.classList.toggle('active', b.dataset.person === 'all'));
  }
  const vp = $('#viewPerson');
  if (vp) {
    let sx = 0, sy = 0, tracking = false;
    vp.addEventListener('touchstart', e => { sx = e.touches[0].clientX; sy = e.touches[0].clientY; tracking = true; }, { passive: true });
    vp.addEventListener('touchend', e => {
      if (!tracking) return; tracking = false;
      const dx = e.changedTouches[0].clientX - sx, dy = e.changedTouches[0].clientY - sy;
      if (Math.abs(dx) > 56 && Math.abs(dx) > Math.abs(dy) * 2) switchPerson(dx < 0 ? 1 : -1);
    }, { passive: true });
    let mx = null;
    vp.addEventListener('mousedown', e => { mx = e.clientX; });
    vp.addEventListener('mouseup', e => {
      if (mx === null) return;
      const dx = e.clientX - mx; mx = null;
      if (Math.abs(dx) > 56) switchPerson(dx < 0 ? 1 : -1);
    });
  }
  if ($('#personBack')) $('#personBack').addEventListener('click', showFamAll);
  if ($('#moodTrendBtn')) $('#moodTrendBtn').addEventListener('click', () => {
    $('#viewPerson').classList.remove('active');
    $('#viewMood').classList.add('active');
    const n = $('#ptName') ? $('#ptName').textContent : '阿嬤';
    if ($('#moodTitle')) $('#moodTitle').textContent = n + '的心情';
    renderMoodWeek();
    const lg = $('#moodLegend');
    if (lg && !lg.childElementCount) lg.innerHTML = Object.keys(MOODS).map(k =>
      '<span><i style="background:' + MOODS[k].bg + '">' + moodFaceSvg(k, 14) + '</i>' + MOODS[k].label + '</span>').join('');
  });
  if ($('#moodBack')) $('#moodBack').addEventListener('click', () => {
    $('#viewMood').classList.remove('active');
    $('#viewPerson').classList.add('active');
  });
  if ($('#moodRange')) $('#moodRange').addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    $('#moodRange').querySelectorAll('button').forEach(x => x.classList.toggle('active', x === b));
    const month = b.dataset.r === 'month';
    $('#moodWeek').style.display = month ? 'none' : '';
    if (!month) $('#moodDayDetail').style.display = '';
    $('#moodMonth').style.display = month ? '' : 'none';
    if (month) renderMoodMonth();
  });
  const setReminders = $('#medEntrySettings');
  if (setReminders) setReminders.addEventListener('click', () => {
    const mask = $('#medMgrModal');
    if (mask) { renderMedList(); mask.classList.add('show'); }
  });
  if ($('#medMgrClose')) $('#medMgrClose').addEventListener('click', () => $('#medMgrModal').classList.remove('show'));
  if ($('#medMgrModal')) $('#medMgrModal').addEventListener('click', e => { if (e.target === $('#medMgrModal')) $('#medMgrModal').classList.remove('show'); });
  const chipToggle = (boxId, single) => {
    const box = $(boxId);
    if (!box) return;
    box.addEventListener('click', e => {
      const b = e.target.closest('.mchip');
      if (!b) return;
      if (single) box.querySelectorAll('.mchip').forEach(x => x.classList.remove('on'));
      b.classList.toggle('on');
    });
  };
  chipToggle('#medTimeChips', false);
  chipToggle('#medDayChips', true);
  if ($('#medAddBtn')) $('#medAddBtn').addEventListener('click', () => {
    const name = $('#medName').value.trim();
    const times = [...document.querySelectorAll('#medTimeChips .mchip.on')].map(b => b.dataset.t);
    const days = document.querySelector('#medDayChips .mchip.on')?.dataset.d || '長期';
    if (!name) { toast('先寫藥名（照藥袋抄就好）'); return; }
    if (!times.length) { toast('點一下什麼時候吃（可以選好幾個）'); return; }
    const meds = loadMeds();
    meds.push({ name, time: times.join('、'), days, by: '美華' });
    try { localStorage.setItem('munea.meds', JSON.stringify(meds)); syncPush('meds', meds); } catch (e) {}
    $('#medName').value = '';
    document.querySelectorAll('#medTimeChips .mchip.on').forEach(x => x.classList.remove('on'));
    renderMedList();
    updateMedCount();
    toast('好，' + cname() + '會在' + times.join('、') + '提醒吃「' + name + '」，時間照你的作息');
  });
  if ($('#medEntryStatus')) $('#medEntryStatus').addEventListener('click', () => { renderMedList(); $('#medMgrModal').classList.add('show'); });
  if ($('#medBackBtn')) $('#medBackBtn').addEventListener('click', () => showView('settings'));
  if ($('#topUpBtn')) $('#topUpBtn').addEventListener('click', () => $('#topUpModal').classList.add('show'));
  if ($('#topUpClose')) $('#topUpClose').addEventListener('click', () => $('#topUpModal').classList.remove('show'));
  if ($('#topUpModal')) $('#topUpModal').addEventListener('click', e => {
    if (e.target === $('#topUpModal')) { $('#topUpModal').classList.remove('show'); return; }
    const card = e.target.closest('.tu-card');
    if (card) { document.querySelectorAll('.tu-card').forEach(x => x.classList.remove('on')); card.classList.add('on'); }
  });
  if ($('#tuBuyBtn')) $('#tuBuyBtn').addEventListener('click', () => {
    const selCard = document.querySelector('.tu-card.on');
    const p = selCard ? +selCard.dataset.p : 0;
    try { localStorage.setItem('munea.ptsBought', String((POINTS.bought || 0) + p)); } catch (e2) {}
    renderPoints();
    $('#topUpModal').classList.remove('show');
    toast('買好了，' + p.toLocaleString() + ' 點入帳（餘額已更新），這批不會過期');
  });
  const tierList = document.querySelector('.tier-list');
  function renderPlanNext() {
    const nx = localStorage.getItem('munea.planNext');
    document.querySelectorAll('.tier .tier-tag.next').forEach(x => x.remove());
    const meta = document.querySelector('.pc-meta');
    if (meta) meta.textContent = '我的訂閱 · 下次扣款 7/26 · 你和阿公兩位使用中' + (nx ? '（' + nx + ' 7/26 起）' : '');
    if (nx && tierList) {
      const t = [...tierList.querySelectorAll('.tier')].find(x => x.dataset.t === nx);
      if (t) {
        const em = document.createElement('em');
        em.className = 'tier-tag next';
        em.textContent = '7/26 起';
        t.querySelector('span').appendChild(em);
      }
    }
  }
  if (tierList) tierList.addEventListener('click', e => {
    const t = e.target.closest('.tier');
    if (!t || t.classList.contains('on')) return;
    try { localStorage.setItem('munea.planNext', t.dataset.t); } catch (e2) {}
    renderPlanNext();
    toast('排好了：7/26 起改「' + t.dataset.t + '」，這期權益照用');
  });
  renderPlanNext();
  if ($('#planCancelBtn')) $('#planCancelBtn').addEventListener('click', () => {
    $('#planModal').classList.remove('show');
    toast('會在 7/25 到期後停止扣款、轉為免費試用；資料和記憶都會留著');
  });
  if ($('#managePlanBtn')) $('#managePlanBtn').addEventListener('click', () => $('#planModal').classList.add('show'));
  if ($('#planClose')) $('#planClose').addEventListener('click', () => $('#planModal').classList.remove('show'));
  if ($('#planModal')) $('#planModal').addEventListener('click', e => { if (e.target === $('#planModal')) $('#planModal').classList.remove('show'); });
  const famSwitch = $('#famSwitch');
  if (famSwitch) famSwitch.addEventListener('click', e => {
    const b = e.target.closest('.fam-switch-item'); if (!b) return;
    const p = b.dataset.person;
    if (p === 'all') showFamAll();
    else if (p === 'invite') hint('好，我幫你發邀請給家人，加進來就能互相關心健康。');
    else showFamPerson(p, b.dataset.rel, b.dataset.init, b.dataset.tint);
  });
  const healthList = $('#healthList');
  if (healthList) healthList.addEventListener('click', e => {
    const r = e.target.closest('.health-row'); if (!r) return;
    showFamPerson(r.dataset.person, r.dataset.rel, r.dataset.init, r.dataset.tint);
  });
  // 週/月趨勢切換
  const TREND = {
    week: {
      bars: [
        { l: '一', h: 55, s: 'soso' }, { l: '二', h: 72, s: 'ok' }, { l: '三', h: 45, s: 'soso' },
        { l: '四', h: 80, s: 'ok' }, { l: '五', h: 62, s: 'today' }, { l: '六', h: 0, s: 'future' }, { l: '日', h: 0, s: 'future' }],
      note: '這週到目前 <b>2 天達標</b>；今天已經走 6,200 步，再走一小段就達標了。'
    },
    month: {
      bars: [
        { l: '第 1 週', h: 64, s: 'ok' }, { l: '第 2 週', h: 78, s: 'ok' }, { l: '第 3 週', h: 42, s: 'soso' }, { l: '第 4 週', h: 70, s: 'today' }],
      note: '這個月 <b>2 週達標</b>；第 3 週在感冒、少動很正常，這週正在補回來。'
    }
  };
  function renderTrend(range) {
    const box = $('#trendBars');
    if (!box) return;
    const d = TREND[range] || TREND.week;
    box.innerHTML = d.bars.map(b2 => '<div class="tb ' + b2.s + '"><i style="height:' + Math.max(b2.h, 6) + '%"></i><span>' + b2.l + '</span></div>').join('');
    if ($('#trendNote')) $('#trendNote').innerHTML = d.note;
  }
  renderTrend('week');
  const trendTabs = $('#trendTabs');
  if (trendTabs) trendTabs.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    trendTabs.querySelectorAll('button').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    renderTrend(b.dataset.range);
  });

  // 一鍵回診摘要
  const rep = $('#reportBtn');
  if (rep) rep.addEventListener('click', () => $('#reportModal').classList.add('show'));
  if ($('#reportClose')) $('#reportClose').addEventListener('click', () => $('#reportModal').classList.remove('show'));
  if ($('#reportModal')) $('#reportModal').addEventListener('click', e => { if (e.target === $('#reportModal')) $('#reportModal').classList.remove('show'); });
  if ($('#rptSendBtn')) $('#rptSendBtn').addEventListener('click', () => {
    $('#reportModal').classList.remove('show');
    toast('傳給美華了，回診那天她手機一打開就有');
    pushFamilyFeed('<b>阿嬤</b>把 6 月的回診摘要傳給了美華');
  });

  // 發起挑戰面板
  const chalModal = $('#chalModal');
  const closeChal = () => chalModal && chalModal.classList.remove('show');
  if ($('#newChalBtn')) $('#newChalBtn').addEventListener('click', () => {
    if (!chalModal) return;
    const cur = document.querySelector('.chal-type.active');
    applyChalKind(cur ? (cur.dataset.kind || 'walk') : 'walk');
    chalModal.classList.add('show');
  });
  const WD = ['週日', '週一', '週二', '週三', '週四', '週五', '週六'];
  function fmtDay(d) { return (d.getMonth() + 1) + '/' + d.getDate() + '（' + WD[d.getDay()] + '）'; }
  function resolveEvDate() {
    const on = document.querySelector('#evDayChips .mchip.on');
    const now = new Date();
    const d = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const k = on ? on.dataset.day : 'sat';
    if (k === 'tomorrow') d.setDate(d.getDate() + 1);
    else if (k === 'sat') d.setDate(d.getDate() + (((6 - d.getDay() + 7) % 7) || 7));
    else if (k === 'sun') d.setDate(d.getDate() + (((0 - d.getDay() + 7) % 7) || 7));
    else if (k === 'pick') {
      const on = document.querySelector('#evDatePick .cal-cell.on');
      if (on) { const pd = new Date(on.dataset.iso + 'T00:00'); if (!isNaN(pd)) return pd; }
    }
    return d;
  }
  function isoOf(d) { return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }
  function buildCalGrid(boxSel) {
    const box = $(boxSel || '#evDatePick');
    if (!box || box.dataset.built) return;
    box.dataset.built = '1';
    const now = new Date();
    let html = '';
    for (let i = 0; i < 14; i++) {
      const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + i);
      const wdName = i === 0 ? '今天' : (i === 1 ? '明天' : '週' + '日一二三四五六'[d.getDay()]);
      html += '<button type="button" class="cal-cell" data-iso="' + isoOf(d) + '"><small>' + wdName + '</small><b>' + (d.getDate() === 1 ? (d.getMonth() + 1) + '/1' : d.getDate()) + '</b></button>';
    }
    box.innerHTML = html;
    box.addEventListener('click', e => {
      const cell = e.target.closest('.cal-cell');
      if (!cell) return;
      box.querySelectorAll('.cal-cell').forEach(x => x.classList.remove('on'));
      cell.classList.add('on');
    });
  }
  function loadActs() { try { return JSON.parse(localStorage.getItem('munea.activities')) || []; } catch (e) { return []; } }
  function saveActs(a) { try { localStorage.setItem('munea.activities', JSON.stringify(a)); } catch (e) {} syncPush('activities', a); }
  function renderActCard(act) {
    const list = document.querySelector('#newChalBtn')?.closest('.pad')?.querySelector('.quest-card');
    if (!list) return;
    const card = document.createElement('div');
    card.className = 'quest-card pending';
    let chip, goal, note;
    if (act.status === 'done') {
      chip = '已結束';
      goal = act.kind === 'quiz' ? ('你答對 ' + act.score + ' / ' + (act.q || 5) + ' 題') : (act.title + ' 結束了');
      note = '等大家都看過就收進記錄簿 · 最多留 3 天，還沒看的，寧寧會親口告訴';
    } else if (act.kind === 'walk') {
      chip = act.days + ' 天內';
      goal = '大家一起走 ' + (+act.goal).toLocaleString() + ' 步';
      note = cname() + '會親口問阿嬤要不要一起；開始後每個人走多少都看得到';
    } else if (act.kind === 'quiz') {
      chip = act.q + ' 題';
      goal = '你的 ' + act.q + ' 題準備好了';
      note = '點這張卡先作答；' + cname() + '會找其他人玩，都答完看排名';
    } else {
      chip = act.dateLabel;
      goal = act.title + '，誰能到？';
      note = cname() + '會親口問阿嬤、幫大家收「去 / 沒空」；過了那天卡片會自動收進記錄簿';
    }
    const rwLine = act.rewards && act.rewards.some(Boolean)
      ? '<div class="qc-note">🏅 獎勵：' + act.rewards.map((r, i2) => r ? '第 ' + (i2 + 1) + ' 名 ' + r : '').filter(Boolean).join('、') + '</div>'
      : '';
    card.innerHTML = '<div class="qc-kicker"><svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg>' +
      (act.kind === 'event' ? '揪一攤 · ' + act.title : '邀請已送出 · ' + act.title) +
      '<span class="qc-days">' + chip + '</span></div>' +
      '<div class="qc-goal">' + goal + '</div>' +
      '<div class="qc-num">' + note + '</div>' + rwLine;
    if (act.kind === 'quiz' && act.status !== 'done') { card.style.cursor = 'pointer'; card.addEventListener('click', () => startQuiz(act, card)); }
    list.parentNode.insertBefore(card, list);
  }
  if ($('#startChalBtn')) $('#startChalBtn').addEventListener('click', () => {
    const type = document.querySelector('.chal-type.active');
    const kind = type ? (type.dataset.kind || 'walk') : 'walk';
    const ons = $$('#inviteList .iv.on');
    const names = ons.map(x => x.dataset.name).filter(Boolean);
    if (!names.length) { toast('先選至少一位家人一起'); return; }
    const act = { id: Date.now(), kind, names };
    if (kind === 'walk') {
      act.goal = +(($('#walkGoal') && $('#walkGoal').value) || 30000);
      act.days = +(($('#walkDays') && $('#walkDays').value) || 7);
      act.title = '一起運動';
      const end = new Date(); end.setDate(end.getDate() + act.days);
      act.dateISO = isoOf(end);
    } else if (kind === 'quiz') {
      act.q = +(($('#quizN') && $('#quizN').value) || 10);
      act.title = '機智問答';
    } else {
      const d = resolveEvDate();
      act.dateISO = isoOf(d);
      act.dateLabel = fmtDay(d) + ((document.querySelector('#evTimeChips .mchip.on') || { dataset: {} }).dataset.t || '');
      act.title = (($('#eventName') && $('#eventName').value.trim()) || '家庭聚會');
    }
    const rw = ['#rw1', '#rw2', '#rw3'].map(x => ($(x) && $(x).value.trim()) || '');
    if (rw.some(Boolean)) act.rewards = rw;
    ['#rw1', '#rw2', '#rw3'].forEach(x => { if ($(x)) $(x).value = ''; });
    const acts = loadActs(); acts.push(act); saveActs(acts);
    closeChal();
    renderActCard(act);
    hint(kind === 'event' ? '好，' + cname() + '幫你問大家，誰能到、誰沒空，回覆齊了告訴你。' : '好，邀請發出去了，' + cname() + '會親口問阿嬤，等大家答應就開始。');
  });
  // 到期自動收卡：過了活動日就從牆上收走、記到家庭動態
  (function restoreActs() {
    const today = isoOf(new Date());
    const acts = loadActs();
    const keep = [];
    const d3 = new Date(); d3.setDate(d3.getDate() - 3);
    const cutoff = isoOf(d3);
    acts.forEach(a => {
      if (a.status === 'done' && a.doneISO && a.doneISO <= cutoff) {
        pushFamilyFeed('「' + a.title + '」的結果收進<b>家庭記錄簿</b>了');
      } else if (a.status !== 'done' && a.kind !== 'quiz' && a.dateISO && a.dateISO < today) {
        pushFamilyFeed('「' + a.title + '」結束了，那天的紀錄收進<b>家庭記錄簿</b>了');
      } else { keep.push(a); renderActCard(a); }
    });
    if (keep.length !== acts.length) saveActs(keep);
  })();
  if (chalModal) chalModal.addEventListener('click', e => { if (e.target === chalModal) closeChal(); });
  // 邀請勾選 → 依人數+能力動態算目標
  const inviteList = $('#inviteList');
  function updateWalkLabels() {
    const g = +($('#walkGoal') ? $('#walkGoal').value : 30000);
    if ($('#walkGoalVal')) $('#walkGoalVal').textContent = g.toLocaleString() + ' 步';
    const n = $$('#inviteList .iv.on').length || 1;
    const d = +($('#walkDays') ? $('#walkDays').value : 7);
    if ($('#walkDaysVal')) $('#walkDaysVal').textContent = d + ' 天';
    const per = Math.max(100, Math.round(g / (n * d) / 100) * 100);
    if ($('#goalHint')) $('#goalHint').textContent = n + ' 人一起走 ' + d + ' 天 · 平均每人每天約 ' + per.toLocaleString() + ' 步';
  }
  function recalcWalk(reset) {
    const slider = $('#walkGoal');
    if (!slider) return;
    const n = $$('#inviteList .iv.on').length || 1;
    const d = +($('#walkDays') ? $('#walkDays').value : 7);
    const suggest = Math.round(n * d * 4000 / 1000) * 1000;
    slider.min = Math.max(2000, Math.round(n * d * 1500 / 1000) * 1000);
    slider.max = Math.max(suggest * 2, n * d * 8000);
    slider.step = 1000;
    if (reset || +slider.value < +slider.min || +slider.value > +slider.max) slider.value = suggest;
    updateWalkLabels();
  }
  if (inviteList) inviteList.addEventListener('click', e => { const it = e.target.closest('.iv'); if (it) { it.classList.toggle('on'); recalcWalk(true); } });
  // 挑戰類型選擇
  const INVITE_NOTES = () => ({ walk: '阿嬤那份，' + cname() + '會親口問她', quiz: '阿嬤用說的就能玩；其他人手機作答', event: cname() + '親口問阿嬤；其他人回「去／沒空」' });
  function applyChalKind(kind) {
    if ($('#inviteNote')) $('#inviteNote').textContent = INVITE_NOTES()[kind] || '';
    if ($('#walkFields')) $('#walkFields').style.display = kind === 'walk' ? '' : 'none';
    if ($('#quizFields')) $('#quizFields').style.display = kind === 'quiz' ? '' : 'none';
    if ($('#eventFields')) $('#eventFields').style.display = kind === 'event' ? '' : 'none';
  }
  $$('.chal-type').forEach(b => b.addEventListener('click', () => {
    $$('.chal-type').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    applyChalKind(b.dataset.kind || 'walk');
  }));
  applyChalKind('walk');
  recalcWalk(true);
  // 拉桿連動
  if ($('#walkGoal')) $('#walkGoal').addEventListener('input', () => updateWalkLabels());
  if ($('#walkDays')) $('#walkDays').addEventListener('input', () => recalcWalk(true));
  if ($('#quizN')) $('#quizN').addEventListener('input', () => {
    if ($('#quizNVal')) $('#quizNVal').textContent = $('#quizN').value + ' 題';
  });
  // 日期／時段／期間 點選（單選）
  ['#evDayChips', '#evTimeChips'].forEach(id => {
    const box = $(id);
    if (!box) return;
    box.addEventListener('click', e => {
      const b2 = e.target.closest('.mchip');
      if (!b2) return;
      box.querySelectorAll('.mchip').forEach(x => x.classList.remove('on'));
      b2.classList.add('on');
      if (id === '#evDayChips' && $('#evDatePick')) {
        const g = $('#evDatePick');
        if (b2.dataset.day === 'pick') { buildCalGrid(); g.style.display = ''; } else { g.style.display = 'none'; }
      }
    });
  });
  // 狀態頁三檔切換（今天/本週/本月）
  const statusSeg = $('#statusSeg');
  if (statusSeg) {
    const sviews = { today: $('#statusToday'), week: $('#statusWeek'), month: $('#statusMonth') };
    const stitles = { today: '今天的狀態', week: '這週的狀態', month: '這個月的狀態' };
    statusSeg.addEventListener('click', e => {
      const b = e.target.closest('.seg-btn');
      if (!b) return;
      statusSeg.querySelectorAll('.seg-btn').forEach(x => x.classList.toggle('on', x === b));
      Object.entries(sviews).forEach(([k, el]) => { if (el) el.style.display = k === b.dataset.v ? '' : 'none'; });
      if ($('#statusTitle')) $('#statusTitle').textContent = stitles[b.dataset.v];
    });
  }
  function loadVisit() { try { return JSON.parse(localStorage.getItem('munea.visit')); } catch (e) { return null; } }
  function renderVisitRow() {
    const v = loadVisit();
    const lb = $('#visitLabel');
    if (lb) lb.textContent = v ? (v.label + ' ›') : '未設定 ›';
  }
  if ($('#visitEntry')) $('#visitEntry').addEventListener('click', () => {
    buildCalGrid('#visitDatePick');
    $('#visitModal').classList.add('show');
  });
  if ($('#visitClose')) $('#visitClose').addEventListener('click', () => $('#visitModal').classList.remove('show'));
  if ($('#visitModal')) $('#visitModal').addEventListener('click', e => { if (e.target === $('#visitModal')) $('#visitModal').classList.remove('show'); });
  if ($('#visitTimeChips')) $('#visitTimeChips').addEventListener('click', e => {
    const b = e.target.closest('.mchip');
    if (!b) return;
    $('#visitTimeChips').querySelectorAll('.mchip').forEach(x => x.classList.remove('on'));
    b.classList.add('on');
  });
  if ($('#visitSaveBtn')) $('#visitSaveBtn').addEventListener('click', () => {
    const on = document.querySelector('#visitDatePick .cal-cell.on');
    if (!on) { toast('先選一天'); return; }
    const t = (document.querySelector('#visitTimeChips .mchip.on') || { dataset: {} }).dataset.t || '上午';
    const d = new Date(on.dataset.iso + 'T00:00');
    const label = fmtDay(d) + t;
    try { localStorage.setItem('munea.visit', JSON.stringify({ dateISO: on.dataset.iso, label })); } catch (e2) {} syncPush('visit', { dateISO: on.dataset.iso, label });
    renderVisitRow();
    $('#visitModal').classList.remove('show');
    toast('好，' + label + '回診，' + cname() + '前一天會提醒你，摘要也會先準備好');
  });
  renderVisitRow();
  const FONT_STEPS = [['std', '標準', ''], ['lg', '大', '1.07'], ['xl', '特大', '1.14']];
  function applyFontScale() {
    const cur = localStorage.getItem('munea.fontScale') || 'std';
    const step = FONT_STEPS.find(x => x[0] === cur) || FONT_STEPS[0];
    document.querySelectorAll('.screen .pad, .modal').forEach(el => { el.style.zoom = step[2]; });
    const row = $('#fontRow .sr-arrow');
    if (row) row.textContent = step[1] + ' ›';
  }
  if ($('#fontRow')) $('#fontRow').addEventListener('click', () => {
    const cur = localStorage.getItem('munea.fontScale') || 'std';
    const i = FONT_STEPS.findIndex(x => x[0] === cur);
    const next = FONT_STEPS[(i + 1) % FONT_STEPS.length];
    try { localStorage.setItem('munea.fontScale', next[0]); } catch (e) {}
    applyFontScale();
    toast('字體改成「' + next[1] + '」了');
  });
  applyFontScale();
  if ($('#safetyRow')) $('#safetyRow').addEventListener('click', () => toast('正式版可以選誰收緊急通知；目前跌倒會通知美華'));
  function openLegal(tab) {
    const seg = $('#legalSeg');
    if (seg) seg.querySelectorAll('.seg-btn').forEach(x => x.classList.toggle('on', x.dataset.v === tab));
    if ($('#legalTerms')) $('#legalTerms').style.display = tab === 'terms' ? '' : 'none';
    if ($('#legalPrivacy')) $('#legalPrivacy').style.display = tab === 'privacy' ? '' : 'none';
    $('#legalModal').classList.add('show');
  }
  if ($('#privacyRow')) $('#privacyRow').addEventListener('click', () => openLegal('privacy'));
  if ($('#legalRow')) $('#legalRow').addEventListener('click', () => openLegal('terms'));
  if ($('#legalClose')) $('#legalClose').addEventListener('click', () => $('#legalModal').classList.remove('show'));
  if ($('#legalModal')) $('#legalModal').addEventListener('click', e => { if (e.target === $('#legalModal')) $('#legalModal').classList.remove('show'); });
  if ($('#legalSeg')) $('#legalSeg').addEventListener('click', e => {
    const b = e.target.closest('.seg-btn');
    if (b) openLegal(b.dataset.v);
  });
  const authTermsLink = document.querySelector('.auth-terms a');
  if (authTermsLink) authTermsLink.addEventListener('click', e => { e.preventDefault(); closeAuthSheet(); openLegal('terms'); });
  if ($('#historyEntry')) $('#historyEntry').addEventListener('click', () => { rcInit(); $('#historyModal').classList.add('show'); });
  if ($('#histSeg')) $('#histSeg').addEventListener('click', e => {
    const b = e.target.closest('.seg-btn');
    if (!b) return;
    $('#histSeg').querySelectorAll('.seg-btn').forEach(x => x.classList.toggle('on', x === b));
    $('#histMonths').style.display = b.dataset.v === 'months' ? '' : 'none';
    $('#histRange').style.display = b.dataset.v === 'range' ? '' : 'none';
  });
  // 自選日期範圍（一年內）
  let rcYear = 0, rcMonth = 0, rcStart = null, rcEnd = null;
  function rcInit() {
    const now = new Date();
    rcYear = now.getFullYear(); rcMonth = now.getMonth();
    rcStart = null; rcEnd = null;
    if ($('#rcResult')) { $('#rcResult').style.display = 'none'; }
    if ($('#rcHint')) $('#rcHint').textContent = '點開始那天，再點結束那天';
    renderRangeCal();
  }
  function renderRangeCal() {
    const grid = $('#rcGrid');
    if (!grid) return;
    if ($('#rcTitle')) $('#rcTitle').textContent = rcYear + ' 年 ' + (rcMonth + 1) + ' 月';
    const startPad = (new Date(rcYear, rcMonth, 1).getDay() + 6) % 7;
    const daysInM = new Date(rcYear, rcMonth + 1, 0).getDate();
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const minDate = new Date(today); minDate.setFullYear(minDate.getFullYear() - 1);
    let html = '';
    for (let i = 0; i < startPad; i++) html += '<span class="rc-cell pad"></span>';
    for (let d = 1; d <= daysInM; d++) {
      const dt = new Date(rcYear, rcMonth, d);
      const iso = isoOf(dt);
      let cls = 'rc-cell';
      if (dt > today || dt < minDate) cls += ' off';
      if (rcStart && iso === rcStart) cls += ' sel';
      if (rcEnd && iso === rcEnd) cls += ' sel';
      if (rcStart && rcEnd && iso > rcStart && iso < rcEnd) cls += ' in';
      html += '<span class="' + cls + '" data-iso="' + iso + '">' + d + '</span>';
    }
    grid.innerHTML = html;
  }
  function rcShowResult() {
    const a = new Date(rcStart + 'T00:00'), b2 = new Date(rcEnd + 'T00:00');
    const days = Math.round((b2 - a) / 86400000) + 1;
    const med = Math.max(1, Math.round(days * 0.86));
    const act = Math.max(1, Math.round(days * 0.55));
    const box = $('#rcResult');
    box.innerHTML = '<div class="rpt-row"><span class="rpt-k">期間</span><div><b>' + fmtDay(a) + ' 到 ' + fmtDay(b2) + '</b><span>共 ' + days + ' 天（示範數據）</span></div></div>' +
      '<div class="rpt-row"><span class="rpt-k">用藥</span><div><b>準時 ' + med + ' / ' + days + ' 天</b></div></div>' +
      '<div class="rpt-row"><span class="rpt-k">活動</span><div><b>達標 ' + act + ' 天</b></div></div>' +
      '<div class="rpt-row"><span class="rpt-k">睡眠</span><div><b>平均 7.2 小時</b></div></div>';
    box.style.display = '';
    if ($('#rcHint')) $('#rcHint').textContent = '要看別段，再點一次新的開始日';
  }
  if ($('#rcGrid')) $('#rcGrid').addEventListener('click', e => {
    const cell = e.target.closest('.rc-cell');
    if (!cell || cell.classList.contains('off') || cell.classList.contains('pad')) return;
    const iso = cell.dataset.iso;
    if (!rcStart || (rcStart && rcEnd)) { rcStart = iso; rcEnd = null; if ($('#rcResult')) $('#rcResult').style.display = 'none'; if ($('#rcHint')) $('#rcHint').textContent = '再點結束那天'; }
    else if (iso < rcStart) { rcStart = iso; if ($('#rcHint')) $('#rcHint').textContent = '再點結束那天'; }
    else { rcEnd = iso; rcShowResult(); }
    renderRangeCal();
  });
  if ($('#rcPrev')) $('#rcPrev').addEventListener('click', () => {
    const min = new Date(); min.setFullYear(min.getFullYear() - 1);
    if (new Date(rcYear, rcMonth - 1, 28) < min) { toast('紀錄保存一年，再往前就沒有了'); return; }
    rcMonth--; if (rcMonth < 0) { rcMonth = 11; rcYear--; }
    renderRangeCal();
  });
  if ($('#rcNext')) $('#rcNext').addEventListener('click', () => {
    const now = new Date();
    if (rcYear === now.getFullYear() && rcMonth === now.getMonth()) { toast('已經是這個月了'); return; }
    rcMonth++; if (rcMonth > 11) { rcMonth = 0; rcYear++; }
    renderRangeCal();
  });
  if ($('#historyClose')) $('#historyClose').addEventListener('click', () => $('#historyModal').classList.remove('show'));
  if ($('#historyModal')) $('#historyModal').addEventListener('click', e => {
    if (e.target === $('#historyModal')) { $('#historyModal').classList.remove('show'); return; }
    const row = e.target.closest('.hist-row');
    if (row) toast(row.classList.contains('dim') ? '正式版點開就是當月整理，示範先看 6 月這行' : '6 月整理好了，完整月報之後接引擎');
  });

  // B1 提醒排程：app 開著就到點響（打包後升級推播）
  const SLOT_MIN = { '早餐後': ['b', 30], '午餐後': ['l', 30], '晚餐後': ['d', 30], '睡前': ['s', -30] };
  function slotDueMinutes(slot) {
    const m = SLOT_MIN[slot];
    if (!m) return null;
    const rt = loadRoutine();
    const [h2, mi] = (rt[m[0]] || '08:00').split(':').map(Number);
    return h2 * 60 + mi + m[1];
  }
  function todayKey() { const n = new Date(); return 'munea.medDone.' + isoOf(n); }
  let medSnoozeUntil = 0, medShowing = null;
  function fireMedReminder(med) {
    medShowing = med;
    if ($('#medDueName')) $('#medDueName').textContent = med.name;
    if ($('#medDueSay')) $('#medDueSay').textContent = cname() + '：' + med.time + '的藥，時間到囉';
    showView('med');
  }
  function checkDueMeds() {
    if (Date.now() < medSnoozeUntil || medShowing) return;
    const now = new Date();
    const nowMin = now.getHours() * 60 + now.getMinutes();
    let done = {};
    try { done = JSON.parse(localStorage.getItem(todayKey())) || {}; } catch (e) {}
    for (const med of loadMeds()) {
      for (const slot of String(med.time).split('、')) {
        const due = slotDueMinutes(slot.trim());
        if (due === null) continue;
        const key = slot.trim() + '|' + med.name;
        if (!done[key] && nowMin >= due && nowMin <= due + 20) { fireMedReminder({ ...med, time: slot.trim(), key }); return; }
      }
    }
  }
  window.__fireMedNow = () => { const m = loadMeds()[0]; if (m) fireMedReminder({ ...m, time: String(m.time).split('、')[0], key: 'test|' + m.name }); };
  if ($('#medTaken')) $('#medTaken').addEventListener('click', () => {
    if (medShowing) {
      let done = {};
      try { done = JSON.parse(localStorage.getItem(todayKey())) || {}; } catch (e) {}
      done[medShowing.key] = true;
      try { localStorage.setItem(todayKey(), JSON.stringify(done)); } catch (e) {}
      pushFamilyFeed('<b>阿嬤</b>' + medShowing.time + '的藥吃了，' + cname() + '有看著');
    }
    medShowing = null;
    showView('home');
    toast('記下了，藥吃了。');
    const pt = document.querySelector('.task-item[data-task="pill"]');
    if (pt && !pt.classList.contains('done')) { pt.classList.add('done'); refreshTaskProgress(); }
  });
  if ($('#medSnooze')) $('#medSnooze').addEventListener('click', () => {
    medSnoozeUntil = Date.now() + 10 * 60 * 1000;
    medShowing = null;
    showView('home');
    toast('好，10 分鐘後再提醒你。');
  });
  setInterval(checkDueMeds, 30000);
  setTimeout(checkDueMeds, 1500);
  // 回診前一天：開 app 提醒一次
  (function visitEve() {
    const v = loadVisit && loadVisit();
    if (!v || !v.dateISO) return;
    const t = new Date(); t.setDate(t.getDate() + 1);
    if (v.dateISO === isoOf(t) && !sessionStorage.getItem('visitEveShown')) {
      sessionStorage.setItem('visitEveShown', '1');
      setTimeout(() => toast('明天' + v.label.slice(-2) + '回診，回診摘要我準備好了'), 1200);
    }
  })();

  // 機智問答（示範題庫；正式版由寧寧出題、語音作答）
  const QUIZ_BANK = [
    { q: '一般建議大人每天走多少步，比較有活力？', opts: ['500 步', '2,000 步', '7,000 步左右', '50,000 步'], a: 2 },
    { q: '下面哪一個是台灣的傳統節日？', opts: ['感恩節', '端午節', '萬聖節', '復活節'], a: 1 },
    { q: '睡前做哪件事，通常比較好睡？', opts: ['喝濃茶', '滑手機', '聽輕音樂', '吃宵夜'], a: 2 },
    { q: '「一暝大一寸」說的是誰？', opts: ['小嬰兒', '大樹', '月亮', '麵團'], a: 0 },
    { q: '夏天出門，哪件事最重要？', opts: ['多喝水', '穿厚外套', '戴毛帽', '正中午曬太陽'], a: 0 },
    { q: '台灣哪個節日要吃湯圓？', opts: ['冬至', '端午節', '中秋節', '清明節'], a: 0 },
    { q: '晚上走路，穿什麼顏色比較安全？', opts: ['亮色或反光', '全黑', '深藍', '深咖啡'], a: 0 },
    { q: '「呷緊弄破碗」是什麼意思？', opts: ['欲速則不達', '吃飯要快', '碗要買厚的', '肚子餓了'], a: 0 },
    { q: '綠燈行，紅燈要怎樣？', opts: ['停', '衝', '倒退', '按喇叭'], a: 0 },
    { q: '台灣夏天最有名的水果是？', opts: ['芒果', '蘋果', '水梨', '柿子'], a: 0 },
    { q: '喝茶說的「回甘」是指？', opts: ['喝完嘴裡回甜', '茶很苦', '茶涼了', '要再泡一次'], a: 0 },
    { q: '中秋節大家常一起做什麼？', opts: ['烤肉賞月', '包粽子', '掃墓', '提燈籠'], a: 0 },
    { q: '台語「呷飽未」是什麼意思？', opts: ['吃飽了嗎', '睡飽了嗎', '要出門嗎', '天氣好嗎'], a: 0 },
    { q: '散步選什麼時段比較舒服？', opts: ['清晨或傍晚', '正中午', '半夜', '颱風天'], a: 0 },
    { q: '睡前喝哪一種，比較不好睡？', opts: ['濃咖啡', '溫開水', '溫牛奶', '無咖啡因花茶'], a: 0 },
    { q: '元宵節會做什麼？', opts: ['提燈籠吃元宵', '烤肉', '立蛋', '吃月餅'], a: 0 },
    { q: '「家和萬事」下一個字是？', opts: ['興', '好', '成', '樂'], a: 0 },
    { q: '適度曬太陽，身體會自己做出什麼？', opts: ['維生素 D', '維生素 C', '鐵', '鈣片'], a: 0 },
    { q: '過馬路前，先做哪件事？', opts: ['左右看清楚', '看手機', '快跑', '閉眼睛'], a: 0 },
  ];
  let quizState = null;
  function startQuiz(act, card) {
    quizState = { act, card, i: 0, score: 0, n: Math.min(act.q || 5, QUIZ_BANK.length) };
    renderQuizStep();
    $('#quizModal').classList.add('show');
  }
  function renderQuizStep() {
    const st = quizState;
    if (!st) return;
    const item = QUIZ_BANK[st.i];
    $('#quizProgress').textContent = '第 ' + (st.i + 1) + ' 題／共 ' + st.n + ' 題';
    $('#quizQ').textContent = item.q;
    const order = item.opts.map((_, k) => k).sort((a2, b2) => ((a2 * 7 + st.i * 3) % 4) - ((b2 * 7 + st.i * 3) % 4));
    st.map = order;
    $('#quizOpts').innerHTML = order.map(k => '<button type="button" class="quiz-opt" data-k="' + k + '">' + item.opts[k] + '</button>').join('');
  }
  function finishQuiz() {
    const st = quizState;
    $('#quizProgress').textContent = '完成！';
    $('#quizQ').textContent = '';
    $('#quizOpts').innerHTML = '<div class="quiz-score">答對 ' + st.score + ' / ' + st.n + ' 題</div>' +
      '<p class="modal-sub" style="text-align:center">寧寧會找 ' + st.act.names.join('、') + ' 來作答，都答完就看排名</p>' +
      '<button class="modal-btn quiz-close-btn" type="button">好</button>';
    const closeBtn = $('#quizOpts .quiz-close-btn');
    if (closeBtn) closeBtn.addEventListener('click', () => $('#quizModal').classList.remove('show'));
    const note = st.card && st.card.querySelector('.qc-num');
    if (note) note.textContent = '你答對 ' + st.score + '/' + st.n + '，等 ' + st.act.names.join('、') + ' 作答完看排名';
    const acts2 = loadActs();
    const rec = acts2.find(a => a.id === st.act.id);
    if (rec) { rec.status = 'done'; rec.score = st.score; rec.doneISO = isoOf(new Date()); saveActs(acts2); }
    pushFamilyFeed('<b>你</b>完成了機智問答，答對 ' + st.score + '/' + st.n + ' 題，等大家玩完看排名');
  }
  if ($('#quizOpts')) $('#quizOpts').addEventListener('click', e => {
    const btn = e.target.closest('.quiz-opt');
    if (!btn || !quizState) return;
    const item = QUIZ_BANK[quizState.i];
    const k = +btn.dataset.k;
    [...$('#quizOpts').children].forEach(b2 => {
      if (+b2.dataset.k === item.a) b2.classList.add('good');
      else if (b2 === btn) b2.classList.add('bad');
      b2.disabled = true;
    });
    if (k === item.a) quizState.score++;
    setTimeout(() => { quizState.i++; if (quizState.i >= quizState.n) finishQuiz(); else renderQuizStep(); }, 700);
  });
  if ($('#quizModal')) $('#quizModal').addEventListener('click', e => { if (e.target === $('#quizModal')) $('#quizModal').classList.remove('show'); });

  // 家庭記錄簿
  function openBook() { showView('family'); $$('#family .fam-view').forEach(v => v.classList.remove('active')); $('#viewBook').classList.add('active'); }
  if ($('#bookBtn')) $('#bookBtn').addEventListener('click', openBook);
  const peekCard = document.querySelector('.fam-peek');
  if (peekCard) { peekCard.style.cursor = 'pointer'; peekCard.addEventListener('click', openBook); }
  if ($('#bookBack')) $('#bookBack').addEventListener('click', () => { $('#viewBook').classList.remove('active'); $('#viewAll').classList.add('active'); });

  // 聊聊：日常語音陪聊 · [ENGINE] 正式版換中文（台灣）/英文即時語音 + 反射腦
  const SR2 = window.SpeechRecognition || window.webkitSpeechRecognition;
  let chatRec = null, chatOn = false;
  const CHAT_RULES = [
    [/(藥.*(怎麼吃|幾顆|[0-9一二兩三四五]顆|停|加量|減量|可以吃|能不能吃))|劑量|(可以吃.*藥)/, '藥怎麼吃、吃幾顆，我不能幫你決定，這要聽醫生或藥師的喔。要不要我幫你記下來，回診時問醫生？'],
    [/痛|痠|不舒服|頭暈/, '聽到你不太舒服，我有點擔心。先坐下歇會兒，需要的話我幫你通知美華。'],
    [/累|睡不|失眠/, '辛苦了，累了就休息、不要硬撐，我在這裡陪你。'],
    [/孫|想.*他|想.*她|寂寞|一個人/, '想家人了是吧？要不要我提醒他們今晚打給你？'],
    [/吃|飯|餓|藥/, '好，吃飯吃藥都別忘了，到時間我會叫你。'],
    [/天氣|冷|熱|下雨/, '記得隨天氣加減衣服，別著涼了。'],
    [/謝|你真好|感謝/, '不用謝，陪著你是我最想做的事。'],
  ];
  function chatReply(t) { for (const [re, r] of CHAT_RULES) if (re.test(t.toLowerCase())) return r; return '我聽見了，你慢慢說，我都在。'; }
  function parseChatIntent(t) {
    // 聊聊代辦：講一句、寧寧直接把 app 設定做好（原型版；真腦版走同一批動作）
    const relay0 = t.match(/(提醒|告訴|跟)\s*([一-龥]{2,3})(說|，|要|來)?\s*(.{2,30})/);
    if (relay0 && relay0[2] !== '我' && !/我/.test(relay0[2])) {
      let who = relay0[2].replace(/[要說來]$/, '');
      if (who.length < 2) who = relay0[2];
      pushFamilyFeed('<b>你</b>托' + cname() + '帶話給' + who + '：' + relay0[4].replace(/^[要說來，]/, '').replace(/[。！]$/, ''));
      return '好，我會帶話給' + who + '，也會顯示在' + who + '的首頁上。';
    }
    const seg = (t.match(/(早餐後|午餐後|晚餐後|睡前)/) || [])[1];
    if (/(提醒|記得|叫我).*吃.{0,4}藥|吃.{0,4}藥.*(提醒|記)|(提醒|記得|叫我).*(吃藥|用藥)|(吃藥|用藥).*(提醒|記)/.test(t)) {
      let name = (t.match(/吃(「)?([一-龥A-Za-z0-9]{1,6}藥)/) || [])[2] || (t.match(/吃(「)?([一-龥A-Za-z0-9]{2,6})(」)?(藥)?/) || [])[2];
      const meds = loadMeds();
      meds.push({ name: name && name !== '血壓' ? name : '血壓藥', time: seg || '早餐後', days: '長期', by: '本人' });
      try { localStorage.setItem('munea.meds', JSON.stringify(meds)); syncPush('meds', meds); } catch (e) {}
      updateMedCount();
      return '好，我幫你設好了：' + (seg || '早餐後') + '提醒吃藥，時間照你的作息。想改隨時跟我說。';
    }
    const visitDay = (t.match(/(\d{1,2})[\/月](\d{1,2})/) || []);
    if (/(回診|看診|門診).*(提醒|記)/.test(t) || (/(回診|看診)/.test(t) && visitDay[0])) {
      if (visitDay[0]) {
        const now = new Date();
        const d = new Date(now.getFullYear(), +visitDay[1] - 1, +visitDay[2]);
        const label = (d.getMonth() + 1) + '/' + d.getDate() + '（週' + '日一二三四五六'[d.getDay()] + '）' + (/(下午)/.test(t) ? '下午' : /(晚上)/.test(t) ? '晚上' : '上午');
        const iso2 = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
        try { localStorage.setItem('munea.visit', JSON.stringify({ dateISO: iso2, label })); } catch (e) {} syncPush('visit', { dateISO: iso2, label });
        if (typeof renderVisitRow === 'function') try { renderVisitRow(); } catch (e2) {}
        return '記好了，' + label + '回診。我前一天會提醒你，回診摘要也會先準備好。';
      }
      return '好，跟我說是哪一天回診（例如 7 月 10 日下午），我來設提醒。';
    }
    return null;
  }
  window.__chatTest = t => { const r = parseChatIntent(t); return r || chatReply(t); };
  async function chatHandle(t) {
    const acted = parseChatIntent(t);
    if (acted) { speakChat(acted); return; }
    setCallHint('我聽見了');
    chatHistory.push({ role: 'user', text: t });
    activeChatTurnCount += 1;
    // [S2S] 思考態：不顯示文字稿，只讓臉與狀態提示表達「她在想」
    setTimeout(() => { setFaceState('thinking'); setCallHint('我想一下'); }, 380);
    const r = await voiceProvider.sendText({ history: chatHistory, char: currentChar });
    if (r && r.reply) {                              // 真腦回話＋真聲音
      setCallHint('正在說話');
      chatHistory.push({ role: 'model', text: r.reply });
      if (r.audio) playB64(r.audio); else speakChat(r.reply);
      faceSpeak(r.reply);
      trackProductEvent('voice_turn_completed', {
        turnCount: activeChatTurnCount,
        replyAudio: !!r.audio,
        fallbackUsed: false,
      });
      postTurnReview();
    } else {                                          // 沒真腦 → 退回規則版（純靜態 demo 也能動）
      const rr = chatReply(t);
      setCallHint('正在說話');
      chatHistory.push({ role: 'model', text: rr });
      speakChat(rr);
      faceSpeak(rr);
      trackProductEvent('voice_session_fallback_used', {
        turnCount: activeChatTurnCount,
        fallback: 'local-rule-reply',
      });
      postTurnReview();
    }
  }
  function blobToDataUrl(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }
  async function sendVoiceNote(blob, durationMs) {
    if (!blob || !blob.size) {
      setCallHint('沒有聽清楚，再說一次');
      setFaceState('idle');
      return;
    }
    setCallHint('我想一下');
    const audio = await blobToDataUrl(blob);
    const r = await voiceProvider.sendVoiceNote({ char: currentChar, audio, mime: blob.type || 'audio/webm', durationMs });
    if (r && r.ok) {
      trackProductEvent('voice_note_uploaded', {
        durationMs,
        bytes: r.bytes || 0,
        mime: blob.type || 'audio/webm',
      });
      setCallHint('正在說話');
    } else {
      trackProductEvent('voice_session_fallback_used', {
        fallback: 'voice-note-upload-failed',
        durationMs,
      });
      setCallHint('目前無法語音連線');
      const s = prompt(`我先用文字接住你，想跟${companionDisplayName}說什麼？`);
      if (s) chatHandle(s);
    }
    setFaceState('idle');
  }
  const chatMic = $('#chatMic');
  let mediaRec = null, mediaChunks = [], mediaStartedAt = 0;
  async function startVoiceCapture() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
      const s = prompt(`（這個裝置先用打字，正式版用即時語音）跟${companionDisplayName}說什麼？`);
      if (s) chatHandle(s);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaChunks = [];
      mediaStartedAt = Date.now();
      mediaRec = new MediaRecorder(stream);
      mediaRec.ondataavailable = e => { if (e.data && e.data.size) mediaChunks.push(e.data); };
      mediaRec.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        chatOn = false;
        chatMic.classList.remove('recording');
        const blob = new Blob(mediaChunks, { type: mediaRec.mimeType || 'audio/webm' });
        await sendVoiceNote(blob, Date.now() - mediaStartedAt);
      };
      mediaRec.start();
      chatOn = true;
      chatMic.classList.add('recording');
      setFaceState('listening');
      setCallHint('我在聽，說完再按一次');
    } catch (e) {
      setCallHint('目前拿不到麥克風權限');
      const s = prompt(`想跟${companionDisplayName}說什麼？`);
      if (s) chatHandle(s);
    }
  }
  let micMuted = false;
  function startListening() {
    if (!SR2 || chatOn || micMuted || !callConnected) return;
    chatRec = new SR2(); chatRec.lang = 'zh-TW'; chatRec.interimResults = false;
    chatRec.onstart = () => { chatOn = true; chatMic && chatMic.classList.add('recording'); setFaceState('listening'); setCallHint('我在聽'); };
    chatRec.onresult = e => chatHandle(e.results[0][0].transcript);
    chatRec.onend = () => {
      chatOn = false;
      chatMic && chatMic.classList.remove('recording');
      if (callConnected && !micMuted) { setTimeout(() => startListening(), 300); }
      else if ($('#chat') && $('#chat').dataset.state === 'listening') setFaceState('idle');
    };
    chatRec.onerror = chatRec.onend;
    try { chatRec.start(); } catch (e) {}
  }
  window.__muneaStartListen = startListening;
  window.__muneaStopListen = () => { micMuted = false; try { chatRec && chatRec.stop(); } catch (e) {} };
  if (chatMic) chatMic.addEventListener('click', async () => {
    if (!SR2) {
      if (chatOn && mediaRec) { mediaRec.stop(); return; }
      await startVoiceCapture();
      return;
    }
    if (!callConnected) { // 還沒接通：按一下講一句（舊行為保底）
      if (chatOn) { chatRec && chatRec.stop(); return; }
      startListening();
      return;
    }
    // 通話中：麥克風＝靜音開關
    micMuted = !micMuted;
    chatMic.classList.toggle('off', micMuted);
    if (micMuted) { try { chatRec && chatRec.stop(); } catch (e) {} setCallHint('麥克風先關著'); }
    else { setCallHint('我在聽'); startListening(); }
  });

  // 陪伴角色：使用者命名與模板分離
  const companionNameInput = $('#companionNameInput');
  if (companionNameInput) {
    companionNameInput.addEventListener('input', e => setCompanionName(e.target.value, { skipBackend: true }));
    companionNameInput.addEventListener('blur', () => {
      if (!companionDisplayName.trim()) companionDisplayName = templateFor().defaultName;
      companionNameTouched = companionDisplayName.trim().length > 0;
      saveCompanionProfileToBackend();
      persistCompanionProfile();
      syncCompanionUI();
      saveCompanionProfileToBackend();
      syncAccountBootstrap('create', { reason: 'companion_name_updated' });
      toast('名字改好了：以後叫「' + companionDisplayName.trim() + '」');
    });
  }
  const avatarPick = $('#avatarPick');
  if (avatarPick) avatarPick.addEventListener('click', e => {
    const o = e.target.closest('.avo:not(.soon)'); if (!o) return;
    const wasOn = o.classList.contains('on');
    setCompanionTemplate(o.dataset.ava);
    if (!wasOn) {
      const label = o.querySelector('.avl b');
      toast('已換成 ' + (label ? label.textContent : '新的陪伴'));
    }
  });

  if ('speechSynthesis' in window) speechSynthesis.onvoiceschanged = () => {};
}
document.addEventListener('DOMContentLoaded', init);
