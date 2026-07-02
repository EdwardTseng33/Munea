/* Munea 沐寧 — 原型互動
 * 落實 Claude Design「沐寧 沐寧 配色」+ Elfie 融入（安心存摺 / 今天一起完成 / 家人互動）
 * 標 [ENGINE] 處正式版接 castle-voice-engine（中文〔台灣〕優先、英文第二 + 三顆腦 + 擬真 avatar；台語先不承諾）。 */

const $  = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

const OVERLAYS = ['med', 'chat', 'connect'];
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
  const fimg = $('#faceImg'); if (fimg) fimg.src = fullSrc;
  $$('.bc-avatar img').forEach(i => { i.src = homeSrc; });
  $$('#avatarPick .avo').forEach(o => o.classList.toggle('on', o.dataset.ava === currentAvatarId));
  avatarRuntime.setCharacter(display, currentAvatarId);
  renderAiDiagnostics();
}
function setCompanionName(name) {
  companionDisplayName = (name || '').slice(0, 12);
  companionNameTouched = companionDisplayName.trim().length > 0;
  persistCompanionProfile();
  syncCompanionUI();
  saveCompanionProfileToBackend();
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
async function enterChat() {
  startCallTimer();
  setCaption('接通了，直接說話就可以', '想到什麼就說，寧寧聽得到');
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
    if (r.audio) playB64(r.audio); else say(r.reply);
    faceSpeak(r.reply);
  } else {
    const fallback = '我在這裡，今天過得好嗎？想聊什麼都可以。';
    setCallHint('直接說，我在這裡');
    faceSpeak(fallback);
  }
}

