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
  const toggle = $('#aiProviderConsentToggle');
  const status = $('#aiProviderConsentStatus');
  const panel = $('#aiProviderConsentPanel');
  if (toggle) toggle.checked = consent.agreed === true;
  if (status) status.textContent = consent.agreed ? '已同意' : '尚未同意';
  if (panel) panel.dataset.consent = consent.agreed ? 'agreed' : 'missing';
}
function setupAiProviderConsentControls() {
  const toggle = $('#aiProviderConsentToggle');
  if (!toggle) return;
  updateAiProviderConsentUI();
  toggle.addEventListener('change', e => {
    saveAiProviderConsent(e.target.checked, 'settings');
  });
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
function updateAuthUI() {
  const state = authState();
  const signedIn = state.status === 'signed-in';
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
  if ($('#authSignOutBtn')) $('#authSignOutBtn').addEventListener('click', signOutAuth);
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
    let icon = sun, text = '晴 26°，下午去公園正好';
    if (h >= 18 || h < 5) { icon = moon; text = '睡前 10 分鐘，說說今天的事'; }
    else if (h >= 5 && h < 11) { text = '晴 26°，早上出門走走正好'; }
    else if (h >= 14) { text = '晴 26°，傍晚去公園正好'; }
    chip.innerHTML = icon + text;
  }
  const stat = $('#bcStatus');
  if (stat) stat.textContent = '連續 6 天都有聊 · 今天還沒';
  const wd = ['日','一','二','三','四','五','六'][now.getDay()];
  const meta = $('#metaDate');
  if (meta) meta.textContent = `${now.getMonth() + 1}月${now.getDate()}日 週${wd}`;
  const kick = $('#greetKicker'), big = $('#greetBig');
  let k = '今日概況', b = '今天想先聊聊嗎？';
  if (h >= 5 && h < 11) { k = '早安'; b = '新的一天，想先聊聊嗎？'; }
  else if (h >= 11 && h < 14) { k = '午安'; b = '吃飽了嗎？來聊聊吧'; }
  else if (h >= 14 && h < 18) { k = '午後好'; b = '下午了，想聊聊今天的事嗎？'; }
  else if (h >= 18 && h < 22) { k = '晚上好'; b = '今天過得怎麼樣？'; }
  else { k = '夜深了'; b = '睡前想說說話嗎？'; }
  if (kick) kick.textContent = k;
  if (big) big.textContent = b;
})();