function completeChatSession(reason = 'ended') {
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
  $$('.screen').forEach(s => s.classList.toggle('active', s.id === id));
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
  const h = now.getHours();
  const wd = ['日','一','二','三','四','五','六'][now.getDay()];
  const meta = $('#metaDate');
  if (meta) meta.textContent = `${now.getMonth() + 1}/${now.getDate()} 週${wd}`;
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
function say(text) {
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
  say(CHEERS[item.dataset.task] || '做得很好。');
}

function init() {
  syncCompanionUI();
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
    say('好，記下來了，連續六天，你真棒。');
    showView('home');
  });
  if ($('#medSnooze')) $('#medSnooze').addEventListener('click', () => showView('home'));

  // 連接裝置（狀態頁資料條 / 設定裝置區 → 串接三方裝置引導）
  if ($('#srcStrip')) $('#srcStrip').addEventListener('click', () => showView('connect'));
  if ($('#setDevices')) $('#setDevices').addEventListener('click', () => showView('connect'));
  if ($('#setProfile')) $('#setProfile').addEventListener('click', () => say('這裡可以改頭像、名稱、對家人顯示的稱呼、年齡、所在地。'));
  if ($('#connectBack')) $('#connectBack').addEventListener('click', () => showView('status'));
  $$('#connect .cn-btn').forEach(b => b.addEventListener('click', () => {
    const on = b.classList.toggle('done');
    b.textContent = on ? '✓ 已連接' : (b.dataset.label || '連接');
    if (on) say('好，連上了，之後健康資料我會自動留意。');
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
    say(`好，寧寧會幫你轉達——你${b.dataset.react}。`);
    const who = document.getElementById('ptName')?.textContent || '家人';
    pushFamilyFeed(`<b>你</b>剛剛給${who}${b.dataset.react || '送上心意'}——寧寧下次聊天會親口告訴${who === '阿嬤' ? '她' : 'TA'}`);
  });

  // 全家健康圈：切換成員看健康
  function showFamPerson(p, rel, init, tint) {
    $('#viewAll').classList.remove('active');
    $('#viewPerson').classList.add('active');
    if ($('#ptName')) $('#ptName').textContent = p;
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
  if ($('#personBack')) $('#personBack').addEventListener('click', showFamAll);
  const famSwitch = $('#famSwitch');
  if (famSwitch) famSwitch.addEventListener('click', e => {
    const b = e.target.closest('.fam-switch-item'); if (!b) return;
    const p = b.dataset.person;
    if (p === 'all') showFamAll();
    else if (p === 'invite') say('好，我幫你發邀請給家人，加進來就能互相關心健康。');
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
  if (rep) rep.addEventListener('click', () => say('好，我把這個月的用藥和血壓整理成一張，回診給醫生看就清楚了。'));

  // 發起挑戰面板
  const chalModal = $('#chalModal');
  const closeChal = () => chalModal && chalModal.classList.remove('show');
  if ($('#newChalBtn')) $('#newChalBtn').addEventListener('click', () => chalModal && chalModal.classList.add('show'));
  if ($('#startChalBtn')) $('#startChalBtn').addEventListener('click', () => {
    const type = document.querySelector('.chal-type.active');
    const kind = type ? (type.dataset.kind || 'walk') : 'walk';
    const evName = $('#eventName') ? $('#eventName').value.trim() : '';
    const evDate = $('#eventDate') ? $('#eventDate').value.trim() : '';
    const typeName = kind === 'event' ? (evName || '家庭聚會') : (type ? type.textContent.trim() : '挑戰');
    const ons = $$('#inviteList .invite-item.on');
    const names = ons.map(x => (x.querySelector('.iv-name')?.childNodes[0]?.textContent || '').trim()).filter(Boolean);
    closeChal();
    const list = document.querySelector('#newChalBtn')?.closest('.pad')?.querySelector('.quest-card');
    if (list && names.length) {
      const card = document.createElement('div');
      card.className = 'quest-card pending';
      const kickerLabel = kind === 'event' ? ('揪一攤 · ' + typeName) : ('邀請已送出 · ' + typeName);
      const daysChip = kind === 'event' ? (evDate || '等回覆') : '等待回覆';
      const goal = kind === 'event' ? (typeName + '，誰能到？') : ('等 ' + names.join('、') + ' 答應就開始');
      const note = kind === 'event'
        ? '寧寧會親口問阿嬤、幫大家收「去 / 沒空」，回覆都到了會告訴你'
        : (kind === 'quiz' ? '寧寧當主持人；到齊 2 人就自動開局' : '寧寧會親口問阿嬤要不要一起；大家答應後自動開局');
      card.innerHTML = '<div class="qc-kicker"><svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg>' + kickerLabel +
        '<span class="qc-days">' + daysChip + '</span></div>' +
        '<div class="qc-goal">' + goal + '</div>' +
        '<div class="qc-num">' + note + '</div>';
      list.parentNode.insertBefore(card, list);
    }
    say(kind === 'event' ? '好，寧寧幫你問大家——誰能到、誰沒空，回覆齊了告訴你。' : '好，邀請發出去了——寧寧會親口問阿嬤，等大家答應就開始。');
  });
  if (chalModal) chalModal.addEventListener('click', e => { if (e.target === chalModal) closeChal(); });
  // 邀請勾選 → 依人數+能力動態算目標
  const inviteList = $('#inviteList');
  function recalcGoal() {
    const ons = $$('#inviteList .invite-item.on');
    const sum = ons.reduce((a, b) => a + (+b.dataset.step || 0), 0);
    if ($('#goalN')) $('#goalN').textContent = ons.length;
    if ($('#goalSum')) $('#goalSum').textContent = sum.toLocaleString();
  }
  if (inviteList) inviteList.addEventListener('click', e => { const it = e.target.closest('.invite-item'); if (it) { it.classList.toggle('on'); recalcGoal(); } });
  // 挑戰類型選擇
  const CHAL_UNITS = { walk: ['3,000 步', '8,000 步', '8,000 步', '6,000 步'], quiz: ['用說的就能玩', '手機作答', '手機作答', '手機作答'], event: ['寧寧親口問她', '回覆 去/沒空', '回覆 去/沒空', '回覆 去/沒空'] };
  $$('.chal-type').forEach(b => b.addEventListener('click', () => {
    $$('.chal-type').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    const kind = b.dataset.kind || 'walk';
    const units = CHAL_UNITS[kind] || [];
    $$('#inviteList .invite-item').forEach((it, i) => {
      const sub = it.querySelector('.iv-sub');
      if (sub && units[i]) sub.textContent = kind === 'walk' ? ('份額 ' + units[i] + '（依能力）') : units[i];
    });
    const ef = $('#eventFields');
    if (ef) ef.style.display = kind === 'event' ? '' : 'none';
    const gb = document.querySelector('.goal-box');
    if (gb) gb.style.display = kind === 'walk' ? '' : 'none';
  }));
  // 家庭記錄簿
  if ($('#bookBtn')) $('#bookBtn').addEventListener('click', () => { $('#viewAll').classList.remove('active'); $('#viewPerson').classList.remove('active'); $('#viewBook').classList.add('active'); });
  if ($('#bookBack')) $('#bookBack').addEventListener('click', () => { $('#viewBook').classList.remove('active'); $('#viewAll').classList.add('active'); });

  // 聊聊：日常語音陪聊 · [ENGINE] 正式版換中文（台灣）/英文即時語音 + 反射腦
  const SR2 = window.SpeechRecognition || window.webkitSpeechRecognition;
  let chatRec = null, chatOn = false;
  const CHAT_RULES = [
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
      if (r.audio) playB64(r.audio); else say(r.reply);
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
      say(rr);
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
  if ($('#chatEnd')) $('#chatEnd').addEventListener('click', () => { completeChatSession('user_ended'); chatOpened = false; showView('home'); });

  // 陪伴角色：使用者命名與模板分離
  const companionNameInput = $('#companionNameInput');
  if (companionNameInput) {
    companionNameInput.addEventListener('input', e => setCompanionName(e.target.value));
    companionNameInput.addEventListener('blur', () => {
      if (!companionDisplayName.trim()) companionDisplayName = templateFor().defaultName;
      companionNameTouched = companionDisplayName.trim().length > 0;
      persistCompanionProfile();
      syncCompanionUI();
      saveCompanionProfileToBackend();
      syncAccountBootstrap('create', { reason: 'companion_name_updated' });
    });
  }
  const avatarPick = $('#avatarPick');
  if (avatarPick) avatarPick.addEventListener('click', e => {
    const o = e.target.closest('.avo:not(.soon)'); if (!o) return;
    setCompanionTemplate(o.dataset.ava);
  });

  if ('speechSynthesis' in window) speechSynthesis.onvoiceschanged = () => {};
}
document.addEventListener('DOMContentLoaded', init);