function loadMeds() {
  try { return JSON.parse(localStorage.getItem('munea.meds')) || [
    { name: '脈優 Amlodipine', time: '14:00', days: '長期', by: '美華' },
    { name: '維他命 D', time: '08:30', days: '30 天', by: '阿嬤' }]; } catch (e) { return []; }
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

const POINTS = { total: 800, used: 320 };
function renderPoints() {
  const left = POINTS.total - POINTS.used;
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
function pushFamilyFeed(text) {
  const peek = $('.fam-peek .fp-text');
  if (peek) peek.innerHTML = text;
  try { localStorage.setItem('munea.familyFeed', text); } catch (e) {}
}
function restoreFamilyFeed() {
  try { const t = localStorage.getItem('munea.familyFeed'); if (t) { const peek = $('.fam-peek .fp-text'); if (peek) peek.innerHTML = t; } } catch (e) {}
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
  chat: '謝謝你跟我說這些，我都記著呢。',
};
function refreshTaskProgress() {
  const items = $$('#taskCard .task-item');
  const done = items.filter(i => i.classList.contains('done')).length;
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
      toast('這件已經完成了——再按一次才會取消。');
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
function moodFaceSvg(key, size) {
  const m = MOODS[key] || MOODS.calm;
  return '<svg class="ic" viewBox="0 0 24 24" style="color:' + m.fg + ';width:' + size + 'px;height:' + size + 'px"><circle cx="12" cy="12" r="9"/><path d="' + m.face + '"/></svg>';
}
function renderMoodWeek() {
  const wrap = $('#moodWeek');
  if (!wrap) return;
  wrap.innerHTML = MOOD_WEEK_DEMO.map((day, i) => {
    const m = MOODS[day.mood];
    const today = day.d === '今天';
    return '<button class="md' + (today ? ' today' : '') + '" data-i="' + i + '">' +
      '<span class="mcirc" style="background:' + m.bg + '">' + moodFaceSvg(day.mood, 22) +
      (day.mixed ? '<span class="mixdot"></span>' : '') + '</span>' +
      '<span class="mday">' + day.d + '</span></button>';
  }).join('');
  wrap.querySelectorAll('.md').forEach(b => b.addEventListener('click', () => showMoodDay(+b.dataset.i)));
  showMoodDay(MOOD_WEEK_DEMO.length - 1);
}
function showMoodDay(i) {
  const day = MOOD_WEEK_DEMO[i];
  const box = $('#moodDayDetail');
  if (!box || !day) return;
  box.innerHTML = '<div class="dd-date">' + (day.d === '今天' ? '今天' : '週' + day.d) + ' · 聊了 ' + day.chats.length + ' 次</div>' +
    day.chats.map(c => '<div class="dd-row">' + moodFaceSvg(c.m, 19) + '<span>' + c.t + '</span></div>').join('');
}
function renderMoodMonth() {
  const wrap = $('#moodMonth');
  if (!wrap || wrap.childElementCount) return;
  const seq = ['calm','glad','happy','calm','tired','glad','calm','down','calm','glad','happy','glad','calm','calm','tired','glad','calm','happy','glad','calm','down','tired','glad','calm','happy','glad','calm','happy'];
  wrap.innerHTML = seq.map(k => '<b style="background:' + MOODS[k].bg + '" title="' + MOODS[k].label + '"></b>').join('');
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
  setCaption('接通了——按一下麥克風跟我說話', '講完再按一次，寧寧就會回你');
  openVoiceSession();
}

function init() {
  if (location.hash === '#med') setTimeout(() => showView('med'), 300);
  syncCompanionUI();
  setupHscrollHints();
  renderPoints();
  updateMedCount();
  if ($('#callToggle')) $('#callToggle').addEventListener('click', () => {
    if (!callConnected) { connectCall(); }
    else { completeChatSession('user_ended'); chatOpened = false; setCallToggle(false); showView('home'); }
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
  if ($('#startCall')) $('#startCall').addEventListener('click', () => showView('chat'));
  // 用藥服務窗（獨立功能、保留）
  if ($('#medTaken')) $('#medTaken').addEventListener('click', () => {
    trackProductEvent('routine_reminder_completed', { reminderType: 'medication' });
    hint('好，記下來了，連續六天，你真棒。');
    showView('home');
  });
  if ($('#medSnooze')) $('#medSnooze').addEventListener('click', () => showView('home'));

  // 連接裝置（狀態頁資料條 / 設定裝置區 → 串接三方裝置引導）
  if ($('#srcStrip')) $('#srcStrip').addEventListener('click', () => showView('connect'));
  if ($('#setDevices')) $('#setDevices').addEventListener('click', () => showView('connect'));
  if ($('#companionRow')) $('#companionRow').addEventListener('click', () => $('#companionSheet').classList.add('show'));
  if ($('#companionCloseBtn')) $('#companionCloseBtn').addEventListener('click', () => $('#companionSheet').classList.remove('show'));
  if ($('#quizCloseX')) $('#quizCloseX').addEventListener('click', () => $('#quizModal').classList.remove('show'));
  if ($('#companionSheet')) $('#companionSheet').addEventListener('click', e => { if (e.target === $('#companionSheet')) $('#companionSheet').classList.remove('show'); });
  if ($('#setProfile')) $('#setProfile').addEventListener('click', () => hint('這裡可以改頭像、名稱、對家人顯示的稱呼、年齡、所在地。'));
  if ($('#connectBack')) $('#connectBack').addEventListener('click', () => showView('status'));
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
    hint(`好，寧寧會幫你轉達——你${b.dataset.react}。`);
    const who = document.getElementById('ptName')?.textContent || '家人';
    pushFamilyFeed(`<b>你</b>剛剛給${who}${b.dataset.react || '送上心意'}——寧寧下次聊天會親口告訴${['阿嬤','美華'].includes(who) ? '她' : '他'}`);
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
    $('#moodDayDetail').style.display = month ? 'none' : '';
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
    try { localStorage.setItem('munea.meds', JSON.stringify(meds)); } catch (e) {}
    $('#medName').value = '';
    document.querySelectorAll('#medTimeChips .mchip.on').forEach(x => x.classList.remove('on'));
    renderMedList();
    updateMedCount();
    toast('好，寧寧會在' + times.join('、') + '提醒吃「' + name + '」');
  });
  if ($('#medEntryStatus')) $('#medEntryStatus').addEventListener('click', () => { renderMedList(); $('#medMgrModal').classList.add('show'); });
  if ($('#medBackBtn')) $('#medBackBtn').addEventListener('click', () => showView('settings'));
  if ($('#topUpBtn')) $('#topUpBtn').addEventListener('click', () => toast('加值方案：120 點 NT$120 ／ 500 點 NT$450 ——正式版在這裡直接買。'));
  if ($('#managePlanBtn')) $('#managePlanBtn').addEventListener('click', () => toast('方案管理：升級、降級、取消都在這裡；發票寄給付費的家人。'));
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
  const trendTabs = $('#trendTabs');
  if (trendTabs) trendTabs.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    trendTabs.querySelectorAll('button').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    const week = [55,72,45,80,62,90,75], month = [62,70,76,84,72,88,80];
    const data = b.dataset.range === 'month' ? month : week;
    $$('#trendBars .tb i').forEach((i, idx) => i.style.height = data[idx] + '%');
    $$('#trendBars .tb span').forEach((s, idx) => s.textContent = b.dataset.range === 'month' ? ['第1','第2','第3','第4','週','',''][idx] : ['一','二','三','四','五','六','日'][idx]);
  });

  // 一鍵回診摘要
  const rep = $('#reportBtn');
  if (rep) rep.addEventListener('click', () => $('#reportModal').classList.add('show'));
  if ($('#reportClose')) $('#reportClose').addEventListener('click', () => $('#reportModal').classList.remove('show'));
  if ($('#reportModal')) $('#reportModal').addEventListener('click', e => { if (e.target === $('#reportModal')) $('#reportModal').classList.remove('show'); });
  if ($('#rptSendBtn')) $('#rptSendBtn').addEventListener('click', () => {
    $('#reportModal').classList.remove('show');
    toast('傳給美華了——回診那天她手機一打開就有');
    pushFamilyFeed('<b>阿嬤</b>把 6 月的回診摘要傳給了美華');
  });

  // 發起挑戰面板
  const chalModal = $('#chalModal');
  const closeChal = () => chalModal && chalModal.classList.remove('show');
  if ($('#newChalBtn')) $('#newChalBtn').addEventListener('click', () => chalModal && chalModal.classList.add('show'));
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
  function buildCalGrid() {
    const box = $('#evDatePick');
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
  function saveActs(a) { try { localStorage.setItem('munea.activities', JSON.stringify(a)); } catch (e) {} }
  function renderActCard(act) {
    const list = document.querySelector('#newChalBtn')?.closest('.pad')?.querySelector('.quest-card');
    if (!list) return;
    const card = document.createElement('div');
    card.className = 'quest-card pending';
    let chip, goal, note;
    if (act.status === 'done') {
      chip = '已結束';
      goal = act.kind === 'quiz' ? ('你答對 ' + act.score + ' / ' + (act.q || 5) + ' 題') : (act.title + ' 結束了');
      note = '等大家都看過就收進記錄簿 · 最多留 3 天——還沒看的，寧寧會親口告訴';
    } else if (act.kind === 'walk') {
      chip = act.days === 3 ? '3 天內' : '一週內';
      goal = '大家一起走 ' + (+act.goal).toLocaleString() + ' 步';
      note = '寧寧會親口問阿嬤要不要一起；開始後每個人走多少都看得到';
    } else if (act.kind === 'quiz') {
      chip = act.q + ' 題';
      goal = '你的 ' + act.q + ' 題準備好了';
      note = '點這張卡先作答；寧寧會找其他人玩，都答完看排名';
    } else {
      chip = act.dateLabel;
      goal = act.title + '，誰能到？';
      note = '寧寧會親口問阿嬤、幫大家收「去 / 沒空」；過了那天卡片會自動收進記錄簿';
    }
    card.innerHTML = '<div class="qc-kicker"><svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg>' +
      (act.kind === 'event' ? '揪一攤 · ' + act.title : '邀請已送出 · ' + act.title) +
      '<span class="qc-days">' + chip + '</span></div>' +
      '<div class="qc-goal">' + goal + '</div>' +
      '<div class="qc-num">' + note + '</div>';
    if (act.kind === 'quiz' && act.status !== 'done') { card.style.cursor = 'pointer'; card.addEventListener('click', () => startQuiz(act, card)); }
    list.parentNode.insertBefore(card, list);
  }
  if ($('#startChalBtn')) $('#startChalBtn').addEventListener('click', () => {
    const type = document.querySelector('.chal-type.active');
    const kind = type ? (type.dataset.kind || 'walk') : 'walk';
    const ons = $$('#inviteList .invite-item.on');
    const names = ons.map(x => (x.querySelector('.iv-name')?.childNodes[0]?.textContent || '').trim()).filter(Boolean);
    if (!names.length) { toast('先選至少一位家人一起'); return; }
    const act = { id: Date.now(), kind, names };
    if (kind === 'walk') {
      act.goal = +(($('#walkGoal') && $('#walkGoal').value) || 30000);
      act.days = +((document.querySelector('#walkDays .mchip.on') || {}).dataset || {}).d || 7;
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
    const acts = loadActs(); acts.push(act); saveActs(acts);
    closeChal();
    renderActCard(act);
    hint(kind === 'event' ? '好，寧寧幫你問大家——誰能到、誰沒空，回覆齊了告訴你。' : '好，邀請發出去了——寧寧會親口問阿嬤，等大家答應就開始。');
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
        pushFamilyFeed('「' + a.title + '」結束了——那天的紀錄收進<b>家庭記錄簿</b>了');
      } else { keep.push(a); renderActCard(a); }
    });
    if (keep.length !== acts.length) saveActs(keep);
  })();
  if (chalModal) chalModal.addEventListener('click', e => { if (e.target === chalModal) closeChal(); });
  // 邀請勾選 → 依人數+能力動態算目標
  const inviteList = $('#inviteList');
  function recalcGoal() {
    const ons = $$('#inviteList .invite-item.on');
    if ($('#goalN')) $('#goalN').textContent = ons.length;
    if ($('#goalSum')) $('#goalSum').textContent = (+(($('#walkGoal') && $('#walkGoal').value) || 30000)).toLocaleString();
  }
  if (inviteList) inviteList.addEventListener('click', e => { const it = e.target.closest('.invite-item'); if (it) { it.classList.toggle('on'); recalcGoal(); } });
  // 挑戰類型選擇
  const CHAL_SUBS = { quiz: ['用說的就能玩', '手機作答', '手機作答', '手機作答'], event: ['寧寧親口問她', '回覆 去/沒空', '回覆 去/沒空', '回覆 去/沒空'] };
  function applyChalKind(kind) {
    $$('#inviteList .invite-item').forEach((it, i) => {
      const sub = it.querySelector('.iv-sub');
      if (!sub) return;
      if (kind === 'walk') { sub.style.display = 'none'; }
      else { sub.style.display = ''; sub.textContent = (CHAL_SUBS[kind] || [])[i] || ''; }
    });
    if ($('#walkFields')) $('#walkFields').style.display = kind === 'walk' ? '' : 'none';
    if ($('#quizFields')) $('#quizFields').style.display = kind === 'quiz' ? '' : 'none';
    if ($('#eventFields')) $('#eventFields').style.display = kind === 'event' ? '' : 'none';
    const gb = document.querySelector('.goal-box');
    if (gb) gb.style.display = kind === 'walk' ? '' : 'none';
  }
  $$('.chal-type').forEach(b => b.addEventListener('click', () => {
    $$('.chal-type').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    applyChalKind(b.dataset.kind || 'walk');
  }));
  applyChalKind('walk');
  // 拉桿連動
  if ($('#walkGoal')) $('#walkGoal').addEventListener('input', () => {
    if ($('#walkGoalVal')) $('#walkGoalVal').textContent = (+$('#walkGoal').value).toLocaleString() + ' 步';
    recalcGoal();
  });
  if ($('#quizN')) $('#quizN').addEventListener('input', () => {
    if ($('#quizNVal')) $('#quizNVal').textContent = $('#quizN').value + ' 題';
  });
  // 日期／時段／期間 點選（單選）
  ['#walkDays', '#evDayChips', '#evTimeChips'].forEach(id => {
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
  if ($('#historyEntry')) $('#historyEntry').addEventListener('click', () => $('#historyModal').classList.add('show'));
  if ($('#historyClose')) $('#historyClose').addEventListener('click', () => $('#historyModal').classList.remove('show'));
  if ($('#historyModal')) $('#historyModal').addEventListener('click', e => {
    if (e.target === $('#historyModal')) { $('#historyModal').classList.remove('show'); return; }
    const row = e.target.closest('.hist-row');
    if (row) toast(row.classList.contains('dim') ? '正式版點開就是當月整理——示範先看 6 月這行' : '6 月整理好了——完整月報之後接引擎');
  });

  // 機智問答（示範題庫；正式版由寧寧出題、語音作答）
  const QUIZ_BANK = [
    { q: '一般建議大人每天走多少步，比較有活力？', opts: ['500 步', '2,000 步', '7,000 步左右', '50,000 步'], a: 2 },
    { q: '下面哪一個是台灣的傳統節日？', opts: ['感恩節', '端午節', '萬聖節', '復活節'], a: 1 },
    { q: '睡前做哪件事，通常比較好睡？', opts: ['喝濃茶', '滑手機', '聽輕音樂', '吃宵夜'], a: 2 },
    { q: '「一暝大一寸」說的是誰？', opts: ['小嬰兒', '大樹', '月亮', '麵團'], a: 0 },
    { q: '夏天出門，哪件事最重要？', opts: ['多喝水', '穿厚外套', '戴毛帽', '正中午曬太陽'], a: 0 },
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
    $('#quizOpts').innerHTML = item.opts.map((o, k) => '<button type="button" class="quiz-opt" data-k="' + k + '">' + o + '</button>').join('');
  }
  function finishQuiz() {
    const st = quizState;
    $('#quizProgress').textContent = '完成！';
    $('#quizQ').textContent = '';
    $('#quizOpts').innerHTML = '<div class="quiz-score">答對 ' + st.score + ' / ' + st.n + ' 題</div>' +
      '<p class="modal-sub" style="text-align:center">寧寧會找 ' + st.act.names.join('、') + ' 來作答——都答完就看排名</p>' +
      '<button class="modal-btn" id="quizCloseBtn">好</button>';
    $('#quizCloseBtn').addEventListener('click', () => $('#quizModal').classList.remove('show'));
    const note = st.card && st.card.querySelector('.qc-num');
    if (note) note.textContent = '你答對 ' + st.score + '/' + st.n + '——等 ' + st.act.names.join('、') + ' 作答完看排名';
    const acts2 = loadActs();
    const rec = acts2.find(a => a.id === st.act.id);
    if (rec) { rec.status = 'done'; rec.score = st.score; rec.doneISO = isoOf(new Date()); saveActs(acts2); }
    pushFamilyFeed('<b>你</b>完成了機智問答，答對 ' + st.score + '/' + st.n + ' 題——等大家玩完看排名');
  }
  if ($('#quizOpts')) $('#quizOpts').addEventListener('click', e => {
    const btn = e.target.closest('.quiz-opt');
    if (!btn || !quizState) return;
    const item = QUIZ_BANK[quizState.i];
    const k = +btn.dataset.k;
    [...$('#quizOpts').children].forEach((b2, idx) => {
      if (idx === item.a) b2.classList.add('good');
      else if (idx === k) b2.classList.add('bad');
      b2.disabled = true;
    });
    if (k === item.a) quizState.score++;
    setTimeout(() => { quizState.i++; if (quizState.i >= quizState.n) finishQuiz(); else renderQuizStep(); }, 700);
  });
  if ($('#quizModal')) $('#quizModal').addEventListener('click', e => { if (e.target === $('#quizModal')) $('#quizModal').classList.remove('show'); });

  // 家庭記錄簿
  if ($('#bookBtn')) $('#bookBtn').addEventListener('click', () => { $('#viewAll').classList.remove('active'); $('#viewPerson').classList.remove('active'); $('#viewBook').classList.add('active'); });
  if ($('#bookBack')) $('#bookBack').addEventListener('click', () => { $('#viewBook').classList.remove('active'); $('#viewAll').classList.add('active'); });

  // 聊聊：日常語音陪聊 · [ENGINE] 正式版換中文（台灣）/英文即時語音 + 反射腦
  const SR2 = window.SpeechRecognition || window.webkitSpeechRecognition;
  let chatRec = null, chatOn = false;
  const CHAT_RULES = [
    [/(藥.*(怎麼吃|幾顆|停|加量|減量))|劑量|(可以吃.*藥)/, '藥怎麼吃、吃幾顆，我不能幫你決定——這要聽醫生或藥師的喔。要不要我幫你記下來，回診時問醫生？'],
    [/痛|痠|不舒服|頭暈/, '聽到你不太舒服，我有點擔心。先坐下歇會兒，需要的話我幫你通知美華。'],
    [/累|睡不|失眠/, '辛苦了，累就歇著、不用硬撐，我在這陪你。'],
    [/孫|想.*他|想.*她|寂寞|一個人/, '想家人了是吧？要不要我提醒他們今晚打給你？'],
    [/吃|飯|餓|藥/, '好，吃飯吃藥都別忘了，到時間我會叫你。'],
    [/天氣|冷|熱|下雨/, '記得隨天氣加減衣服，別著涼了。'],
    [/謝|你真好|感謝/, '不用謝，陪著你是我最想做的事。'],
  ];
  function chatReply(t) { for (const [re, r] of CHAT_RULES) if (re.test(t.toLowerCase())) return r; return '我聽見了，你慢慢說，我都在。'; }
  async function chatHandle(t) {
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
  if (chatMic) chatMic.addEventListener('click', async () => {
    if (!SR2) {
      if (chatOn && mediaRec) { mediaRec.stop(); return; }
      await startVoiceCapture();
      return;
    }
    if (chatOn) { chatRec && chatRec.stop(); return; }
    chatRec = new SR2(); chatRec.lang = 'zh-TW'; chatRec.interimResults = false;
    chatRec.onstart = () => { chatOn = true; chatMic.classList.add('recording'); setFaceState('listening'); setCallHint('我在聽'); };
    chatRec.onresult = e => chatHandle(e.results[0][0].transcript);
    chatRec.onend = () => { chatOn = false; chatMic.classList.remove('recording'); if ($('#chat') && $('#chat').dataset.state === 'listening') setFaceState('idle'); };
    chatRec.onerror = chatRec.onend;
    chatRec.start();
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
