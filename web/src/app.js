/* Munea 沐寧 — 原型互動
 * 落實 Claude Design「沐寧 沐寧 配色」+ Elfie 融入（安心存摺 / 今天一起完成 / 家人互動）
 * 標 [ENGINE] 處正式版接 castle-voice-engine（中文〔台灣〕優先、英文第二 + 三顆腦 + 擬真 avatar；台語先不承諾）。 */

const $  = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const muneaLocale = () => (window.MuneaI18n ? window.MuneaI18n.current() : 'zh-TW');
const muneaPreferredLanguages = () => (window.MuneaI18n ? window.MuneaI18n.preferredLanguages() : ['zh-TW']);
const muneaT = (key, fallback) => (window.MuneaI18n ? window.MuneaI18n.t(key, null, fallback) : fallback);

const OVERLAYS = ['med', 'connect', 'chat'];
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
// 動物角色（咪咪/旺財）先下架（Edward 2026-07-09：擬真臉引擎做不了卡通動物）——選過的自動回「溫柔型」寧寧、不留半殘狀態
const REMOVED_AVATARS = new Set(['munea-2d-mimi', 'munea-2d-wangcai', 'munea-2d-xiaoyun', 'munea-2d-ayuan']);   // V1 只留兩位擬真真人（Edward 2026-07-10）
if (REMOVED_AVATARS.has(currentAvatarId)) {
  currentAvatarId = 'nening-real-female';
  savedCompanionProfile.templateId = currentAvatarId;
  if (['咪咪', '旺財', '小昀', '阿原'].indexOf((companionDisplayName || '').trim()) >= 0) { companionDisplayName = '寧寧'; companionNameTouched = false; }
}
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
      fimg.src = template.fullAsset || template.homeAsset || template.thumbAsset || ('avatars/' + avatarId + '.png');
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
  // 真語音通話的嘴型：跟著她「實際的聲音大小」動（有聲音才動嘴、停頓就合嘴）— Edward 7/9 六角色全 avatar
  startLiveViseme(getLevel) {
    this.stopMockViseme();
    if (this.mode !== AVATAR_ENGINE_MODES.TWO_D_VISEME) return;
    const shapes = ['open', 'wide', 'round', 'smile'];
    let i = 0;
    visemeTimer = setInterval(() => {
      const lv = Math.max(0, Math.min(1, getLevel ? (getLevel() || 0) : 0));
      if (lv > 0.05) { i = (i + 1) % shapes.length; this.setViseme(shapes[i]); }
      else this.setViseme('rest');
    }, 110);
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
function setCallHint(text, busy) {
  const cap = $('#chatCaption');
  if (cap) { cap.textContent = text; cap.classList.toggle('cap-busy', !!busy); }
}
// 等待中按鈕：加轉圈、鎖點擊（Edward 7/8：Loading 要有動態，不然像當機）
function setBtnBusy(b, text) {
  if (!b) return;
  if (!b.dataset.idleText) b.dataset.idleText = b.textContent;
  b.disabled = true; b.classList.add('busy-spin');
  if (text) b.textContent = text;
}
function clearBtnBusy(b, text) {
  if (!b) return;
  b.disabled = false; b.classList.remove('busy-spin');
  b.textContent = text || b.dataset.idleText || b.textContent;
  delete b.dataset.idleText;
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
  // 薄門通行碼：管家腦雲端開門後靠它擋陌生流量（App 自動帶、用戶無感；本機沒設門=帶了也無妨）
  try { if (typeof MUNEA_APP_KEY === 'string' && MUNEA_APP_KEY) headers['X-Munea-Key'] = MUNEA_APP_KEY; } catch (e) {}
  return headers;
}
async function companionProfileApi(action, profile) {
  if (isStaticPreview()) return null;
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), 2500);
  try {
    const r = await fetch(brainURL('/companion-profile'), {
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
    locale: muneaLocale(),
    timezone: 'Asia/Taipei',
    preferredLanguages: muneaPreferredLanguages(),
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
      const store = response.store || {};
      if (store.primaryCareRecipientId) storageSet('munea.cloudPersonId', store.primaryCareRecipientId);
      if (store.familyGroup && store.familyGroup.id) storageSet('munea.familyGroupId', store.familyGroup.id);
      if (response.activeCompanionProfile) applyCompanionProfile(response.activeCompanionProfile);
      trackProductEvent('onboarding_completed', {
        bootstrapReason: extra.reason || action,
        bootstrapBackend: response.backend && response.backend.provider ? response.backend.provider : 'json',
      });
      try { syncPullAll(); } catch (e) {}
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
  const homeSrc = thumbSrc;   // 首頁頭像＝選角色同一張臉、同一種取景（Edward 7/9：不再用另一張 hero 照）
  const fullSrc = t.fullAsset || homeSrc;
  const homeName = $('#companionHomeName'); if (homeName) homeName.textContent = display;
  const chatName = $('#chatName'); if (chatName) chatName.textContent = display;
  const settingName = $('#settingsCompanionName'); if (settingName) settingName.textContent = display;
  const settingLabel = $('#settingsTemplateLabel'); if (settingLabel) settingLabel.textContent = t.templateLabel;
  const settingImg = $('#settingsCompanionImg'); if (settingImg) settingImg.src = thumbSrc;
  const nameInput = $('#companionNameInput');
  if (nameInput && document.activeElement !== nameInput && nameInput.value !== display) nameInput.value = display;
  const fimg = $('#faceImg'); if (fimg) { fimg.src = fullSrc; fimg.classList.toggle('sq', !t.fullAsset); }
  $$('.bc-avatar img').forEach(i => { i.src = homeSrc; });
  $$('.obs-ava img').forEach(i => { i.src = thumbSrc; });   // 狀態頁「○○的觀察」頭像＝跟著選的角色臉（Edward 2026-07-09）
  $$('.cname').forEach(el => { el.textContent = display; });
  $$('#avatarPick .avo').forEach(o => o.classList.toggle('on', o.dataset.ava === currentAvatarId));
  avatarRuntime.setCharacter(display, currentAvatarId);
  renderCompanionGreeting();
  // 在聊聊頁換角色：待機動態跟著換人（通話中不動）
  try {
    const chatActive = document.getElementById('chat') && document.getElementById('chat').classList.contains('active');
    if (chatActive && typeof FaceIdle !== 'undefined' && (typeof callConnected === 'undefined' || !callConnected)) FaceIdle.start();
  } catch (e) {}
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
  // 名字規則：只有「用戶自己取過的名字」才保留；名字若等於任一角色的預設名＝沒真的取過 → 跟著新角色走
  const defaults = Object.values(CompanionProfile.templates || {}).map(x => x.defaultName);
  const isCustom = companionNameTouched && defaults.indexOf((companionDisplayName || '').trim()) === -1;
  if (!isCustom) { companionDisplayName = t.defaultName; companionNameTouched = false; }
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
const BRAIN_PATIENCE = { '/chat': 30000, '/butler/post-turn': 45000, '/voice-session': 12000 };
// 管家腦雲端正式住址（台灣機房）——打包後的手機沒有「同一棟樓」可打相對路徑，一定要絕對網址
// 否則家人同步/邀請/資料權利/回饋全打空氣（7/9 上線體檢 B2 抓到的重傷）
const BRAIN_URL_DEFAULT = 'https://munea-brain-staging-491603544409.asia-east1.run.app';
// 判斷「是不是打包後的原生 App」：不是 http/https 開頭（capacitor:// file://）或有 Capacitor 殼＝真機
function isPackagedApp() {
  try {
    if (window.Capacitor && (window.Capacitor.isNativePlatform ? window.Capacitor.isNativePlatform() : true)) return true;
    return !/^https?:$/.test(location.protocol);
  } catch (e) { return false; }
}
// 引擎住址：①設過 munea.brainUrl 優先 ②真機沒設→走雲端正式 ③一般網頁（本機/區網有引擎同源）→相對路徑照舊
function brainURL(path) {
  try {
    const b = localStorage.getItem('munea.brainUrl');
    if (b) return b.replace(/\/$/, '') + path;
    if (b === '' ) return path;                 // 明確設空字串＝強制走同源（開發用）
    if (isPackagedApp()) return BRAIN_URL_DEFAULT + path;
    return path;
  } catch (e) { return path; }
}
async function brainPost(url, body) {
  if (isStaticPreview()) return null;
  // 加超時護欄：語音腦連不上時，不卡死畫面（§6.5 降級鐵律：對話不斷、老實退回）
  // 等待分級：聊天回話給足 30 秒（畫面有「我想一下」思考態撐場）、記憶整理背景 45 秒、其餘 6 秒
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), BRAIN_PATIENCE[url] || 6000);
  try {
    const r = await fetch(brainURL(url), { method: 'POST', headers: await muneaAuthHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify(body), signal: ctrl.signal });
    if (!r.ok) return null;
    return await r.json();
  } catch (e) { return null; }
  finally { clearTimeout(to); }
}

async function refreshServerPlanEntitlement() {
  // The server is authoritative: this also reflects an expiry detected while
  // the app was closed, rather than preserving a stale local paid-plan badge.
  if (!isLoggedIn()) return null;
  const result = await brainPost('/entitlements', { action: 'load' });
  renderSubscriptionEndDate(result && result.billing && result.billing.subscription);
  const plan = result && result.billing && result.billing.activePlan;
  if (!['free', 'plus', 'pro'].includes(plan)) return result;
  try { localStorage.setItem('munea.plan', plan); } catch (e) {}
  try { renderPlanState(); renderFcRoster(); } catch (e) {}
  return result;
}

function renderSubscriptionEndDate(subscription) {
  const el = $('#setPlanRenewalDate');
  if (!el) return;
  const expiresAt = subscription && subscription.expiresAt;
  const expires = expiresAt ? new Date(expiresAt) : null;
  const active = subscription && subscription.status === 'active';
  if (!active || !expires || Number.isNaN(expires.getTime())) {
    el.hidden = true;
    el.textContent = '';
    return;
  }
  const date = new Intl.DateTimeFormat('zh-TW', {
    timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit'
  }).format(expires);
  el.textContent = '訂閱到期日：' + date;
  el.hidden = false;
}

function subscriptionSuccessMessage(plan, subscription) {
  const planLabel = ({ plus: 'Plus', pro: 'Pro' })[plan] || '你的';
  const expires = subscription && subscription.expiresAt ? new Date(subscription.expiresAt) : null;
  if (subscription && subscription.status === 'active' && expires && !Number.isNaN(expires.getTime())) {
    const date = new Intl.DateTimeFormat('zh-TW', {
      timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit'
    }).format(expires);
    return '謝謝你訂閱 ' + planLabel + '！方案已啟用；到期日 ' + date + ' 已顯示在設定。';
  }
  return '謝謝你訂閱 ' + planLabel + '！方案已啟用；到期日會顯示在設定的方案卡。';
}

async function routineRemindersPost(body) {
  if (isStaticPreview()) return null;
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), 6000);
  try {
    const r = await fetch(brainURL('/routine-reminders'), {
      method: 'POST',
      headers: await muneaAuthHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body || {}),
      signal: ctrl.signal
    });
    if (!r.ok) return null;
    return await r.json();
  } catch (e) { return null; }
  finally { clearTimeout(to); }
}
function stableReminderId(prefix, raw) {
  let h = 0;
  const s = String(raw || '');
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  return prefix + Math.abs(h).toString(36);
}
function splitReminderSlots(value) {
  return String(value || '').split('\u3001').map(x => x.trim()).filter(Boolean);
}
function medScheduleTimes(med) {
  return splitReminderSlots(med && med.time).map(label => {
    const def = (typeof MED_SLOT_DEF !== 'undefined' ? MED_SLOT_DEF : []).find(x => x[0] === label);
    return { label, time: def ? medSlotTime(def[1], def[2]) : '' };
  });
}
function ensureMedReminderId(med) {
  if (!med.id) med.id = stableReminderId('med_', [med.name, med.time, med.days, med.by].join('|'));
  return med.id;
}
function ensureVisitReminderId(visit) {
  if (!visit.id) visit.id = stableReminderId('visit_', [visit.title, visit.dateISO, visit.time].join('|'));
  return visit.id;
}
function syncMedicationReminder(med) {
  if (!med || !med.name) return;
  ensureMedReminderId(med);
  routineRemindersPost({
    action: 'save',
    reminder: {
      id: med.id,
      title: med.name,
      type: 'medication',
      status: 'active',
      schedule: {
        slotLabels: splitReminderSlots(med.time),
        times: medScheduleTimes(med),
        days: med.days || '\u9577\u671f',
        by: med.by || '',
        photo: med.photo || '',
        source: 'munea-web'
      }
    }
  });
}
function syncVisitReminder(visit) {
  if (!visit || !visit.dateISO) return;
  ensureVisitReminderId(visit);
  routineRemindersPost({
    action: 'save',
    reminder: {
      id: visit.id,
      title: visit.title || '\u56de\u8a3a',
      type: 'check_in',
      status: 'active',
      schedule: {
        date: visit.dateISO,
        time: visit.time || '',
        label: visit.label || '',
        source: 'munea-web'
      }
    }
  });
}
function archiveRoutineReminder(id) {
  if (!id) return;
  routineRemindersPost({ action: 'archive', id });
}
function reminderToLocalMed(reminder) {
  const schedule = reminder.schedule || {};
  const labels = Array.isArray(schedule.slotLabels) ? schedule.slotLabels : splitReminderSlots(schedule.slotLabels || '');
  const fallbackLabels = Array.isArray(schedule.times) ? schedule.times.map(x => x && x.label).filter(Boolean) : [];
  return {
    id: reminder.id,
    name: reminder.title || '\u85e5',
    time: (labels.length ? labels : fallbackLabels).join('\u3001'),
    days: schedule.days || schedule.repeat || '\u9577\u671f',
    by: schedule.by || '\u96f2\u7aef',
    photo: schedule.photo || ''
  };
}
function reminderToLocalVisit(reminder) {
  const schedule = reminder.schedule || {};
  return {
    id: reminder.id,
    title: reminder.title || '\u56de\u8a3a',
    dateISO: schedule.date || '',
    time: schedule.time || '',
    label: schedule.label || ''
  };
}
function mergeByReminderKey(primary, secondary, keyFn) {
  const seen = new Set();
  const out = [];
  [...(primary || []), ...(secondary || [])].forEach(item => {
    const key = keyFn(item);
    if (!key || seen.has(key)) return;
    seen.add(key);
    out.push(item);
  });
  return out;
}
async function refreshRoutineRemindersFromBackend() {
  const data = await routineRemindersPost({ action: 'list', status: 'active', limit: 200 });
  const reminders = data && Array.isArray(data.reminders) ? data.reminders : [];
  if (!reminders.length) return;
  const remoteMeds = reminders.filter(r => r && r.type === 'medication').map(reminderToLocalMed).filter(m => m.name && m.time);
  const remoteVisits = reminders.filter(r => r && r.type === 'check_in').map(reminderToLocalVisit).filter(v => v.dateISO);
  if (remoteMeds.length) {
    const merged = mergeByReminderKey(remoteMeds, loadMeds(), m => m.id || (m.name + '|' + m.time));
    try { localStorage.setItem('munea.meds', JSON.stringify(merged)); } catch (e) {}
    updateMedCount();
  }
  if (remoteVisits.length) {
    let existing = [];
    try { existing = JSON.parse(localStorage.getItem('munea.visits') || '[]') || []; } catch (e2) {}
    const merged = mergeByReminderKey(remoteVisits, existing, v => v.id || (v.title + '|' + v.dateISO + '|' + v.time));
    try { localStorage.setItem('munea.visits', JSON.stringify(merged)); } catch (e3) {}
    if (window.__muneaRefreshVisitRow) window.__muneaRefreshVisitRow();
    if (window.__muneaRenderDailyTasks) window.__muneaRenderDailyTasks();
  }
}
window.__muneaRoutineReminderSync = { refresh: refreshRoutineRemindersFromBackend, saveMed: syncMedicationReminder, saveVisit: syncVisitReminder };

// ===== 聊聊 AI 幫你把提醒設進 App（跟手動新增走同一份清單 + 同一套雲端/手機通知）· 2026-07-09 Edward =====
function aiVisitLabel(dateISO, time) {
  try {
    const d = new Date(dateISO + 'T00:00');
    const md = (d.getMonth() + 1) + '/' + d.getDate();
    const wd = ['日', '一', '二', '三', '四', '五', '六'][d.getDay()];
    let tstr = '';
    if (time && /^\d{1,2}:\d{2}$/.test(time)) {
      const p = time.split(':').map(Number), h = p[0], m = p[1];
      const ap = h < 12 ? '上午' : '下午', h12 = ((h + 11) % 12) + 1;
      tstr = ' ' + ap + ' ' + h12 + ':' + String(m).padStart(2, '0');
    }
    return md + '（' + wd + '）' + tstr;
  } catch (e) { return dateISO + (time ? ' ' + time : ''); }
}
function aiAddVisitReminder(a) {
  const title = (String((a && a.title) || '').trim()) || '回診';
  const dateISO = String((a && a.dateISO) || '').trim();
  const time = String((a && a.time) || '').trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dateISO)) return { ok: false };
  let arr = [];
  try { arr = JSON.parse(localStorage.getItem('munea.visits') || '[]') || []; } catch (e) {}
  if (!Array.isArray(arr)) arr = [];
  const label = aiVisitLabel(dateISO, time);
  const visit = { id: Date.now(), title, dateISO, time, label };
  arr.push(visit);
  try { localStorage.setItem('munea.visits', JSON.stringify(arr)); } catch (e) {}
  try { if (typeof syncPush === 'function') syncPush('visits', arr); } catch (e) {}
  try { syncVisitReminder(visit); } catch (e) {}
  try { if (window.MuneaNotify) window.MuneaNotify.sync(); } catch (e) {}
  try { if (window.__muneaRefreshVisitRow) window.__muneaRefreshVisitRow(); } catch (e) {}
  try { if (window.__muneaRenderDailyTasks) window.__muneaRenderDailyTasks(); } catch (e) {}
  return { ok: true, title, label };
}
function aiAddMedReminder(a) {
  const name = String((a && a.name) || '').trim();
  const SLOTS = ['早餐後', '午餐後', '晚餐後', '睡前'];
  let slots = (a && Array.isArray(a.slots)) ? a.slots.filter(s => SLOTS.indexOf(s) >= 0) : [];
  slots = [...new Set(slots)];
  if (!name || !slots.length) return { ok: false };
  const meds = (typeof loadMeds === 'function') ? loadMeds() : [];
  const med = { name, time: slots.join('、'), days: (a && a.days) || '長期', by: '', photo: '' };
  ensureMedReminderId(med);
  meds.push(med);
  try { localStorage.setItem('munea.meds', JSON.stringify(meds)); } catch (e) {}
  try { if (typeof syncPush === 'function') syncPush('meds', meds); } catch (e) {}
  try { syncMedicationReminder(med); } catch (e) {}
  try { if (typeof updateMedCount === 'function') updateMedCount(); } catch (e) {}
  try { if (typeof renderMedList === 'function') renderMedList(); } catch (e) {}
  try { if (window.MuneaNotify) window.MuneaNotify.sync(); } catch (e) {}
  return { ok: true, name, slots };
}
// 聊聊語音收到 AI 的「幫你做進 App」指令 → 執行 + 螢幕輕提示（寧寧的口頭確認由 AI 那頭講）
function handleVoiceAction(action, args) {
  args = args || {};
  if (action === 'set_clinic_reminder') {
    const r = aiAddVisitReminder({ title: args.title, dateISO: args.date, time: args.time });
    if (typeof toast === 'function') toast(r.ok ? ('看診提醒設好了：' + r.title + ' · ' + r.label) : '看診日期我沒抓到，你再說一次日期好嗎');
    return r;
  }
  if (action === 'set_medication_reminder') {
    const r = aiAddMedReminder({ name: args.name, slots: args.slots, days: args.days });
    if (typeof toast === 'function') toast(r.ok ? ('用藥提醒設好了：' + r.slots.join('、') + '吃「' + r.name + '」') : '要什麼時候吃我沒抓到，你再說一次好嗎');
    return r;
  }
  return { ok: false };
}
window.__muneaHandleVoiceAction = handleVoiceAction;

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
    if (!response && !postTurnReview._retried) {
      postTurnReview._retried = true;
      setTimeout(() => { postTurnReview().finally(() => { postTurnReview._retried = false; }); }, 10000);
    }
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
      locale: muneaLocale(),
      fallback: VOICE_PROVIDER_MODES.STT_CHAT_TTS,
      ...context,
    });
    this.session = session || {
      ok: false,
      provider: VOICE_PROVIDER_MODES.STATIC_FALLBACK,
      fallback: VOICE_PROVIDER_MODES.STT_CHAT_TTS,
      locale: muneaLocale(),
    };
    this.mode = this.session.provider || this.session.fallback || VOICE_PROVIDER_MODES.STT_CHAT_TTS;
    setLatestAiContext(this.session.aiContext, 'voice-session', this.session.relationshipState);
    this.setState('idle');
    return this.session;
  },
  async open(char) {
    if (!this.session) await this.connect({ char });
    return brainPost('/open', { char, locale: muneaLocale() });
  },
  async sendText({ history, char }) {
    this.setState('thinking');
    try {
      const response = await brainPost('/chat', { history, char, locale: muneaLocale(), companionProfile: savedCompanionProfile, userMood: (window.MM && window.MM.currentMood) ? window.MM.currentMood() : '', interests: loadInterests() });
      if (response) setLatestAiContext(response.aiContext, 'chat response', response.relationshipState);
      return response;
    } finally {
      this.setState('idle');
    }
  },
  async sendVoiceNote({ audio, mime, durationMs, char }) {
    this.setState('uploading');
    try {
      const response = await brainPost('/voice-note', { char, locale: muneaLocale(), audio, mime, durationMs, provider: this.mode });
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

// ===== 想聊的話題（興趣）：存本機、文字/語音聊天都帶給 AI 當開場方向＋接話素材 =====
const INTEREST_TOPICS = ['旅遊景點', '美食餐廳', '影劇戲劇', '新聞時事', '健康養生', '運動', '懷舊老歌', '園藝花草', '歷史故事', '寵物', '棋牌麻將', '天氣節氣'];
function loadInterests() {
  try { const a = JSON.parse(localStorage.getItem('munea.interests') || 'null'); return Array.isArray(a) ? a.filter(t => INTEREST_TOPICS.includes(t)).slice(0, 5) : []; }
  catch (e) { return []; }
}
function saveInterests(list) { try { localStorage.setItem('munea.interests', JSON.stringify((list || []).slice(0, 5))); } catch (e) {} }

// ===== 真即時語音（Gemini 3.1 Live）：MuneaVoiceProvider 的 live 模式 =====
// 架構：前端這支 → WebSocket 即時語音橋（engine/live_voice_server.py）。麥克風即時串流上去、聲音即時播回來、可打斷。
// 連哪裡：localStorage['munea.liveVoiceUrl']，沒設就走正式雲端（台灣機房 · 7/9 Edward 拍板正式上線推進）。
const LIVE_VOICE_URL_DEFAULT = 'wss://munea-voice-staging-491603544409.asia-east1.run.app';
// 薄門通行碼：App 自動帶、用戶無感；擋「拿到網址直接來撥」的陌生流量（本機引擎沒開門檢查、帶了也無妨）
const MUNEA_APP_KEY = 'mnk_03d3a1545a3c5215b924c162c54e83f2ecd059e5';
const CALL_CONTROL_URL_DEFAULT = '';
const CallControl = {
  active: null,
  pending: null,
  heartbeatTimer: null,
  cancelled: false,
  url() {
    try { return (localStorage.getItem('munea.callControlUrl') || CALL_CONTROL_URL_DEFAULT).replace(/\/$/, ''); }
    catch (e) { return CALL_CONTROL_URL_DEFAULT; }
  },
  async _headers() {
    const headers = await muneaAuthHeaders({ 'Content-Type': 'application/json' });
    delete headers['X-Munea-Key'];
    return headers;
  },
  async acquire(characterId) {
    const base = this.url();
    if (!base) throw new Error('call_control_not_configured');
    this.cancelled = false;
    const idempotencyKey = (window.crypto && window.crypto.randomUUID) ? window.crypto.randomUUID() : ('call-' + Date.now() + '-' + Math.random());
    while (!this.cancelled) {
      const response = await fetch(base + '/v1/calls', {
        method: 'POST',
        headers: await this._headers(),
        body: JSON.stringify({ character_id: characterId || 'default', idempotency_key: idempotencyKey }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error((result && result.detail) || ('call_control_http_' + response.status));
      if (result.status === 'connect') {
        this.pending = null;
        this.active = result;
        this._startHeartbeat();
        return result;
      }
      if (result.status === 'queued') {
        this.pending = { call_id: result.call_id, idempotency_key: idempotencyKey };
        const queue = result.queue || {};
        setCallHint('目前排第 ' + (queue.position || 1) + ' 位，正在準備通話席位…', true);
        await new Promise(resolve => setTimeout(resolve, 3000));
        continue;
      }
      const reason = result.reason || 'capacity_unavailable';
      throw new Error(reason);
    }
    throw new Error('call_cancelled');
  },
  async refreshToken() {
    if (!this.active) return null;
    const response = await fetch(this.url() + '/v1/calls/' + encodeURIComponent(this.active.call_id) + '/token', {
      method: 'POST', headers: await this._headers(),
      body: JSON.stringify({ lease_version: this.active.lease_version }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok || result.status !== 'connect') throw new Error('call_token_refresh_failed');
    this.active = Object.assign({}, this.active, result);
    return this.active;
  },
  _startHeartbeat() {
    clearInterval(this.heartbeatTimer);
    this.heartbeatTimer = setInterval(async () => {
      const lease = this.active; if (!lease) return;
      try {
        const response = await fetch(this.url() + '/v1/calls/' + encodeURIComponent(lease.call_id) + '/heartbeat', {
          method: 'POST', headers: await this._headers(),
          body: JSON.stringify({ lease_version: lease.lease_version, event_id: 'app-heartbeat-' + Date.now(), component: 'app' }),
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok || result.should_end) {
          try { LiveVoice.stop(); } catch (e) {}
          try { completeChatSession(result.reason || 'lease_ended'); } catch (e) {}
        }
      } catch (e) { /* 45s lease reaper is the final guard; one missed heartbeat is recoverable. */ }
    }, 15000);
  },
  async release(reason) {
    this.cancelled = true;
    clearInterval(this.heartbeatTimer); this.heartbeatTimer = null;
    const lease = this.active; const pending = this.pending;
    this.active = null; this.pending = null;
    try {
      if (lease) {
        await fetch(this.url() + '/v1/calls/' + encodeURIComponent(lease.call_id) + '/release', {
          method: 'POST', headers: await this._headers(), keepalive: true,
          body: JSON.stringify({ lease_version: lease.lease_version, event_id: 'app-release-' + Date.now(), reason: reason || 'ended' }),
        });
      } else if (pending) {
        await fetch(this.url() + '/v1/calls/' + encodeURIComponent(pending.call_id) + '/cancel', {
          method: 'POST', headers: await this._headers(), keepalive: true,
        });
      }
    } catch (e) { /* Voice/Avatar callbacks and lease TTL provide idempotent cleanup. */ }
  },
};
function getLiveVoiceUrl() {
  if (CallControl.active && CallControl.active.voice) return CallControl.active.voice.url || '';
  try { const u = localStorage.getItem('munea.liveVoiceUrl'); if (u !== null) return u; } catch (e) {}
  return LIVE_VOICE_URL_DEFAULT;
}
// ===== 雲端寧寧擬真臉（快照秒醒 · 7/9 定案主力）=====
// 平常全睡不計費；進聊聊頁先「預醒」（8–10 秒）、按通話時臉多半已就緒。
// 連哪裡：localStorage['munea.avatarUrl']（設空字串=關閉臉）；預設＝正式雲端服務。
const AVATAR_URL_DEFAULT = 'https://edwardt0303--munea-nening-avatar-nening-web.modal.run';
// 新引擎 FlashHead（2026-07-11 Edward 拍板轉正主線；同日「直接接到app裡面」＝預設就走它）：
// localStorage['munea.faceEngine'] 只剩「手動退回舊引擎」用（設 'ditto'）；不設＝FlashHead。
// 門牌＝台灣 GLOWS RTX 6000 Ada 常駐主卡（640、3 席、2026-07-13 正式驗收）。
// ⚠ 這台機器 Release 重開後號碼會變；正式 App 下一版會改只認 Call Gateway。
// 備援1（美國 RunPod 4090 常駐）：https://a535qiaoru5bno-8188.proxy.runpod.net
// 備援2（Modal L4 試作版、產能貼預算會截斷）：https://edwardt0303--munea-flashhead-avatar-dev-flashhead-web.modal.run
const FLASHHEAD_URL_DEFAULT = 'https://tw-07.access.glows.ai:26969';
const RETIRED_FLASHHEAD_URLS = new Set([
  'https://tw-06.access.glows.ai:26718',
]);
function faceEngine() {
  try { return localStorage.getItem('munea.faceEngine') || 'flashhead'; } catch (e) { return 'flashhead'; }
}
// 擬真角色 → 雲端臉引擎代號（2026-07-11 Edward 拍板 launch 兩角色）：寧寧=擬真女=a05、阿宏=擬真男=a06。
// 其餘（2D 四角色）回空字串＝不接 flashhead 臉、走 2D 動畫。全身立繪底圖也照這個對應換。
const FLASHHEAD_CHAR_MAP = { '寧寧': 'a05', '阿宏': 'a06' };
function flashheadCharFor(backendChar) { try { return FLASHHEAD_CHAR_MAP[backendChar] || ''; } catch (e) { return ''; } }
function getAvatarUrl() {
  if (CallControl.active && CallControl.active.worker) return CallControl.active.worker.url || '';
  try {
    const raw = localStorage.getItem('munea.avatarUrl');
    if (raw !== null) {
      const u = raw.replace(/\/$/, '');
      // 舊版曾把臨時 GLOWS 門牌寫進 localStorage；升版後要自動回到新主卡。
      if (RETIRED_FLASHHEAD_URLS.has(u)) localStorage.removeItem('munea.avatarUrl');
      else if (u) return u;
    }
  } catch (e) {}
  return faceEngine() === 'flashhead' ? FLASHHEAD_URL_DEFAULT : AVATAR_URL_DEFAULT;
}
// FlashHead 全身合成開關（2026-07-11）：開＝把 512 活臉搬進 9:16 全身立繪的判斷框（羽化貼回、先鋒參數）；
// 關＝活臉搬回原位、恢復照片模式（Ditto/掛斷用）。搬家後補一次 play()——iOS 換位可能暫停。
function _fhFitStage(frame) {
  const host = frame && frame.parentElement;
  if (!host) return;
  const hostWidth = host.clientWidth;
  const hostHeight = host.clientHeight;
  if (!hostWidth || !hostHeight) return;
  const scale = Math.max(hostWidth / 1080, hostHeight / 1920);
  frame.style.width = Math.ceil(1080 * scale) + 'px';
  frame.style.height = Math.ceil(1920 * scale) + 'px';
}
function _fhComposite(on, vid) {
  try {
    const frame = document.getElementById('fhFrame');
    const ov = document.getElementById('fhOverlay');
    if (!frame || !ov || !vid) return;
    if (on) {
      frame.hidden = false;
      _fhFitStage(frame);
      if (!window.__muneaFhStageObserver && typeof ResizeObserver !== 'undefined') {
        window.__muneaFhStageObserver = new ResizeObserver(() => {
          if (!frame.hidden) _fhFitStage(frame);
        });
        window.__muneaFhStageObserver.observe(frame.parentElement);
      }
      const _bg = document.getElementById('fhBg');   // 全身立繪底圖跟著角色換：擬真女 bg-a05、擬真男 bg-a06
      const _fc = flashheadCharFor(currentChar) || 'a05';
      if (_bg && _bg.getAttribute('src') !== 'flashhead/bg-' + _fc + '.png') _bg.src = 'flashhead/bg-' + _fc + '.png';
      // 模型與畫面都使用同一個原生正方形裁切，避免把人物長方形硬壓成 640x640。
      // a05 y=190、a06 y=209，來源均為 1080x1920；高度由 CSS aspect-ratio 固定為正方形。
      const _box = (_fc === 'a06') ? { top: '10.885417%' } : { top: '9.895833%' };
      ov.style.top = _box.top;
      ov.style.height = '';
      if (vid.parentElement !== ov) { ov.appendChild(vid); try { const p = vid.play(); if (p && p.catch) p.catch(() => {}); } catch (e) {} }
      vid.style.objectFit = ''; vid.style.background = '';
    } else {
      frame.hidden = true;
      const bg = document.querySelector('#chat .face-bg');
      if (bg && vid.parentElement !== bg) { bg.insertBefore(vid, document.getElementById('faceAud')); }
    }
  } catch (e) {}
}
// （2026-07-11 施工圖①：方案B「伺服器直送雲端臉」整套已拔除——7/10 退役死碼、聲音上行只走客戶端自己送這一條。）
// 同線收聲（2026-07-11 · 治「聲音先出、臉慢 3-5 秒」根因＝聲音和影像走兩條線）：
// 開＝App 從臉的那條線多收一軌聲音、從那裡播（跟影像天生同步、免手動猜 faceSyncMs）。
// 預設關＝現役零影響；上行照舊走「手機轉送」（Avatar.feed 一寸不動、不碰 7/10 那顆方案B 雷）。
// 保底：同線 3 秒沒出聲 → 自動退回本地播放（防「有臉沒聲」，比慢半拍更糟）。
function faceSameLineOn() {
  try {
    const v = localStorage.getItem('munea.faceSameLine');
    if (v !== null) return v === '1';                 // 手動設定最優先（=0 可在 FlashHead 模式下關同線）
    return faceEngine() === 'flashhead';              // FlashHead 模式預設開同線（它天生兩軌同線）
  } catch (e) { return false; }
}
// 單一真相：「她現在正在出聲嗎」——所有喇叭出口（本地播放/臉那條線）都在這裡認，統一 0.015 門檻＋400ms 餘韻。
// 以後新增任何聲音出口只改這一個函式（v5.4.24 教訓：4 處各自判斷=bug 再生產線）。
function speechActive() {
  try {
    const now = performance.now();
    const face = (window.MuneaAvatar && window.MuneaAvatar._faceAudLevel) || 0;
    const queued = (typeof LiveVoice !== 'undefined' && LiveVoice._playoutUntil && now < LiveVoice._playoutUntil);
    if ((typeof LiveVoice !== 'undefined' && LiveVoice.speaking) || queued || face > 0.015) window.__muneaSpeechTs = now;
    return !!(window.__muneaSpeechTs && (now - window.__muneaSpeechTs) < 400);
  } catch (e) { return false; }
}
const Avatar = {
  pc: null, ws: null, on: false, _waking: false, warm: false, _wakeGen: 0,
  _session: '', _lastError: '',
  _videoReady: false, _feedReady: false, _readyNotified: false,
  _notifyReady() {
    if (this._readyNotified || !this._videoReady || !this._feedReady) return;
    this._readyNotified = true;
    this._diagNote('影像+聲音上行都就緒');
    if (typeof window.__muneaOnFaceReady === 'function') window.__muneaOnFaceReady();
  },
  _diag(msg) {  // 診斷小窗（設定 munea.debug=1 才顯示）：手機上排查「臉沒動」用
    try {
      if (localStorage.getItem('munea.debug') !== '1') return;
      const el = document.getElementById('avatarDiagnostics');
      if (el) { el.hidden = false; el.textContent = '臉: ' + msg; }
    } catch (e) {}
  },
  // 黑盒子：記整串同線聲音事件（帶時間），失敗時自動跳出來讓 Edward 截圖抓真兇（2026-07-12）
  _diagNote(msg, force) {
    try {
      if (!Avatar._diagTrail) Avatar._diagTrail = [];
      const t0 = Avatar._callT0 || Date.now();
      const el = ((Date.now() - t0) / 1000).toFixed(1);
      Avatar._diagTrail.push(el + 's ' + msg);
      if (Avatar._diagTrail.length > 10) Avatar._diagTrail.shift();
      const on = force || (function () { try { return localStorage.getItem('munea.debug') === '1'; } catch (e) { return false; } })();
      if (on) {
        const d = document.getElementById('avatarDiagnostics');
        if (d) { d.hidden = false; d.style.whiteSpace = 'pre-line'; d.style.maxHeight = '40vh'; d.style.overflow = 'auto'; d.textContent = '聲音診斷:\n' + Avatar._diagTrail.join('\n'); }
      }
    } catch (e) {}
  },
  // 進聊聊頁就把顯卡叫醒（Edward 2026-07-09 方案二）：連續探健康到「醒了」為止（涵蓋 8-10 秒冷啟），
  // warm=true 後按通話臉就近乎即到。只在聊聊頁探、離頁就停（不空燒顯卡）。
  wake() {
    const u = getAvatarUrl(); if (!u) { this.warm = false; return; }
    if (this._waking) return;
    this._waking = true; this.warm = false;
    const gen = ++this._wakeGen;
    const onChat = () => { const c = document.getElementById('chat'); return c && c.classList.contains('active'); };
    const ping = () => fetch(u + '/health?key=' + encodeURIComponent(MUNEA_APP_KEY), { mode: 'cors' })
      .then(r => (r && r.ok) ? r.json() : null).catch(() => null);
    const poll = tries => {
      if (gen !== this._wakeGen) return;                 // 換角色/重進頁 → 舊輪作廢
      ping().then(j => {
        if (gen !== this._wakeGen) return;
        if (j && j.ok) { this.warm = true; this._waking = false; this._diag('顯卡就緒'); return; }  // 醒了、就緒
        if (tries > 0 && onChat()) { this._diag('喚醒顯卡中…'); setTimeout(() => poll(tries - 1), 1500); }
        else { this._waking = false; }                   // 離頁或等太久 → 停（按通話時 start 會再喚醒）
      });
    };
    poll(14);   // 最多約 21 秒（冷啟 8-10s 綽綽有餘）
  },
  async start() {
    const u = getAvatarUrl(); if (!u) return false;
    const vid = document.getElementById('faceVid'); if (!vid) return false;
    this._lastError = ''; this._session = '';
    this._videoReady = false; this._feedReady = false; this._readyNotified = false;
    try {
      // 連線路線（7/9 手機實測補強）：家用網路直連即可；手機行動網路（5G/4G）常要走「中繼站」轉一手
      // 中繼＝公開測試中繼（正式上線換自家帳號的中繼、一行換）；munea.avatarRelay=1 可強制全走中繼（診斷用）
      const legacyIceServers = [
        { urls: 'stun:stun.l.google.com:19302' },
        // 自架可靠中繼站（GCP coturn · 34.81.102.52 · 2026-07-10 Edward 選 B、已實測能轉接）——手機行動網路優先走這台、穩
        { urls: ['turn:34.81.102.52:3478?transport=udp', 'turn:34.81.102.52:3478?transport=tcp'],
          username: 'muneaturn', credential: 'munea-turn-a7k2q' },
        // 443 偽裝門（2026-07-11 治「第一通線路 failed」）：走大家都不擋的 443 端口——雲端側開門後生效、開之前這兩條只是白試一下無害
        { urls: ['turn:34.81.102.52:443?transport=tcp', 'turn:34.81.102.52:443?transport=udp'],
          username: 'muneaturn', credential: 'munea-turn-a7k2q' },
        // 免費公用中繼＝備援（自架的萬一掛了還有得用）
        { urls: ['turn:openrelay.metered.ca:80', 'turn:openrelay.metered.ca:443', 'turn:openrelay.metered.ca:443?transport=tcp'],
          username: 'openrelayproject', credential: 'openrelayproject' },
      ];
      const leaseIceServers = CallControl.active && CallControl.active.ice_servers;
      const iceServers = Array.isArray(leaseIceServers) && leaseIceServers.length ? leaseIceServers : legacyIceServers;
      let forceRelay = false;
      try { forceRelay = localStorage.getItem('munea.avatarRelay') === '1'; } catch (e) {}
      this.pc = new RTCPeerConnection(forceRelay ? { iceServers, iceTransportPolicy: 'relay' } : { iceServers });
      this._diag('連線中（中繼' + (forceRelay ? '·強制' : '·備援') + '）');
      this.pc.addTransceiver('video', { direction: 'recvonly' });
      const _sameLine = faceSameLineOn();
      if (_sameLine) this.pc.addTransceiver('audio', { direction: 'recvonly' });   // 同線：臉那條線多收一軌聲音（跟影像同步）
      this.pc.ontrack = e => {
        // 同線＝先鋒真機驗證的做法：一個播放器帶兩軌（影像+聲音同一條 stream）——聲音跟畫面天生綁死、
        // iOS 手勢關卡也只闖一次。faceAud 降級為音量儀表專用（閉麥/沉默計時）、永遠靜音不出聲（防雙聲）。
        if (_sameLine && e.track && e.track.kind === 'audio') {
          this._attachFaceAudio(e.track);
          try { this._faceAudReceiver = e.receiver; } catch (er) {}
          try {
            const _sid = (e.streams && e.streams[0] && e.streams[0].id || '').slice(-4);
            Avatar._diagNote('聲音軌到 str=' + _sid + ' en=' + e.track.enabled + ' mu=' + e.track.muted);
          } catch (er) {}
          const _fa2 = document.getElementById('faceAud'); if (_fa2) _fa2.muted = true;
          return;
        }
        vid.srcObject = e.streams[0];
        if (_sameLine) {
          vid.muted = false;   // 聲音改由影像播放器出（跟先鋒頁同款）
          try { const _sid = (e.streams[0] && e.streams[0].id || '').slice(-4); Avatar._diagNote('影像軌到 str=' + _sid + ' 含音軌=' + (e.streams[0] ? e.streams[0].getAudioTracks().length : '?')); } catch (er) {}
          const _pv = vid.play();
          if (_pv && _pv.then) _pv.then(() => Avatar._diagNote('影音播放:成功')).catch((err) => {   // 被 iOS 擋（手勢斷鏈）→ 點畫面一下＝新手勢救回（先鋒 tap-to-play 的 App 版）
            Avatar._diagNote('影音播放:被擋(' + (err && err.name) + ')', true);
            try { setCallHint('聲音被擋住了，點一下畫面就好', true); } catch (e2) {}
            try {
              document.getElementById('chat').addEventListener('click', () => {
                vid.muted = false; const _p3 = vid.play(); if (_p3 && _p3.catch) _p3.catch(() => {});
                try { setCallHint(''); } catch (e3) {}
              }, { once: true });
            } catch (e4) {}
          });
        }
        if (faceEngine() === 'flashhead') { _fhComposite(true, vid); }   // 全身合成：512 活臉貼回 9:16 立繪判斷框（先鋒 7/11 參數）
        else { _fhComposite(false, vid); vid.style.objectFit = ''; vid.style.background = ''; }
        this._diag('影像到了');
      };
      this.pc.addEventListener('iceconnectionstatechange', () => {
        this._diag('線路 ' + this.pc.iceConnectionState);
        // 第一通線路 failed 自救（Edward 2026-07-11）：臉連線失敗＝自動重連一次（等於幫用戶掛掉重撥）——他實測第二通總是成功
        if (this.pc.iceConnectionState === 'failed' && this.on && Date.now() - (Avatar._lastRetry || 0) > 20000) {
          Avatar._lastRetry = Date.now();
          this._diag('線路失敗 → 自動重連一次');
          try { this.stop(); } catch (e2) {}
          setTimeout(() => {
            if (typeof callConnected !== 'undefined' && !callConnected && !callDialing) return;   // 已掛斷就不重連
            const resume = CallControl.active ? CallControl.refreshToken() : Promise.resolve();
            resume.then(() => Avatar.start()).then(ok => {
              if (!ok) return;
              try {   // 通話已開場的情況下臉遲到加入：補亮會動的臉那層（開場那步早跑過、這裡要自己補）
                const bg = document.querySelector('#chat .face-bg'); if (bg) bg.classList.add('livevid');
                FaceIdle.stop();
              } catch (e3) {}
            }).catch(() => {});
          }, 800);
        }
      });
      const o = await this.pc.createOffer(); await this.pc.setLocalDescription(o);
      await new Promise(res => {  // 等收集完連線候選再送（demo-live 同款）
        if (this.pc.iceGatheringState === 'complete') return res();
        const chk = () => { if (this.pc.iceGatheringState === 'complete') { this.pc.removeEventListener('icegatheringstatechange', chk); res(); } };
        this.pc.addEventListener('icegatheringstatechange', chk); setTimeout(res, 3000);
      });
      // 帶上目前選的角色（六角色 · 7/9）；角色不吃擬真引擎時服務會說不行 → 自動退回 2D 動畫
      // FlashHead 測試模式不帶角色（它目前只有測試臉、帶中文名會被拒連）——擬真女底圖入庫後再帶
      let _cq = '';
      try {
        if (faceEngine() === 'flashhead') {
          const _fc = flashheadCharFor(currentChar);   // 寧寧→a05、阿宏→a06；2D 角色回空＝不帶（服務用預設 a05）
          if (_fc) _cq = '&char=' + encodeURIComponent(_fc);
        } else if (typeof currentChar === 'string' && currentChar) {
          _cq = '&char=' + encodeURIComponent(currentChar);
        }
      } catch (e) {}
      const _leaseToken = CallControl.active && CallControl.active.call_token;
      const _avatarAuth = _leaseToken ? ('token=' + encodeURIComponent(_leaseToken)) : ('key=' + encodeURIComponent(MUNEA_APP_KEY));
      const r = await fetch(u + '/offer?' + _avatarAuth + _cq, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sdp: this.pc.localDescription.sdp, type: this.pc.localDescription.type }) });
      const a = await r.json();
      if (!r.ok || a.error) {
        this._lastError = a.code || ('http_' + r.status);
        throw new Error(a.error || 'avatar offer failed');
      }
      this._session = a.session || '';
      if (!this._session) { this._lastError = 'missing_session'; throw new Error('avatar session missing'); }
      await this.pc.setRemoteDescription(a);
      // 聲音上行：App 自己開一條 WS 把語音送去雲端臉（下面 feed()/reset() 會用到）
      this.ws = new WebSocket(u.replace(/^http/, 'ws') + '/audio?' + _avatarAuth + '&session=' + encodeURIComponent(this._session));
      this.ws.binaryType = 'arraybuffer';
      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error('avatar audio feed timeout')), 6000);
        this.ws.onopen = () => {
          clearTimeout(timer);
          this.on = true; this._feedReady = true;
          this._diagNote('聲音上行就緒');
          this._notifyReady();
          resolve();
        };
        this.ws.onerror = () => { clearTimeout(timer); reject(new Error('avatar audio feed failed')); };
      });
      return true;
    } catch (e) { this.stop(); return false; }
  },
  feed(buf) { try { if (this.on && this.ws && this.ws.readyState === 1) this.ws.send(buf); } catch (e) {} },
  reset() { try { if (this.on && this.ws && this.ws.readyState === 1) this.ws.send('reset'); } catch (e) {} },
  finish() { try { if (this.on && this.ws && this.ws.readyState === 1) this.ws.send('finish'); } catch (e) {} },
  // 同線：把臉那條線多帶的聲音軌接到 faceAud 播出，並持續量音量（給 LiveVoice 3 秒保底判斷用）
  _attachFaceAudio(track) {
    try {
      const aud = document.getElementById('faceAud'); if (!aud) return;
      const ms = new MediaStream([track]);
      aud.srcObject = ms; aud.muted = false;
      const p = aud.play(); if (p && p.catch) p.catch(() => {});
      this._diag('聲音到了（同線）');
      try {
        this._faceAudCtx = new AudioContext();
        const src = this._faceAudCtx.createMediaStreamSource(ms);
        const an = this._faceAudCtx.createAnalyser(); an.fftSize = 512;
        src.connect(an); this._faceAudAnalyser = an;   // 只接分析器、不接喇叭（聲音由 <audio> 播、這裡純量）
        const data = new Uint8Array(an.fftSize);
        this._faceAudMaxLevel = 0;
        const loop = () => {
          if (!this._faceAudAnalyser) return;
          an.getByteTimeDomainData(data);
          let s = 0; for (let i = 0; i < data.length; i++) { const v = (data[i] - 128) / 128; s += v * v; }
          const rms = Math.sqrt(s / data.length);
          this._faceAudLevel = rms;
          if (rms > (this._faceAudMaxLevel || 0)) this._faceAudMaxLevel = rms;
          this._faceAudRaf = requestAnimationFrame(loop);
        };
        loop();
      } catch (e) {}
    } catch (e) {}
  },
  stop() {
    this.on = false;
    this._videoReady = false; this._feedReady = false; this._readyNotified = false;
    try { if (this.ws) this.ws.close(); } catch (e) {}
    try { if (this.pc) this.pc.close(); } catch (e) {}
    this.ws = this.pc = null; this._session = '';
    const vid = document.getElementById('faceVid');
    if (vid) { try { vid.srcObject = null; } catch (e) {} }
    // 同線收聲一起收
    try { if (this._faceAudRaf) cancelAnimationFrame(this._faceAudRaf); } catch (e) {}
    this._faceAudAnalyser = null; this._faceAudRaf = 0; this._faceAudLevel = 0; this._faceAudMaxLevel = 0;
    try { if (this._faceAudCtx) this._faceAudCtx.close(); } catch (e) {}
    this._faceAudCtx = null;
    const aud = document.getElementById('faceAud'); if (aud) { try { aud.srcObject = null; } catch (e) {} }
    const bg = document.querySelector('#chat .face-bg'); if (bg) bg.classList.remove('livevid');
    _fhComposite(false, document.getElementById('faceVid'));   // 掛斷＝收全身合成、活臉歸位、照片回來
  },
};
window.MuneaAvatar = Avatar;
// 有真影格在播才蓋上照片（無縫接手；斷了自動退回照片）
document.addEventListener('DOMContentLoaded', () => {
  const vid = document.getElementById('faceVid');
  if (vid) vid.addEventListener('playing', () => {
    // 會動的臉線路通了＝「臉就緒」候選。⚠ 第一通冷開機時 'playing' 會在「真畫面到之前」就響，
    // 這時亮出來＝整屏粉紅（空畫面被手機渲染成粉色、Edward 2026-07-11 真機抓到）。
    // 修法：等到「真的解出第一格畫」（畫面有寬度＋播放時間有在走）才發就緒信號。
    const _confirmRealFrame = (tries) => {
      if (vid.videoWidth > 0 && vid.currentTime > 0.05) {
        Avatar._facePlaying = true;
        Avatar._videoReady = true;
        Avatar._notifyReady();
        return;
      }
      if (tries > 0) setTimeout(() => _confirmRealFrame(tries - 1), 250);   // 最多再等 25 秒（冷開機窗）——沒真畫面就不亮、待機動畫繼續頂著
    };
    _confirmRealFrame(100);
  });
});

const LiveVoice = {
  ws: null, ac: null, mic: null, proc: null, playCtx: null, playHead: 0, on: false,
  micLevel: 0, playLevel: 0, onCaption: null, onReady: null, micOpen: false, _openMicAfterGreet: false, _capBuf: '',
  prime() {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        this._micUnavailableReason = (!window.isSecureContext && !['localhost', '127.0.0.1'].includes(location.hostname))
          ? 'https_required'
          : 'media_unavailable';
        return false;
      }
      if (!this.playCtx || this.playCtx.state === 'closed') this.playCtx = new AudioContext({ sampleRate: 24000 });
      this.playHead = this.playCtx.currentTime;
      if (!this.ac || this.ac.state === 'closed') this.ac = new AudioContext();
      this._resumeAudio();
      if (!this._primeMicPromise) {
        this._primeMicPromise = navigator.mediaDevices.getUserMedia({ audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: false,
          channelCount: { ideal: 1 },
          sampleRate: { ideal: 48000 },
        } })
          .then(stream => ({ stream })).catch(error => ({ error }));
      }
      return true;
    } catch (e) { return false; }
  },
  _resumeAudio() {
    [this.ac, this.playCtx].forEach(ctx => {
      try { if (ctx && ctx.state === 'suspended') { const p = ctx.resume(); if (p && p.catch) p.catch(() => {}); } } catch (e) {}
    });
  },
  _setMicOpen(open) {
    this.micOpen = !!open;
    clearTimeout(this._micWatchT);
    if (!this.micOpen) return;
    this._resumeAudio();
    const sentAtOpen = this._micPackets || 0;
    this._micWatchT = setTimeout(() => {
      if (!this.micOpen || (this._micPackets || 0) > sentAtOpen) return;
      this._resumeAudio();
      try { trackProductEvent('voice_mic_stalled', { audioState: this.ac && this.ac.state, trackState: this.mic && this.mic.getAudioTracks()[0] && this.mic.getAudioTracks()[0].readyState }); } catch (e) {}
      setCallHint('收音還沒啟動，請點一下畫面');
      if (!this._micGestureBound) {
        this._micGestureBound = true;
        const recover = () => {
          this._micGestureBound = false;
          this._resumeAudio();
          setCallHint('我在聽，你說吧');
        };
        try { document.getElementById('chat').addEventListener('click', recover, { once: true }); } catch (e) {}
      }
    }, 1800);
  },
  greet() { try { if (this.ws && this.ws.readyState === 1) { this.ws.send(JSON.stringify({ type: 'greet' })); this._openMicAfterGreet = true; } } catch (e) {} },   // 請 AI 主動開口；招呼講完才開麥（乾淨第一句）
  nudge(level) { try { if (this.ws && this.ws.readyState === 1) this.ws.send(JSON.stringify({ type: 'nudge', level: level || 1 })); } catch (e) {} },   // 使用者一直沒講話 → 請 AI 溫柔提醒（省點 · Edward 2026-07-10）
  // 掛斷時把整通對話送去萃取長期記憶（讓「聊聊」講的也記得住 · Edward 2026-07-10）——跟文字聊天同一條記憶入口
  saveMemory() {
    try {
      const t = (this._transcript || []).filter(x => x && (x.text || '').trim());
      if (t.length < 2) return;   // 至少一來一往才值得記
      brainPost('/butler/post-turn', {
        history: t.slice(-24),
        char: currentChar,
        companionProfile: savedCompanionProfile,
        sessionId: activeChatSessionId,
        ...authAnalyticsContext(),
      });
    } catch (e) {}
  },
  _f2i(f) { const b = new Int16Array(f.length); for (let i = 0; i < f.length; i++) { let s = Math.max(-1, Math.min(1, f[i])); b[i] = s < 0 ? s * 0x8000 : s * 0x7fff; } return b; },
  _down(buf, inR, outR) { if (outR >= inR) return buf; const r = inR / outR, len = Math.round(buf.length / r), o = new Float32Array(len); let i = 0, j = 0; while (j < len) { const n = Math.round((j + 1) * r); let s = 0, c = 0; for (; i < n && i < buf.length; i++) { s += buf[i]; c++; } o[j++] = c ? s / c : 0; } return o; },
  _toSpeaking() { if (this.speaking) return; this.speaking = true; if (this.onSpeak) this.onSpeak(); },
  _playbackLeadSeconds() {
    // The first answer arrives while the iPhone audio route and Avatar WebRTC
    // jitter buffer are still settling. A 480 ms queue is intentionally used
    // for that first turn; later turns keep the existing low-latency behavior.
    const base = (this._playbackTurn || 0) <= 1 ? 0.48 : 0.22;
    return Math.min(0.72, base + Math.min(3, this._playbackUnderruns || 0) * 0.08);
  },
  _setFaceAudioMuted(muted) {
    ['faceAud', 'faceVid'].forEach(id => {
      try { const el = document.getElementById(id); if (el) el.muted = !!muted; } catch (e) {}
    });
  },
  async _finishSameLineWarmup() {
    if (!this._sameLineWarmupPending || !this.on) return;
    this._sameLineWarmupPending = false;
    let bytes = 0, audioLevel = -1, hasStats = false;
    try {
      const receiver = Avatar._faceAudReceiver;
      if (receiver && receiver.getStats) {
        const stats = await receiver.getStats();
        stats.forEach(r => {
          if (r.type !== 'inbound-rtp' || (r.kind !== 'audio' && r.mediaType !== 'audio')) return;
          hasStats = true;
          if (typeof r.bytesReceived === 'number') bytes = r.bytesReceived;
          if (typeof r.audioLevel === 'number') audioLevel = r.audioLevel;
        });
      }
    } catch (e) {}
    const stable = hasStats && (bytes > 12000 || audioLevel > 0.001);
    if (stable) {
      this._sameLineWarmup = false;
      this._setFaceAudioMuted(false);
      try { trackProductEvent('voice_sameline_warmup', { result: 'ready', bytes, audioLevel }); } catch (e) {}
    } else {
      // If iOS cannot prove the remote track is stable, keep the deterministic
      // local Web Audio path for this call instead of risking choppy speech.
      this._sameLineWarmup = false;
      this._sameLineFellBack = true;
      this._setFaceAudioMuted(true);
      try { trackProductEvent('voice_sameline_warmup', { result: 'local_fallback', bytes, audioLevel, hasStats }); } catch (e) {}
    }
  },
  _notePlayout(byteLength) {
    const now = performance.now();
    const useSameLine = this._sameLine && !this._sameLineWarmup && this._sameLineFellBack !== true;
    const delay = useSameLine ? 1100 : Math.round(this._playbackLeadSeconds() * 1000);
    if (!this._playoutUntil || this._playoutUntil < now) this._playoutUntil = now + delay;
    this._playoutUntil += (byteLength / (24000 * 2)) * 1000;
  },
  _toListening() {
    clearTimeout(this._speakTimer);
    const remain = Math.max(0, (this._playoutUntil || 0) - performance.now());
    if (remain > 80) {
      this._speakTimer = setTimeout(() => this._toListening(), remain + 120);
      return;
    }
    this.speaking = false; this.playLevel = 0;
    if (this._sameLineWarmupPending) this._finishSameLineWarmup();
    if (this._openMicAfterGreet) { this._setMicOpen(true); this._openMicAfterGreet = false; }
    if (this.onListen) this.onListen();
  },
  async start(onListen, onSpeak, onDrop) {
    let url = getLiveVoiceUrl();
    if (!url) return false;
    // 帶上目前選的角色（決定聲音＋個性；漏帶會永遠是寧寧——7/8 Edward 抓的蟲）
    try { if (typeof currentChar === 'string' && currentChar) url += (url.indexOf('?') >= 0 ? '&' : '?') + 'char=' + encodeURIComponent(currentChar); } catch (e) {}
    // 把使用者改過的名字帶給語音伺服器，讓 AI 知道自己現在叫什麼
    try { const nm = (typeof cname === 'function' ? cname() : ''); if (nm) url += (url.indexOf('?') >= 0 ? '&' : '?') + 'name=' + encodeURIComponent(nm); } catch (e) {}
    try { const _md = (window.MM && window.MM.currentMood) ? window.MM.currentMood() : ''; if (_md) url += (url.indexOf('?') >= 0 ? '&' : '?') + 'mood=' + encodeURIComponent(_md); } catch (e) {}
    // 帶上他挑的興趣話題，讓 AI 開場就聊得對味
    try { const _ts = loadInterests(); if (_ts.length) url += (url.indexOf('?') >= 0 ? '&' : '?') + 'topics=' + encodeURIComponent(_ts.join(',')); } catch (e) {}
    // AI 怎麼稱呼「你」＝個人資料的家人稱呼優先、沒填用名稱（7/9 Edward 拍板：不吃帳號）
    try {
      const _pp = JSON.parse(localStorage.getItem('munea.personProfile') || '{}');
      const _uad = ((_pp.nick || '').trim() || (_pp.name || '').trim());
      if (_uad) url += (url.indexOf('?') >= 0 ? '&' : '?') + 'user=' + encodeURIComponent(_uad);
      // 所在地（可到區）→ 讓寧寧推薦附近真的吃得到的餐廳、聊在地話題（不再亂猜位置 · 7/9 Edward）
      const _loc = (_pp.city || '').trim();
      if (_loc) url += (url.indexOf('?') >= 0 ? '&' : '?') + 'loc=' + encodeURIComponent(_loc);
    } catch (e) {}
    // 能力握手：告訴伺服器「這版 App 接得住 AI 幫你設提醒」→ 只有新版才拿到設提醒工具，舊版不會被假成功（2026-07-09 Edward）
    url += (url.indexOf('?') >= 0 ? '&' : '?') + 'cap_rem=1';
    // 熟識度：帶上「聊過幾通」→ 越熟開場越簡短、像老朋友（Edward 2026-07-10「隨熟識度思考語句量」）
    try { url += '&fam=' + (parseInt(localStorage.getItem('munea.callCount') || '0', 10) || 0); } catch (e) {}
    // Production uses a short-lived token bound to this call's Voice+Avatar lease.
    const _callToken = CallControl.active && CallControl.active.call_token;
    url += (url.indexOf('?') >= 0 ? '&' : '?') + (_callToken
      ? ('token=' + encodeURIComponent(_callToken))
      : ('key=' + encodeURIComponent(MUNEA_APP_KEY)));
    this.on = true;
    this.ready = false;   // 伺服器真的接上腦（Gemini session 開好）才會回 ready
    this.micOpen = false; this._openMicAfterGreet = false;   // 麥克風預設關；招呼講完才開（見 beginConversation / turn_complete）
    this._topicSaved = false; this._userBuf = '';   // 每通電話重新抓「你聊了什麼」
    this._transcript = []; this._userTurn = '';   // 每通電話重新累積聊天記錄（掛斷送去萃取長期記憶）
    this._playoutUntil = 0; this._newAvatarTurn = true; this._micPackets = 0;
    this._playbackTurn = 0; this._playbackUnderruns = 0; this._turnHasScheduledAudio = false;
    this.onListen = onListen; this.onSpeak = onSpeak; this.onDrop = onDrop; this.speaking = false; this._speakTimer = null;
    // iOS 只保證在使用者點下通話按鈕的同步呼叫鏈內允許啟動音訊。
    // 先建立並喚醒 AudioContext，也立刻要求麥克風；不要等 WebSocket onopen 才做。
    if (!this.prime()) { this.on = false; return false; }
    const micPromise = this._primeMicPromise;
    try { this.ws = new WebSocket(url); this.ws.binaryType = 'arraybuffer'; }
    catch (e) { this.on = false; return false; }
    return await new Promise(resolve => {
      let settled = false;
      const done = ok => { if (!settled) { settled = true; resolve(ok); } };
      this.ws.onopen = async () => {
        this._sameLine = faceSameLineOn(); this._sameLineFellBack = false; this._sameLineWatchStarted = false;   // 同線收聲狀態每通重置
        this._sameLineWarmup = this._sameLine; this._sameLineWarmupPending = false;
        if (this._sameLineWarmup) this._setFaceAudioMuted(true);
        try { clearTimeout(this._sameLineWatch); } catch (e) {}
        const micResult = await micPromise;
        this._primeMicPromise = null;
        if (!micResult.stream) { setCallHint('拿不到麥克風，請到設定允許'); try { this.ws.close(); } catch (e) {} done(false); return; }
        this.mic = micResult.stream;
        this._resumeAudio();
        const src = this.ac.createMediaStreamSource(this.mic);
        this.proc = this.ac.createScriptProcessor(2048, 1, 1);
        src.connect(this.proc); this.proc.connect(this.ac.destination);
        // 半雙工：她說話時暫停送麥克風→治好手機喇叭被麥克風收回去的回音，讓她每一輪都回你
        this.proc.onaudioprocess = e => {
          const inp = e.inputBuffer.getChannelData(0);
          if (!this.micOpen) { this.micLevel = 0; return; }        // 麥克風要等「真正開場」才開（撥通中/等臉那幾秒不收音，免得你的聲音在她招呼前一直灌進去→她一直「我聽見了」· Edward 2026-07-09）
          if (speechActive()) { this.micLevel = 0; return; }       // 她在出聲（本地播放或臉那條線）＝麥克風靜音——單一真相 speechActive()、防喇叭回音自問自答（Edward 7/11）
          let s = 0; for (let i = 0; i < inp.length; i++) s += inp[i] * inp[i];
          this.micLevel = Math.min(1, Math.sqrt(s / inp.length) * 8);   // 即時音量→收音波頻高度
          if (!this.ws || this.ws.readyState !== 1) return;
          const buf = this._f2i(this._down(inp, this.ac.sampleRate, 16000)).buffer;
          this.ws.send(buf); this._micPackets = (this._micPackets || 0) + 1;
        };
        if (this.onConnecting) this.onConnecting();   // 線接上了、腦還在開機 → 顯示「撥通中」載入動態
        done(true);
      };
      this.ws.onmessage = ev => {
        if (typeof ev.data === 'string') {
          try {
            const o = JSON.parse(ev.data);
            if (o.type === 'interrupted' && this.playCtx) {
              // 使用者插話：把還在播/已排隊的舊語音全部停掉，避免兩個聲音疊在一起（真人不會同時兩個聲音）
              (this._srcs || []).forEach(s => { try { s.stop(); } catch (e2) {} });
              this._srcs = []; this.playHead = this.playCtx.currentTime; this.playLevel = 0;
              Avatar.reset();                                    // 插話：臉也停下舊句、回待機
              this._playoutUntil = performance.now(); this._newAvatarTurn = true;
            }
            if (o.type === 'caption' && o.who === 'nening' && o.text) {   // 寧寧說的話→字幕逐字（累積成一句）
              this._capBuf = (this._capBuf || '') + o.text;
              if (this.onCaption) this.onCaption(this._capBuf);
            }
            if (o.type === 'ready') { this.ready = true; if (this.onReady) this.onReady(); this._toListening(); try { localStorage.setItem('munea.lastChatAt', String(Date.now())); } catch (e2) {} }   // 腦開機完成 → 語音就緒信號＋開麥；記下「聊過了」
            if (o.type === 'caption' && o.who === 'user' && o.text) {
              this._userTurn = (this._userTurn || '') + o.text;   // 累積「這輪你說的話」→ 掛斷時送去萃取長期記憶（讓聊聊講的也記得住 · Edward 2026-07-10）
              if (!this._topicSaved) {
                // 首頁「記得你說…」的在地記憶：抓這通電話你說的第一句話
                this._userBuf = (this._userBuf || '') + o.text;
                // 只存「乾淨、像一句話」的內容當首頁話題，擋語音辨識亂碼／英數雜訊（Edward 2026-07-12）
                const clean = this._userBuf.replace(/\s+/g, '');
                const cjk = (clean.match(/[一-龥]/g) || []).length;
                const looksClean = clean.length >= 5 && clean.length <= 16 && (cjk / clean.length) >= 0.6 && !/[a-zA-Z]{3,}/.test(clean) && (new Set(clean).size / clean.length) >= 0.5;
                if (looksClean) { try { localStorage.setItem('munea.lastTopic', clean.slice(0, 16)); } catch (e3) {} this._topicSaved = true; }
                else if (clean.length >= 24) { this._topicSaved = true; }   // 累積夠長仍不乾淨＝這通沒有適合話題、別硬塞亂碼
              }
            }
            if (o.type === 'turn_complete') {
              // 把這一輪（你說的＋她回的）存進聊天記錄 → 掛斷時送去萃取長期記憶
              try {
                if (!this._transcript) this._transcript = [];
                const ut = (this._userTurn || '').trim(), nt = (this._capBuf || '').trim();
                if (ut) this._transcript.push({ role: 'user', text: ut });
                if (nt) this._transcript.push({ role: 'assistant', text: nt });
                this._userTurn = '';
              } catch (eT) {}
              Avatar.finish();                    // WebSocket 順序保證尾包先到，再要求 Avatar 補算不足一整塊的句尾
              if (this._sameLineWarmup) this._sameLineWarmupPending = true;
              this._newAvatarTurn = true;
              this._toListening(); this._capBuf = '';
            }   // 她講完 → 換你講、麥克風重開、字幕緩衝清空
            if (o.type === 'action' && o.action) {   // AI 要「幫你做進 App」（設看診/用藥提醒）→ 執行
              try { if (window.__muneaHandleVoiceAction) window.__muneaHandleVoiceAction(o.action, o.args || {}); } catch (eAct) {}
            }
          } catch (e) {}
          return;
        }
        if (!this.playCtx) return;
        if (this._newAvatarTurn) {
          Avatar.reset();                         // 每輪新回答先清上一輪殘音／模型音訊記憶，避免句首帶到上一句尾巴
          this._newAvatarTurn = false;
          this._playoutUntil = 0;
          this._playbackTurn = (this._playbackTurn || 0) + 1;
          this._playbackUnderruns = 0;
          this._turnHasScheduledAudio = false;
        }
        this._notePlayout(ev.data.byteLength);     // Gemini 會快轉送完資料；用「音訊實際長度」算何時真的播完
        if (this._sameLineWarmup) this._setFaceAudioMuted(true);
        Avatar.feed(ev.data);                                      // 同一份聲音餵給雲端臉（對嘴）
        this._toSpeaking();                                        // 收到她的聲音 → 進入「她在說」
        const i16 = new Int16Array(ev.data), f = new Float32Array(i16.length);
        for (let k = 0; k < i16.length; k++) f[k] = i16[k] / 0x8000;
        let ps = 0; for (let k = 0; k < f.length; k++) ps += f[k] * f[k];
        this.playLevel = Math.min(1, Math.sqrt(ps / f.length) * 3.4);   // 即時音量→講話波頻高度
        // 同線模式：聲音改從 faceAud（臉那條線）出、這裡不本地排程播放（也不用等 faceSyncMs）。
        // 保底：頭一段講話若 3 秒內 faceAud 完全沒出聲 → 判定同線失效、之後這通改回本地播放（防「有臉沒聲」）。
        if (this._sameLine && !this._sameLineWarmup && this._sameLineFellBack !== true) {
          if (!this._sameLineWatchStarted) {
            this._sameLineWatchStarted = true;
            try { Avatar._faceAudMaxLevel = 0; } catch (e) {}
            this._sameLineWatch = setTimeout(async () => {
              let mx = 0; try { mx = Avatar._faceAudMaxLevel || 0; } catch (e) {}
              // iPhone 上 Web Audio 讀遠端串流會恆為 0（Safari 已知坑）→ 不能只信量表 mx。
              // 第二證人：連線「真的有沒有收到聲音位元組」（getStats，iPhone 讀得到）——有流量＝同線活著、別退回。
              let bytes = 0, alevel = -1, hasStats = false;
              try {
                const rcv = Avatar._faceAudReceiver;
                if (rcv && rcv.getStats) {
                  const st = await rcv.getStats();
                  st.forEach(r => { if (r.type === 'inbound-rtp' && (r.kind === 'audio' || r.mediaType === 'audio')) { hasStats = true; if (typeof r.bytesReceived === 'number') bytes = r.bytesReceived; if (typeof r.audioLevel === 'number') alevel = r.audioLevel; } });
                }
              } catch (e) {}
              const streamAlive = (bytes > 3000) || (alevel > 0.001);   // 連線收到夠多聲音位元組＝真的有聲在傳
              try { Avatar._diagNote('3秒查:量表=' + mx.toFixed(3) + ' 流量=' + bytes + 'B 音量=' + (alevel < 0 ? '無' : alevel.toFixed(3)) + (hasStats ? '' : '(無stats)')); } catch (e) {}
              try { trackProductEvent('sameline_check', { result: (mx < 0.015 && !streamAlive) ? 'fellback' : 'kept', mx: +(mx || 0).toFixed(3), bytes: bytes, audioLevel: alevel, hasStats: hasStats, trail: (Avatar._diagTrail || []).join(' | ') }); } catch (e) {}   // 回報後台=不用靠截圖也拿得到真機診斷（Codex 2026-07-12 建議）
              if (mx < 0.015 && !streamAlive) {
                this._sameLineFellBack = true;
                // 關鍵：退回本地播放的同時「把同線那軌靜音」——不然引擎晚點醒過來、兩邊一起出聲＝回答重疊（Edward 2026-07-11 真機抓到）
                try { const _fa = document.getElementById('faceAud'); if (_fa) _fa.muted = true; } catch (e) {}
                try { const _fv = document.getElementById('faceVid'); if (_fv) _fv.muted = true; } catch (e) {}   // 聲音改走影像播放器後（1.24.4）：退回時它也要閉嘴、同理防重疊
                try { Avatar._diagNote('判定真沒聲→退回本地(會慢)', true); } catch (e) {}
                try { localStorage.setItem('munea.sameLineFellBack', String(Date.now())); } catch (e) {}
              } else {
                try { Avatar._diagNote('同線活著→維持不退回' + (mx < 0.015 ? '(繞過iPhone坑)' : ''), mx < 0.015); } catch (e) {}
              }
            }, 3000);
          }
          this._toListening();                                    // 依實際應播完時間換手，不再用「資料停止到貨」誤判句尾
          return;                                                  // 不本地排程（聲音由 faceAud 出）
        }
        const b = this.playCtx.createBuffer(1, f.length, 24000); b.getChannelData(0).set(f);
        const s = this.playCtx.createBufferSource(); s.buffer = b; s.connect(this._avAnalyser || this.playCtx.destination);   // 延遲量測開時串一顆分析器（透明、不改聲音）
        const now = this.playCtx.currentTime;
        // 有會動的臉在跑時，聲音多等一下跟臉對齊（臉要往返雲端、比聲音慢約 1 秒）→ 聲音+嘴一起出、不再話先出嘴慢半拍（Edward 2026-07-10）。
        // 純語音不接臉＝維持 0.18 秒快起播。等多久可在手機上微調：localStorage['munea.faceSyncMs']（毫秒、預設 900、0~3000）。
        let _off = 0.18;
        try {
          if (typeof Avatar !== 'undefined' && Avatar.on) {
            // 舊水管拆除（1.24.6）：新引擎臉快 3 倍、退回本地播放也只等 0.2 秒＝寫死（連校時器寫進手機的舊毒值一併無視）；
            // 舊引擎照舊 0.9 秒可手調。不拆＝退回狀態聲音被推後最多 3 秒 → 「嘴跑在聲音前面」（Edward 7/11 症狀④機制源）。
            const _fh = (typeof faceEngine === 'function' && faceEngine() === 'flashhead');
            let ms = _fh ? 200 : parseInt(localStorage.getItem('munea.faceSyncMs') || '900', 10);
            if (isNaN(ms) || ms < 0 || ms > 3000) ms = _fh ? 200 : 900;
            _off = ms / 1000;
          }
        } catch (e) {}
        _off = Math.max(_off, this._playbackLeadSeconds());
        if (!this._turnHasScheduledAudio) {
          this.playHead = now + _off;
          this._turnHasScheduledAudio = true;
        } else if (this.playHead < now + 0.06) {
          this._playbackUnderruns = (this._playbackUnderruns || 0) + 1;
          this.playHead = now + this._playbackLeadSeconds();
          try { trackProductEvent('voice_playback_underrun', { turn: this._playbackTurn, count: this._playbackUnderruns }); } catch (e) {}
        }
        s.start(this.playHead); this.playHead += b.duration;
        // 記著正在播的語音，插話時才能一次停乾淨（不留尾巴跟新句疊音）
        if (!this._srcs) this._srcs = [];
        this._srcs.push(s); s.onended = () => { const k2 = this._srcs.indexOf(s); if (k2 >= 0) this._srcs.splice(k2, 1); };
        // 安全網：她若一段時間沒再吐聲音，視同講完、把麥克風打開（防 turn_complete 沒到就卡住）。
        // 放寬 0.9→2 秒：斷續破洞不再被誤判成「講完」把她攔腰切斷（Edward 2026-07-12）；真講完有 turn_complete 即時接手、不靠這條
        this._toListening();                                      // 本地備援同樣等排程音訊真的播完才開麥
      };
      this.ws.onclose = () => { const wasOpen = this.on; done(false); this.stop(); if (wasOpen && onDrop) onDrop(); };
      this.ws.onerror = () => { done(false); };
    });
  },
  stop() {
    this.on = false;
    this.ready = false;
    clearTimeout(this._speakTimer); clearTimeout(this._micWatchT); this._playoutUntil = 0; this._newAvatarTurn = true;
    this.micOpen = false; this._openMicAfterGreet = false;
    this._sameLineWarmup = false; this._sameLineWarmupPending = false;
    try { clearTimeout(this._sameLineWatch); } catch (e) {} this._sameLineWatchStarted = false;   // 同線保底計時器一起收
    try { Avatar.stop(); } catch (e) {}   // 掛斷＝臉一起收（所有掛斷路徑都走這裡）
    try { const c = document.getElementById('chat'); if (c && c.dataset.state === 'connecting') c.dataset.state = 'idle'; } catch (e) {}
    try { if (this.proc) this.proc.disconnect(); } catch (e) {}
    try { if (this.mic) this.mic.getTracks().forEach(t => t.stop()); } catch (e) {}
    const pendingMic = this._primeMicPromise; this._primeMicPromise = null;
    if (pendingMic) pendingMic.then(r => { try { if (r && r.stream) r.stream.getTracks().forEach(t => t.stop()); } catch (e) {} });
    try { if (this.ws) this.ws.close(); } catch (e) {}
    try { if (this.ac) this.ac.close(); } catch (e) {}
    try { if (this.playCtx) this.playCtx.close(); } catch (e) {}
    try { if (window.MuneaAvSyncMeter) MuneaAvSyncMeter.stop(); } catch (e) {}   // 延遲量測器一起收
    this._avAnalyser = null;                                                      // playCtx 關了→分析器作廢，下通重建
    this.ws = this.ac = this.mic = this.proc = this.playCtx = null;
  },
};
window.MuneaLiveVoice = LiveVoice;

// ── 聲↔臉 延遲量測器（Edward 2026-07-10：肉眼抓延遲太累、改用機器量）─────────────────
// 原理：同一個時鐘下，同時盯「播出去的聲音何時起」＋「臉的嘴巴那塊畫面何時開始動」，
// 兩個「開始」時間相減＝這句話的延遲秒數。左下角小字直接顯示（近幾句平均＋建議補償值）。
// 進階：munea.avSyncAuto=1 時，量到多少就自動把「聲音等臉」的時間補到剛好對齊（代價：她回話會慢一點）。
// 2026-07-11 施工圖②降級為隱藏除錯工具：munea.debug=1 才啟動，預設完全不跑（不建 canvas、不取像素、不顯示浮層）——
// 預設開著時它每幀取像素白燒長輩舊 iPhone CPU、螢光浮層又像 bug（Edward 抱怨的閃爍元凶）。
const AvSyncMeter = {
  on: false, _raf: 0, _video: null, _canvas: null, _ctx: null, _prev: null, _overlay: null,
  _audioHot: false, _videoHot: false, _pendA: false, _tA: 0, _samples: [], _lastTune: 0,
  start(videoEl) {
    if (this.on) return;
    try {
      if (localStorage.getItem('munea.debug') !== '1') return;   // debug-only：munea.debug=1 才啟動；預設不建 canvas、不取像素、不顯示浮層（2026-07-11 ②）
      this._video = videoEl || document.getElementById('faceVid');
      this._canvas = document.createElement('canvas'); this._canvas.width = 48; this._canvas.height = 48;
      this._ctx = this._canvas.getContext('2d', { willReadFrequently: true });
      this._overlay = document.createElement('div');
      this._overlay.style.cssText = 'position:fixed;left:10px;bottom:12px;z-index:99999;background:rgba(12,14,20,.78);color:#fff;font:600 12px/1.5 -apple-system,system-ui,sans-serif;padding:7px 10px;border-radius:10px;pointer-events:none;white-space:pre;letter-spacing:.2px;';
      this._overlay.textContent = '延遲量測：聽聲音、看嘴巴中…';
      document.body.appendChild(this._overlay);
      this._samples = []; this._prev = null; this._audioHot = this._videoHot = this._pendA = false;
      this.on = true; this._loop();
    } catch (e) {}
  },
  _ensureAnalyser() {
    if (LiveVoice._avAnalyser || !LiveVoice.playCtx) return LiveVoice._avAnalyser || null;
    try {
      const a = LiveVoice.playCtx.createAnalyser(); a.fftSize = 512; a.smoothingTimeConstant = 0.2;
      a.connect(LiveVoice.playCtx.destination); LiveVoice._avAnalyser = a;   // 之後的每段聲音都會串過它（透明、不改音）
    } catch (e) {}
    return LiveVoice._avAnalyser || null;
  },
  _audioRms() {
    const a = this._ensureAnalyser(); if (!a) return 0;
    const buf = new Uint8Array(a.fftSize); a.getByteTimeDomainData(buf);
    let s = 0; for (let i = 0; i < buf.length; i += 2) { const v = (buf[i] - 128) / 128; s += v * v; }
    return Math.sqrt(s / (buf.length / 2));   // 0~1 播出去的聲音能量
  },
  _mouthMotion() {
    const v = this._video; if (!v || !v.videoWidth) return 0;
    try {
      const sw = v.videoWidth, sh = v.videoHeight;
      this._ctx.drawImage(v, sw * 0.30, sh * 0.33, sw * 0.40, sh * 0.17, 0, 0, 48, 48);   // 嘴巴區＝高度33-50%（7/10 錄影逐格驗證：55%以下是胸口、之前盯錯位置才一直不出數字）
      const cur = this._ctx.getImageData(0, 0, 48, 48).data; let m = 0, n = 0;
      if (this._prev) { for (let i = 0; i < cur.length; i += 8) { m += Math.abs(cur[i] - this._prev[i]); n++; } }
      this._prev = cur;
      return n ? (m / n / 255) : 0;   // 0~1 嘴巴那塊畫面的變化量
    } catch (e) { return 0; }
  },
  _loop() {
    if (!this.on) return;
    const now = performance.now();
    const ar = this._audioRms(), mm = this._mouthMotion();
    if (ar > 0.045 && !this._audioHot) { this._audioHot = true; this._tA = now; this._pendA = true; }   // 聲音：靜→起
    else if (ar < 0.02) this._audioHot = false;
    if (mm > 0.028 && !this._videoHot) {                                                                  // 嘴巴：靜→動
      this._videoHot = true;
      if (this._pendA) {
        const d = (now - this._tA) / 1000;
        if (d > 0.05 && d < 5.5) { this._samples.push(d); if (this._samples.length > 6) this._samples.shift(); this._pendA = false; this._render(); this._maybeTune(); }
      }
    } else if (mm < 0.014) this._videoHot = false;
    this._raf = requestAnimationFrame(() => this._loop());
  },
  _avg() { const n = this._samples.length; return n ? this._samples.reduce((a, b) => a + b, 0) / n : 0; },
  _render() {
    if (!this._overlay) return;
    const n = this._samples.length, last = n ? this._samples[n - 1] : 0, avg = this._avg();
    const curW = parseInt(localStorage.getItem('munea.faceSyncMs') || '900', 10);
    const suggest = Math.max(0, Math.min(2800, Math.round(curW + avg * 1000)));   // 想對齊該把「聲音等臉」設多少
    const auto = ((localStorage.getItem('munea.avSyncAuto') || '1') === '1') ? '（自動補償中）' : '';   // 7/11 起預設開：量到差多少就自動補多少
    this._overlay.textContent = `臉比聲音慢 ${last.toFixed(1)}s（這句）\n近 ${n} 句平均 ${avg.toFixed(1)}s${auto}\n對齊建議：聲音等臉 ${suggest}ms`;
  },
  _maybeTune() {
    // 舊水管拆除（1.24.6）：新引擎＝臉聲同線原生對齊、退回也用寫死小等待——校時器只准看、不准動手
    //（它是舊雙管世界的拐杖，在新世界會把聲音越推越後＝嘴先動的機制源；量測顯示照舊、供機器人成績單用）
    try { if (typeof faceEngine === 'function' && faceEngine() === 'flashhead') return; } catch (e) {}
    if ((localStorage.getItem('munea.avSyncAuto') || '1') !== '1') return;   // 7/11 起預設開（Edward 拍板對齊為正解）；munea.avSyncAuto=0 可關
    if (this._samples.length < 3) return;
    const now = performance.now(); if (now - this._lastTune < 4000) return;   // 每 4 秒最多調一次、給它時間穩
    const sorted = this._samples.slice().sort((a, b) => a - b), med = sorted[Math.floor(sorted.length / 2)];
    const curW = parseInt(localStorage.getItem('munea.faceSyncMs') || '900', 10);
    const newW = Math.max(0, Math.min(2800, Math.round(curW + med * 1000)));   // D=臉lag−等待 → 等待+=D 一步對齊
    if (Math.abs(newW - curW) > 120) {
      try { localStorage.setItem('munea.faceSyncMs', String(newW)); } catch (e) {}
      this._lastTune = now; this._samples = [];   // 換了等待時間 → 清掉重量、看新的對齊結果
    }
  },
  stop() {
    this.on = false; if (this._raf) cancelAnimationFrame(this._raf);
    if (this._overlay) { try { this._overlay.remove(); } catch (e) {} this._overlay = null; }
    this._prev = null; this._samples = [];
  },
};
window.MuneaAvSyncMeter = AvSyncMeter;

// 聲波波頻：收音／講話都跟著「真實音量」跳；沒聲音就低伏收攏，不再是常亮的假 loading
const FaceWave = {
  bars: null, raf: 0, src: null, cur: 0,
  _init() { this.bars = Array.prototype.slice.call(document.querySelectorAll('.face-wave i')); },
  start(getLevel) {
    this.src = getLevel;                                     // 已在跑就只換來源（收音↔講話）
    if (!this.bars || !this.bars.length) this._init();
    if (this.raf) return;
    const loop = () => {
      const n = this.bars.length;
      const target = Math.max(0, Math.min(1, this.src ? (this.src() || 0) : 0));
      this.cur += (target - this.cur) * 0.35;                // 平滑起落，不抖
      const t = performance.now() / 1000;
      for (let i = 0; i < n; i++) {
        const shape = 1 - Math.abs(i - (n - 1) / 2) / n;     // 中間高、兩側低＝聲波形狀
        const wob = 0.5 + 0.5 * Math.sin(t * (5.2 + (i % 4) * 1.9) + i * 1.9);  // 每根有自己的節奏＝顆粒感（Edward 7/9）
        const h = 0.2 + this.cur * (0.3 + shape * 0.55 + wob * 0.65);
        this.bars[i].style.transform = 'scaleY(' + Math.min(1.8, h).toFixed(2) + ')';
      }
      this.raf = requestAnimationFrame(loop);
    };
    this.raf = requestAnimationFrame(loop);
  },
  stop() {
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = 0; this.src = null; this.cur = 0;
    if (this.bars) this.bars.forEach(b => { b.style.transform = 'scaleY(0.16)'; });
  },
};
window.MuneaFaceWave = FaceWave;

// 進聊聊頁：她像朋友一樣「主動先開口」（帶記憶＋今日狀態）
let callConnected = false;
let callDialing = false;
// 撥通中狀態：按鈕顯示「撥通中···」循環；真的接通（她開始聽/說）才變「結束通話」＋開始計時（Edward 7/9）
function setCallDialing(on) {
  callDialing = on;
  const b = $('#callToggle'); if (!b) return;
  b.classList.toggle('dialing', on);
  const lbl = $('#callToggleLabel');
  if (lbl) {
    if (on) lbl.innerHTML = '撥號中<span class="dial-dots"><i>·</i><i>·</i><i>·</i></span>';
    else lbl.textContent = callConnected ? '結束通話' : '開始通話';
  }
}
function setCallToggle(connected) {
  callConnected = connected;
  callDialing = false;
  const _b0 = $('#callToggle'); if (_b0) _b0.classList.remove('dialing');
  // 在線狀態：撥通前「未在線」（灰點）、撥通後「在線」（綠點呼吸）
  const fn = document.querySelector('.face-name');
  if (fn) { fn.classList.toggle('off', !connected); const st = fn.querySelector('.fn-status'); if (st) st.textContent = connected ? '在線' : '未在線'; }
  const b = $('#callToggle');
  if (!b) return;
  b.classList.toggle('start', !connected);
  b.classList.toggle('end', connected);
  const pts = document.querySelector('.hud-pill.pts');
  if (pts) pts.style.display = connected ? 'none' : '';
  const lbl = $('#callToggleLabel');
  if (lbl) lbl.textContent = connected ? '結束通話' : '開始通話';
}

// ===== 待機動態（Edward 7/9 供片）：進聊聊頁播「打招呼」一次 → 「待機」循環；按通話即停回靜態，交給語音＋雲端臉 =====
const FACE_MOTION = {
  'nening-real-female': { hello: 'avatars/motion/nening-hello.mp4', idles: ['avatars/motion/nening-idle.mp4'] },
  // 擬真男重新掛回（2026-07-11 Edward 給新影片、新長相）：撥號前用「打招呼→待機」影片、引擎已做交叉淡入不黑閃
  'companion-real-male': { hello: 'avatars/motion/ahong-hello.mp4', idles: ['avatars/motion/ahong-idle.mp4'] },
  'munea-2d-xiaoyun': { hello: 'avatars/motion/xiaoyun-hello.mp4', idles: ['avatars/motion/xiaoyun-idle.mp4'] },
  'munea-2d-ayuan': { hello: 'avatars/motion/ayuan-hello.mp4', idles: ['avatars/motion/ayuan-idle.mp4'] },
  'munea-2d-mimi': { hello: 'avatars/motion/mimi-hello.mp4', idles: ['avatars/motion/mimi-idle.mp4', 'avatars/motion/mimi-idle2.mp4'] },   // 咪咪有兩段待機（含舔鼻子）輪著播
  'munea-2d-wangcai': { hello: 'avatars/motion/wangcai-hello.mp4', idles: ['avatars/motion/wangcai-idle.mp4'] },
};
function currentFaceTemplate() {
  try {
    const P = window.MuneaCompanionProfile;
    const raw = (typeof currentAvatarId !== 'undefined' && currentAvatarId)
      ? currentAvatarId
      : (((P && P.loadProfile ? P.loadProfile() : null) || {}).templateId || '');
    return P && P.normalizeTemplateId ? P.normalizeTemplateId(raw) : (raw || 'nening-real-female');
  } catch (e) { return 'nening-real-female'; }
}
const FaceIdle = {
  // 輪播引擎：打招呼一次 → 多段待機輪流（咪咪有兩段）。兩支播放器輪班：下一段永遠先在底下備好、
  // 真的出畫面才交叉淡入，上一段停在最後一格墊著——任何換片點都沒有黑格、不閃頻（Edward 7/9）
  vA: null, vB: null, active: false, _gen: 0, _front: null, _back: null, _idles: null, _nextIdx: 0,
  _mk(suffix) {
    const img = document.getElementById('faceImg');
    if (!img || !img.parentElement) return null;
    const v = document.createElement('video');
    v.id = 'faceIdle' + suffix; v.muted = true; v.playsInline = true; v.setAttribute('playsinline', ''); v.preload = 'auto';
    v.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:0;transition:opacity .28s ease;pointer-events:none';
    img.insertAdjacentElement('afterend', v);   // 蓋在靜態照上、壓在雲端臉(faceVid)下
    v.onended = () => { if (FaceIdle.active && v === FaceIdle._front) FaceIdle._swap(); };
    return v;
  },
  ensure() {
    if (!this.vA) this.vA = this._mk('A');
    if (!this.vB) this.vB = this._mk('B');
    return this.vA && this.vB;
  },
  _preloadNext() {
    if (!this._idles || !this._idles.length) return;   // 只有打招呼片：播完停在最後一格
    // 把下一段待機片裝進待命的那支播放器（單段角色＝同一支片重複裝、換片點一樣淡接）
    const src = this._idles[this._nextIdx % this._idles.length];
    this._back.loop = false; this._back.style.opacity = '0'; this._back.src = src;
    try { this._back.load(); } catch (e) {}
  },
  _swap() {
    const gen = this._gen;
    const front = this._front, back = this._back;
    const cross = () => {
      if (gen !== this._gen) return;
      back.style.opacity = '1';                                                          // 新片淡入（舊片停最後一格墊著）
      setTimeout(() => { if (gen === this._gen) front.style.opacity = '0'; }, 200);      // 疊 0.2 秒再讓舊片淡出
      this._front = back; this._back = front;
      this._nextIdx++;
      setTimeout(() => { if (gen === this._gen) this._preloadNext(); }, 650);            // 等淡出完全結束才裝下一段（裝片會重置畫面、不能在交疊中做）
    };
    back.play().then(() => requestAnimationFrame(() => requestAnimationFrame(cross))).catch(cross);
  },
  start(tplId) {
    const m = FACE_MOTION[tplId || currentFaceTemplate()];
    if (!this.ensure()) return;
    if (!m) { this.stop(); return; }             // 沒動態素材的角色維持靜態圖
    const gen = ++this._gen;                     // 換角色/重進頁時作廢舊流程
    this.active = true;
    this._idles = m.idles || []; this._nextIdx = 0;
    this._front = this.vA; this._back = this.vB;
    const A = this._front;
    A.loop = false; A.src = m.hello;
    this._preloadNext();                         // 第一段待機先備好
    const showA = () => { if (gen === this._gen) A.style.opacity = '1'; A.removeEventListener('playing', showA); };
    A.addEventListener('playing', showA);
    A.play().catch(() => {
      // 被省電規則暫時擋下（例如分頁在背景）：半秒後再試一次，仍不行就維持靜態圖
      setTimeout(() => { if (this.active && gen === this._gen) A.play().catch(() => { if (gen === this._gen) this.stop(); }); }, 600);
    });
  },
  stop() {
    this.active = false; this._gen++; this._idles = null;
    [this.vA, this.vB].forEach(v => {
      if (!v) return;
      try { v.pause(); } catch (e) {}
      v.style.opacity = '0'; v.removeAttribute('src'); try { v.load(); } catch (e) {}
    });
  },
};

async function enterChat() {
  setCallToggle(false);
  const box = document.querySelector('.face-caption-box');
  if (box) box.style.display = 'none';
  setFaceState('idle');
  if (typeof callConnected === 'undefined' || !callConnected) FaceIdle.start();   // 待機動態輪播（通話中不搶）
}

async function openVoiceSession() {
  if (chatOpened) return;
  chatOpened = true;
  activeChatSessionId = makeSessionId('voice');
  activeChatStartedAt = Date.now();
  activeChatTurnCount = 0;
  setFaceState('idle');
  setCallHint(muneaT('voice.connecting', '正在連線...'));
  await prepareAvatarSession();
  trackProductEvent('voice_session_started', {
    locale: muneaLocale(),
    requestedAvatarMode: requestedAvatarMode(),
  });
  const r = await voiceProvider.open(currentChar);
  if (r && r.reply) {
    setCallHint('正在說話');
    chatHistory.push({ role: 'model', text: r.reply });
    if (r.audio) playB64(r.audio); else speakChat(r.reply);
    faceSpeak(r.reply);
  } else {
    const fallback = muneaT('voice.fallback', '我在這裡，今天過得好嗎？想聊什麼都可以。');
    setCallHint(muneaT('voice.ready', '直接說，我在這裡'));
    faceSpeak(fallback);
  }
}

function completeChatSession(reason = 'ended') {
  try { CallControl.release(reason); } catch (e) {}
  if (_callSec > 3) {
    const mins = Math.max(1, Math.round(_callSec / 60));
    POINTS.used = Math.min(POINTS.total, POINTS.used + mins * 1);
    pushWallet();
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
  // 掛斷 → 把這通聊聊的對話送去萃取長期記憶（讓聊聊講的也記得住 · Edward 2026-07-10）
  try { if (typeof LiveVoice !== 'undefined' && LiveVoice.saveMemory) LiveVoice.saveMemory(); } catch (e) {}
  activeChatSessionId = null;
  activeChatStartedAt = 0;
  activeChatTurnCount = 0;
}

function showView(id) {
  // 聊聊要登入才能用（7/9 Edward 拍板 A：免費 5 分鐘要綁帳號才守得住、不怕重裝重置）
  // 所有進聊聊的路都經過這個路口——訪客點聊聊＝先引導登入註冊、不進聊天頁
  if (id === 'chat' && !isLoggedIn()) {
    if (typeof openAuthSheet === 'function') openAuthSheet();
    if (typeof setAuthMessage === 'function') setAuthMessage('請先登入或註冊，就能和' + cname() + '聊聊；免費帳號會收到一次性 5 點，約 5 分鐘', 'ok');
    try { trackProductEvent('login_gate_shown', { feature: 'chat' }); } catch (e) {}
    return;
  }
  const t = $('#toast'); if (t) t.classList.remove('show');
  $$('.modal-mask.show').forEach(m => m.classList.remove('show'));
  if (id === 'status') {
    renderStatusCharts();
    const strip = $('#srcStrip');
    if (strip) strip.style.display = localStorage.getItem('munea.devicesOn') ? 'none' : '';
    // 底部「接上 Apple 健康」卡：還沒接才顯示；接上了就收起來（Edward 7/9）
    const cc = $('#stConnectCard');
    if (cc) cc.style.display = localStorage.getItem('munea.devicesOn') ? 'none' : '';
    const segBtns = document.querySelectorAll('#statusSeg .seg-btn');
    if (segBtns.length) {
      segBtns.forEach(x => x.classList.toggle('on', x.dataset.v === 'today'));
      const m = { today: $('#statusToday'), week: $('#statusWeek'), month: $('#statusMonth') };
      Object.entries(m).forEach(([k, el]) => { if (el) el.style.display = k === 'today' ? '' : 'none'; });
      if ($('#statusTitle')) $('#statusTitle').textContent = '今天的狀態';
    }
  }
  if (id === 'family') {
    try { syncPullAll(); } catch (e) {}   // 進家人頁先拉最新動態
    if (window.__muneaSweepActs) { try { window.__muneaSweepActs(); } catch (e) {} }   // 順手收掉到期的活動卡（不用重開 App）
    const va = $('#viewAll');
    if (va && !va.classList.contains('active')) {
      $$('#family .fam-view').forEach(v => v.classList.remove('active'));
      va.classList.add('active');
    }
  }
  $$('.screen').forEach(s => s.classList.toggle('active', s.id === id));
  if (window.__muneaApplyUserAvatar) window.__muneaApplyUserAvatar();
  setTimeout(refreshHscrollHints, 60); // 分頁切換後重算「右邊還有」提示
  const overlay = OVERLAYS.includes(id);
  $('#tabBar').classList.toggle('hidden', overlay);
  $$('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.view === id));
  const el = $('#' + id); if (el) el.scrollTop = 0;
  if (id === 'chat') { Avatar.wake(); enterChat(); }   // 進聊聊頁＝先預醒雲端臉（按通話時多半已就緒）
  else if (typeof FaceIdle !== 'undefined') FaceIdle.stop();   // 離開聊聊頁＝待機動態停、省電
}

// 登入把關（7/9 Edward 拍板）：聊聊＋家人連線類要登入·用到才問；solo（今日健康/心情/提醒）免登入
// 回 true=已登入可繼續；回 false=擋下並跳「先登入」提示（不是一開 App 就擋登入牆）
function isLoggedIn() { try { const st = authState(); return !!(st && st.status === 'signed-in'); } catch (e) { return false; } }
function requireLogin(reasonText, feature) {
  try {
    if (isLoggedIn()) return true;
    if (typeof openAuthSheet === 'function') openAuthSheet();
    if (typeof setAuthMessage === 'function') setAuthMessage(reasonText || '先用 Google 或 Apple 登入一下（30 秒就好）', 'ok');
    try { trackProductEvent('login_gate_shown', { feature: feature || 'family' }); } catch (e) {}
    return false;
  } catch (e) { return true; }   // 判斷出錯就不擋（不因把關 bug 卡死使用者）
}
function requireLoginForFamily(reasonText) { return requireLogin(reasonText, 'family'); }
// 登入後帳號卡標題顯示什麼（Edward 2026-07-14 問）：優先真名（Google／Apple 登入都會給），
// 沒名字就用 email 的 @ 前面那段，再沒有才退回「已登入」。
function authDisplayName(state) {
  if (!state) return '';
  if (state.name) return String(state.name).trim();
  if (state.email) return String(state.email).split('@')[0];
  return '';
}
// 帳號卡右上角「唯一」的身份標籤（Edward 2026-07-14：只留一顆、統一右上，不要兩顆）
// 開發測試帳號 → TEST；否則 FREE / PLUS / PRO
let _memBadgePlan = 'free';
function renderMemBadge(plan) {
  if (plan) _memBadgePlan = String(plan).toLowerCase();
  const mb = $('#memBadge');
  if (!mb) return;
  let dev = false;
  try { dev = !!authState().developerMode; } catch (e) {}
  const key = dev ? 'test' : _memBadgePlan;
  mb.textContent = dev ? 'TEST' : key.toUpperCase();
  mb.className = 'mem-badge ' + key;
}
function authState() {
  const auth = window.MuneaAuth;
  return auth && typeof auth.state === 'function' ? auth.state() : { status: 'guest' };
}
function localPersonAvatar() {
  try { return (JSON.parse(localStorage.getItem('munea.personProfile') || '{}')).avatar || ''; } catch (e) { return ''; }
}
function renderAuthAvatar(state = authState(), signedIn = state.status === 'signed-in') {
  const box = $('#authAvatar');
  const img = $('#authAvatarImg');
  if (!box || !img) return;
  const meta = state && state.user && state.user.user_metadata ? state.user.user_metadata : {};
  const accountPhoto = signedIn ? (state.avatarUrl || meta.avatar_url || meta.picture || meta.photo_url || '') : '';
  const uploadedPhoto = signedIn ? localPersonAvatar() : '';
  const source = accountPhoto || uploadedPhoto;
  box.classList.toggle('guest', !signedIn);
  box.classList.toggle('has-photo', !!source);
  if (!source) {
    img.hidden = true;
    img.removeAttribute('src');
    img.dataset.source = '';
    img.onerror = null;
    return;
  }
  img.hidden = false;
  img.dataset.source = accountPhoto ? 'account' : 'local';
  img.onerror = () => {
    if (img.dataset.source === 'account' && uploadedPhoto && uploadedPhoto !== img.src) {
      img.dataset.source = 'local';
      img.src = uploadedPhoto;
      return;
    }
    img.hidden = true;
    img.removeAttribute('src');
    box.classList.remove('has-photo');
  };
  img.src = source;
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
// 通用「下拉關閉」手勢：抓每個彈窗頂部的把手往下拖，過門檻就關、沒過就彈回（Edward 7/7：所有類似彈窗都要有）
function enableSheetDrag() {
  let active = null, startY = 0, dy = 0;
  const modalOf = m => m && m.querySelector('.modal');
  const move = clientY => {
    if (!active) return;
    dy = Math.max(0, clientY - startY);
    const m = modalOf(active); if (m) m.style.transform = 'translateY(' + dy + 'px)';
  };
  const end = () => {
    if (!active) return;
    const mask = active, m = modalOf(mask); active = null;
    if (m) {
      m.style.transition = 'transform .28s cubic-bezier(.22,.9,.32,1)';
      if (dy > 88) { m.style.transform = 'translateY(100%)'; setTimeout(() => { mask.classList.remove('show'); m.style.transform = ''; m.style.transition = ''; }, 250); }
      else { m.style.transform = ''; setTimeout(() => { if (m) m.style.transition = ''; }, 300); }
    }
    dy = 0;
  };
  document.querySelectorAll('.modal-mask').forEach(mask => {
    const grab = mask.querySelector('.modal-grab');
    if (!grab || grab.dataset.drag) return;
    grab.dataset.drag = '1';
    grab.style.touchAction = 'none';                 // 把手上不觸發捲動
    const down = clientY => { active = mask; startY = clientY; dy = 0; const m = modalOf(mask); if (m) m.style.transition = 'none'; };
    grab.addEventListener('touchstart', e => down(e.touches[0].clientY), { passive: true });
    grab.addEventListener('mousedown', e => { e.preventDefault(); down(e.clientY); });
  });
  window.addEventListener('touchmove', e => { if (active) { move(e.touches[0].clientY); if (e.cancelable) e.preventDefault(); } }, { passive: false });
  window.addEventListener('touchend', end);
  window.addEventListener('mousemove', e => { if (active) move(e.clientY); });
  window.addEventListener('mouseup', end);
}
function updateAuthUI() {
  // 7/9 正式化：示範假登入（陳秀英）拆除——畫面只反映真實登入狀態
  const state = authState();
  let signedIn = state.status === 'signed-in';
  renderAuthAvatar(state, signedIn);
  const card = $('#authCard');
  if (card) card.dataset.authState = signedIn ? 'signed-in' : 'guest';
  const status = $('#authStatusText');
  if (status) status.textContent = signedIn ? (authDisplayName(state) || '已登入') : '訪客模式';
  const email = $('#authEmailText');
  if (email) email.textContent = signedIn && state.email ? state.email : '';
  const signIn = $('#authSignInBtn');
  if (signIn) signIn.hidden = signedIn;
  const signOut = $('#authSignOutBtn');
  if (signOut) signOut.hidden = !signedIn;
  renderMemBadge();
  renderAiDiagnostics();
}
async function signInWithAuthProvider(provider) {
  // 7/9 正式化：沒設定好就老實說、不再假裝登入成功
  if (authState().configured === false) {
    setAuthMessage('登入服務還沒接上，請稍後再試', 'error');
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
    updateAuthUI();
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

// 首頁天氣：真的查（open-meteo 免費氣象站、不用鑰匙）——查得到才顯示、查不到整塊不出現，不擺假太陽
(function homeWeather() {
  const wrap = document.getElementById('homeWxWrap'), wx = document.getElementById('homeWx');
  if (!wrap || !wx) return;
  const CK = 'munea.wxCache';
  try { const c = JSON.parse(localStorage.getItem(CK) || 'null'); if (c && Date.now() - c.t < 1800000) { wx.textContent = c.text; wrap.style.display = ''; return; } } catch (e) {}
  function wtxt(code) {
    const M = [[0, '☀ 晴'], [1, '🌤 晴時多雲'], [2, '⛅ 多雲'], [3, '☁ 陰'], [45, '🌫 有霧'], [51, '🌦 毛毛雨'], [61, '🌧 有雨'], [71, '❄ 下雪'], [80, '🌧 陣雨'], [95, '⛈ 雷雨']];
    let t = '⛅ 多雲'; for (const [c, s] of M) if (code >= c) t = s; return t;
  }
  function ok(text) { wx.textContent = text; wrap.style.display = ''; try { localStorage.setItem(CK, JSON.stringify({ t: Date.now(), text })); } catch (e) {} }
  function byCoords(lat, lon) {
    return fetch('https://api.open-meteo.com/v1/forecast?latitude=' + lat + '&longitude=' + lon + '&current=temperature_2m,weather_code&timezone=auto')
      .then(r => r.json()).then(j => {
        const c = j && j.current;
        if (!c || typeof c.temperature_2m !== 'number') throw new Error('no-data');
        ok(wtxt(c.weather_code || 0) + ' ' + Math.round(c.temperature_2m) + '°');
      });
  }
  function byCity(city) {
    return fetch('https://geocoding-api.open-meteo.com/v1/search?count=' + 1 + '&language=' + encodeURIComponent(window.MuneaI18n ? window.MuneaI18n.weatherLanguage() : 'zh') + '&name=' + encodeURIComponent(city))
      .then(r => r.json()).then(j => {
        const g = j && j.results && j.results[0];
        if (!g) throw new Error('no-city');
        return byCoords(g.latitude, g.longitude);
      });
  }
  let city = '';
  try { const p = JSON.parse(localStorage.getItem('munea.personProfile') || 'null'); city = ((p && p.city) || '').trim(); } catch (e) {}
  // 7/9 隱私修正（送審前）：拿掉精確定位（GPS）備援，只用「個人資料」設定的縣市查天氣——沒設城市就整塊不顯示，不再問使用者要精確位置
  (city ? byCity(city) : Promise.reject(new Error('no-profile-city')))
    .catch(() => { /* 沒設所在地＝不顯示天氣，只留日期 */ });
})();

function renderCompanionGreeting(now = new Date()) {
  const h = now.getHours();
  const msg = $('#bcMsg');
  if (!msg) return;
  // 首頁招呼語的四個階段（Edward 7/9 拍板設計）：
  //   ① 還沒聊過（首次進來）→ 自我介紹＋邀請認識
  //   ② 聊過了、還沒抓到話題 → 「上次聊得很開心」＋時段邀請
  //   ③ 有記住的話題（目前＝上通電話你說的第一句；雲端記憶接上後換真記憶）→ 「記得你說…」
  //   ④ 之後每次聊天都會更新話題，這句會一直跟著你們的對話變
  const nm = (typeof cname === 'function' ? cname() : '寧寧');
  const lastAt = +(localStorage.getItem('munea.lastChatAt') || 0);
  // 顯示前再過濾一次：舊版可能已存過亂碼，不乾淨就當沒話題、退回乾淨招呼（Edward 2026-07-12）
  const _topicRaw = (localStorage.getItem('munea.lastTopic') || '').trim();
  const _tcjk = (_topicRaw.match(/[一-龥]/g) || []).length;
  const topic = (_topicRaw.length >= 5 && _topicRaw.length <= 16 && (_tcjk / _topicRaw.length) >= 0.6 && !/[a-zA-Z]{3,}/.test(_topicRaw) && (new Set(_topicRaw).size / _topicRaw.length) >= 0.5) ? _topicRaw : '';
  let ask = '來跟我聊聊今天？';
  if (h >= 18 || h < 5) ask = '睡前跟我聊聊今天？';
  else if (h >= 5 && h < 11) ask = '走走回來，說給我聽？';
  else if (h >= 14) ask = '傍晚散個步，回來跟我聊？';
  let line;
  if (!lastAt) line = '我是' + nm + '，來陪你說說話的——點下面，跟我認識一下？';
  else if (topic) line = '記得你說「' + topic + '」——' + ask;
  else line = '上次聊得很開心，我都記得你——' + ask;
  msg.textContent = line;
  const idleGreeting = $('#faceIdleHi');
  if (idleGreeting) idleGreeting.textContent = line;
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
  renderCompanionGreeting(now);

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
  if (big) big.textContent = k;
})();

function loadMeds() {
  // 沒設用藥就是空的——首頁不該有吃藥任務、用藥管理顯示空狀態（Edward 2026-07-07）
  try { return JSON.parse(localStorage.getItem('munea.meds')) || []; } catch (e) { return []; }
}
function updateMedCount() {
  const n = loadMeds().length + ' 種藥';
  const el = $('#medCountLabel');
  if (el) el.textContent = n;
  const el2 = $('#medCountSettings');
  if (el2) el2.textContent = n;
  renderPillTask();
  if (window.MuneaNotify) window.MuneaNotify.sync(); // 用藥變動 → 重排 App 關著也會響的提醒
}
const PILL_SLOT_ORDER = ['早餐後', '午餐後', '晚餐後', '睡前'];
function pillDateKey() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}
const WEEK_STEPS = [4200, 5100, 3600, 6200, 5500, 0, 0]; // 一~日；今天=第5天
function renderStatusCharts() {
  const wb = document.getElementById('weekBars');
  if (wb && !wb.dataset.done) {
    const mx = Math.max(...WEEK_STEPS, 1);
    const names = ['一', '二', '三', '四', '五', '六', '日'];
    wb.innerHTML = WEEK_STEPS.map((v, i) => {
      const kind = i === 4 ? 'today' : (i > 4 ? 'future' : (v >= 5000 ? 'hi' : ''));
      const hpx = v ? Math.max(10, Math.round(v / mx * 74)) : 8;
      return '<div class="cbar ' + kind + '"><i style="height:' + hpx + 'px"></i><b>' + names[i] + '</b></div>';
    }).join('');
    wb.dataset.done = '1';
  }
  const mb = document.getElementById('monthBars');
  if (mb && !mb.dataset.done) {
    let html = '';
    for (let d = 1; d <= 30; d++) {
      const v = d <= 23 ? (30 + ((d * 37) % 60)) : 0; // 過去23天示範值、未來留白
      const kind = d === 23 ? 'today' : (d > 23 ? 'future' : (v >= 70 ? 'hi' : ''));
      html += '<div class="cbar ' + kind + '"><i style="height:' + Math.max(6, Math.round(v / 90 * 44)) + 'px"></i></div>';
    }
    mb.innerHTML = html;
    mb.dataset.done = '1';
  }
}
function renderPillTask() {
  const card = document.querySelector('.task-item[data-task="pill"]');
  const title = $('#pillTitle'), sub = $('#pillSub');
  if (!card || !title || !sub) return;
  const meds = loadMeds();
  if (!meds.length) {
    // 沒設定用藥就不該有這個任務——整條收起來，不留佔位（Edward 2026-07-07）
    card.style.display = 'none';
    card.classList.remove('done');
    if (typeof refreshTaskProgress === 'function') refreshTaskProgress();
    return;
  }
  card.style.display = '';
  let done = {};
  try { done = JSON.parse(localStorage.getItem('munea.medDone.' + pillDateKey())) || {}; } catch (e) {}
  const slots = [];
  for (const med of meds) {
    for (const raw of String(med.time).split('、')) {
      const slot = raw.trim();
      if (slot) slots.push({ slot, name: med.name, key: slot + '|' + med.name, photo: med.photo || '' });
    }
  }
  slots.sort((a, b) => PILL_SLOT_ORDER.indexOf(a.slot) - PILL_SLOT_ORDER.indexOf(b.slot));
  const total = slots.length;
  const doneN = slots.filter(s => done[s.key]).length;
  const next = slots.find(s => !done[s.key]);
  if (next) {
    title.textContent = '吃' + String(next.name).split(/\s+/)[0]; // 標題用短名、全名在用藥管理
    sub.textContent = next.slot + ' · 今天 ' + doneN + '/' + total + ' 次';
    card.classList.remove('done');
  } else {
    title.textContent = '今天的藥都吃了';
    sub.textContent = total + ' 次都記到了，讚';
    card.classList.add('done');
  }
  const _pico = card.querySelector('.task-ico');
  if (_pico) { const _pph = next && next.photo; if (_pph) { _pico.style.backgroundImage = 'url(' + _pph + ')'; _pico.style.backgroundSize = 'cover'; _pico.style.backgroundPosition = 'center'; _pico.classList.add('med-photo-ico'); _pico.onclick = ev => { ev.stopPropagation(); showMedPhoto(_pph, next.name); }; } else { _pico.style.backgroundImage = ''; _pico.classList.remove('med-photo-ico'); _pico.onclick = null; } }
  if (typeof refreshTaskProgress === 'function') refreshTaskProgress();
}
// 回診只在「當天」變成今日任務；其餘日子不顯示（Edward 2026-07-07）
function _todayISO() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}
function visitToday() {
  let arr = null;
  try { arr = JSON.parse(localStorage.getItem('munea.visits') || 'null'); } catch (e) {}
  if (!Array.isArray(arr)) return null;
  const today = _todayISO();
  return arr.filter(v => v && v.dateISO === today).sort((a, b) => String(a.time || '').localeCompare(String(b.time || '')))[0] || null;
}
function _clock12(tv) {
  const p = String(tv || '').split(':'); const hh = +p[0], mm = +p[1] || 0;
  if (isNaN(hh)) return '';
  const ap = hh < 12 ? '上午' : '下午'; const h12 = ((hh + 11) % 12) + 1;
  return ap + ' ' + h12 + (mm ? ':' + String(mm).padStart(2, '0') : '');
}
// 24 小時制，跟用藥任務的「14:00」一致（Edward 2026-07-14）
function _clock24(tv) {
  const p = String(tv || '').split(':'); const hh = +p[0], mm = +p[1] || 0;
  if (isNaN(hh)) return '';
  return String(hh).padStart(2, '0') + ':' + String(mm).padStart(2, '0');
}
// 只要「7/14（週二）」——不帶標題、不帶時間（Edward 2026-07-14）
function _visitDayShort(v) {
  if (!v) return '';
  if (v.dateISO) {
    const d = new Date(v.dateISO + 'T00:00');
    if (!isNaN(d.getTime())) return (d.getMonth() + 1) + '/' + d.getDate() + '（' + ['週日', '週一', '週二', '週三', '週四', '週五', '週六'][d.getDay()] + '）';
  }
  return String(v.label || '').split(/\s*[上下]午/)[0].trim();  // 舊資料兜底
}
function renderVisitTask() {
  const card = document.getElementById('visitTask');
  if (!card) return;
  const v = visitToday();
  if (!v) { card.style.display = 'none'; card.classList.remove('done'); if (typeof refreshTaskProgress === 'function') refreshTaskProgress(); return; }
  card.style.display = '';
  const t = $('#visitTaskTitle'), s = $('#visitTaskSub'), tm = $('#visitTaskTime');
  if (t) t.textContent = v.title || v.label || '回診';
  if (s) s.textContent = _visitDayShort(v) || '記得帶健保卡';
  if (tm) tm.textContent = _clock24(v.time) || '今天';
  if (typeof refreshTaskProgress === 'function') refreshTaskProgress();
}
// 首頁「今天一起完成」整組重算：用藥（有設才有）＋回診（當天才有）＋走走＋心情筆記＋聊聊
function renderDailyTasks() { renderPillTask(); renderVisitTask(); refreshMoodTask(); }
window.__muneaRenderDailyTasks = renderDailyTasks;
// Apple 健康的步數 → 首頁走路任務（原生端 health.js 讀到步數後呼叫）
window.__muneaSetSteps = function (n) {
  n = Math.max(0, Math.round(+n || 0));
  const card = document.querySelector('.task-item[data-task="walk"]');
  if (!card) return;
  const goal = (window.MuneaHealth && window.MuneaHealth.GOAL) || 500;
  const sub = document.getElementById('walkSub');
  const chip = document.getElementById('walkChip');
  if (sub) sub.textContent = n >= goal ? ('今天走了 ' + n.toLocaleString() + ' 步，達標了') : ('今天走了 ' + n.toLocaleString() + ' / ' + goal + ' 步');
  if (chip) chip.textContent = n >= goal ? '達標' : (n.toLocaleString() + ' 步');
  card.dataset.steps = String(n);
  if (n >= goal) card.classList.add('done'); // 走到目標就自動完成
  if (typeof refreshTaskProgress === 'function') refreshTaskProgress();
  // 步數也記進數據日記帳（供 7/30 天真趨勢）
  try {
    if (!isLoggedIn()) throw 'guest';
    const day = _todayISO();
    mergeHealthHistory([{ date: day, steps: n }]);
  } catch (e) {}
};

const HEALTH_LOG_RETENTION_DAYS = 365;
function mergeHealthHistory(days, syncCloud = true) {
  if (!isLoggedIn() || !Array.isArray(days)) return {};
  let log = {};
  try { log = JSON.parse(localStorage.getItem('munea.healthLog') || '{}') || {}; } catch (e) {}
  const fields = ['bpSys', 'bpDia', 'hr', 'spo2', 'sleepHours', 'steps'];
  for (const item of days) {
    if (!item || !/^\d{4}-\d{2}-\d{2}$/.test(String(item.date || ''))) continue;
    const current = Object.assign({}, log[item.date] || {});
    for (const field of fields) {
      const value = Number(item[field]);
      if (Number.isFinite(value) && value >= 0) current[field] = value;
    }
    if (Object.keys(current).length) log[item.date] = current;
  }
  const keys = Object.keys(log).sort();
  while (keys.length > HEALTH_LOG_RETENTION_DAYS) delete log[keys.shift()];
  try { localStorage.setItem('munea.healthLog', JSON.stringify(log)); } catch (e) {}
  if (syncCloud) pushOwnHealthLog(log);
  return log;
}
window.__muneaSetHealthHistory = function (days) { return mergeHealthHistory(days, true); };

function muneaCloudPersonId() {
  try { return localStorage.getItem('munea.cloudPersonId') || muneaDeviceId(); }
  catch (e) { return muneaDeviceId(); }
}
function pushOwnHealthLog(log) {
  try {
    const pf = JSON.parse(localStorage.getItem('munea.personProfile') || '{}');
    const personId = muneaCloudPersonId();
    const keys = Object.keys(log || {}).sort();
    const day = keys[keys.length - 1] || _todayISO();
    const current = (log || {})[day] || {};
    const mine = {};
    mine[personId] = Object.assign({ name: (pf.name || '').trim(), nick: (pf.nick || '').trim(), day, updatedAt: Date.now(), log }, current);
    syncPush('vitals', mine);
  } catch (e) {}
}
// Apple 健康的完整摘要 → 狀態頁「今天」的真數值（原生端 health.js 讀到後呼叫）
// s = { available, steps, hr, spo2, bpSys, bpDia, sleepHours }；缺哪項就不動哪項（示範值留著、不清空）
window.__muneaSetHealth = function (s) {
  if (!s || s.available === false) return;
  const num = v => (typeof v === 'number' && isFinite(v) && v > 0) ? v : null;
  const put = (id, txt) => { const el = document.getElementById(id); if (el) el.textContent = txt; };
  const chip = (id, txt, warn) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = txt;
    el.style.display = '';   // 真數據到了就把標籤點亮（沒接裝置時是藏起來的）
    el.style.background = warn ? 'var(--coral-soft)' : 'var(--mint)';
    el.style.color = warn ? 'var(--coral-d)' : 'var(--teal-dd)';
  };
  const sys = num(s.bpSys), dia = num(s.bpDia), hr = num(s.hr), spo2 = num(s.spo2),
        sleep = num(s.sleepHours), steps = num(s.steps);
  const worry = []; // 給「寧寧的觀察」的注意事項（白話）
  if (sys && dia) {
    const hi = sys >= 140 || dia >= 90, lo = sys < 90;
    put('bpNum', String(Math.round(sys)));
    put('bpUnit', '/' + Math.round(dia) + ' mmHg');
    chip('bpChip', hi ? '偏高' : lo ? '偏低' : '穩定', hi || lo);
    put('bpSub', hi ? '比平常高一點，晚點再量一次' : lo ? '偏低一些，起身動作放慢' : '正常範圍內');
    if (hi) worry.push('血壓比平常高一點'); if (lo) worry.push('血壓偏低');
  }
  if (hr) {
    const odd = hr < 50 || hr > 100;
    put('hrNum', String(Math.round(hr)));
    chip('hrChip', odd ? '注意' : '正常', odd);
    if (odd) worry.push('心跳' + (hr > 100 ? '偏快' : '偏慢'));
  }
  if (spo2) {
    put('spo2Num', String(Math.round(spo2)));
    if (spo2 < 95) worry.push('血氧有點低');
  }
  if (sleep) {
    put('sleepNum', String(Math.round(sleep * 10) / 10));
    if (sleep < 6) worry.push('昨晚睡得少');
  }
  if (steps) {
    put('stepsNum', Math.round(steps).toLocaleString());
    // 運動量不足（7/9 Edward 點題）：傍晚後還走不到 3000 步才提、白天不亂催
    if (new Date().getHours() >= 18 && steps < 3000) worry.push('今天走得比較少');
  }
  // 寧寧的觀察：有真資料才改寫，一句話講重點
  const obs = document.getElementById('obsText');
  if (obs && (sys || hr || sleep)) {
    const B = t => '<b style="color:#8FD4CC">' + t + '</b>';
    const bits = [];
    if (sys && dia) bits.push('血壓 ' + B(Math.round(sys) + '/' + Math.round(dia)));
    if (hr) bits.push('心率 ' + B(Math.round(hr)));
    if (sleep) bits.push('睡眠 ' + B((Math.round(sleep * 10) / 10) + ' 小時'));
    const head = '今天' + bits.join('、') + '，';
    obs.innerHTML = worry.length
      ? head + '大致都穩，不過' + B(worry.join('、')) + '，我幫你多留意，先別擔心。'
      : head + '整體狀態不錯。<span style="color:#8FD4CC;font-weight:700">保持這個節奏就很好</span>，想出門走走我陪你。';
    window.__muneaObsReal = obs.innerHTML;   // 真觀察已寫：分頁切換不得用預設蓋掉
  }
  // 安全通知（真的動）：數據掉出危險範圍 → 寫進家人動態（雲端同步、家人打開沐寧就看到）；同類 6 小時最多一次
  try {
    const danger = [];
    if (sys && (sys >= 180 || sys < 90)) danger.push('血壓 ' + Math.round(sys) + (dia ? '/' + Math.round(dia) : ''));
    if (hr && (hr > 120 || hr < 45)) danger.push('心率 ' + Math.round(hr));
    if (spo2 && spo2 < 90) danger.push('血氧 ' + Math.round(spo2) + '%');
    if (danger.length) {
      const last = +(localStorage.getItem('munea.safetyAlertAt') || 0);
      if (Date.now() - last > 21600000) {
        localStorage.setItem('munea.safetyAlertAt', String(Date.now()));
        let who = '家人';
        try { const pf = JSON.parse(localStorage.getItem('munea.personProfile') || '{}'); who = pf.nick || pf.name || '家人'; } catch (e2) {}
        pushFamilyFeed('⚠️ <b>' + who + '</b>的' + danger.join('、') + '超出安全範圍，打通電話關心一下');
        try { trackProductEvent('safety_alert_recorded', { kinds: danger.length }); } catch (e2) {}
      }
    }
  } catch (e) {}
  // 數據日記帳：今天的數據記成歷史（日期為鍵、留 365 天），狀態頁 7/30 天分頁就從這裡長出真趨勢
  // 7/9 Edward 拍板：只有登入的會員才記每天的數據 → 之後才有 7/30 天趨勢（訪客看得到今天、但不累積歷史）
  try {
    if (!isLoggedIn()) throw 'guest';   // 訪客不記歷史（今日即時數字上面已顯示）
    const day = _todayISO();
    const cur = {};
    if (sys) cur.bpSys = Math.round(sys);
    if (dia) cur.bpDia = Math.round(dia);
    if (hr) cur.hr = Math.round(hr);
    if (spo2) cur.spo2 = Math.round(spo2);
    if (sleep) cur.sleepHours = Math.round(sleep * 10) / 10;
    if (steps) cur.steps = Math.round(steps);
    mergeHealthHistory([Object.assign({ date: day }, cur)]);
  } catch (e) {}
};
function renderMedList() { renderMedSlots(); }
const MED_SLOT_DEF = [
  ['早餐後', 'b', 30], ['午餐後', 'l', 30], ['晚餐後', 'd', 30], ['睡前', 's', -30]
];
function medSlotTime(rtKey, offset) {
  let rt = { b: '07:30', l: '12:00', d: '18:00', s: '22:00' };
  try { rt = Object.assign(rt, JSON.parse(localStorage.getItem('munea.routine') || '{}')); } catch (e) {}
  let parts = (rt[rtKey] || '08:00').split(':').map(Number);
  const total = (parts[0] * 60 + parts[1] + offset + 1440) % 1440;
  return String(Math.floor(total / 60)).padStart(2, '0') + ':' + String(total % 60).padStart(2, '0');
}
function showMedPhoto(url, name) {
  if (!url) return;
  let lb = document.getElementById('medLightbox');
  if (!lb) { lb = document.createElement('div'); lb.id = 'medLightbox'; lb.className = 'med-lightbox'; document.body.appendChild(lb); lb.addEventListener('click', ev => { if (ev.target === lb || ev.target.classList.contains('mlb-close')) lb.classList.remove('show'); }); }
  lb.innerHTML = '<div class="mlb-card"><img src="' + url + '" alt=""><div class="mlb-name">' + (name || '') + '</div><button type="button" class="mlb-close">關閉</button></div>';
  lb.classList.add('show');
}
function canvasToJpeg(cv) { let q = 0.82; let url = cv.toDataURL('image/jpeg', q); while (url.length > 180000 && q > 0.4) { q -= 0.16; url = cv.toDataURL('image/jpeg', q); } return url; }
function looksLikeImage(file) { return !!file && (/^image\//.test(file.type || '') || /\.(jpe?g|png|heic|heif|webp|gif|bmp)$/i.test(file.name || '')); }
function resizeSquare(file, cb, onErr) {
  if (!looksLikeImage(file)) { if (onErr) onErr(); return; }
  const r = new FileReader();
  r.onerror = () => { if (onErr) onErr(); };
  r.onload = () => { const img = new Image(); img.onload = () => { try { const S = 512; const side = Math.min(img.width, img.height); const sx = (img.width - side) / 2, sy = (img.height - side) / 2; const cv = document.createElement('canvas'); cv.width = S; cv.height = S; cv.getContext('2d').drawImage(img, sx, sy, side, side, 0, 0, S, S); cb(canvasToJpeg(cv)); } catch (e) { if (onErr) onErr(); } }; img.onerror = () => { if (onErr) onErr(); }; img.src = r.result; };
  r.readAsDataURL(file);
}
function renderMedSlots() {
  const box = $('#medSlots');
  if (!box) return;
  const meds = loadMeds();
  box.innerHTML = MED_SLOT_DEF.map(def => {
    const slot = def[0], k = def[1], off = def[2];
    const inSlot = meds.filter(m => String(m.time).split('、').map(x => x.trim()).includes(slot));
    const rows = inSlot.length
      ? inSlot.map(m => '<div class="ms-med">' + (m.photo ? '<span class="ms-thumb" data-name="' + m.name + '" style="background-image:url(' + m.photo + ')"></span>' : '') + '<b>' + m.name + '</b><span>' + m.days + '</span><button type="button" class="ms-del" data-slot="' + slot + '" data-name="' + m.name + '" aria-label="移除">✕</button></div>').join('')
      : '<div class="ms-empty">這個時段沒有藥</div>';
    return '<div class="ms-group"><div class="ms-head"><b>' + slot + '</b>' +
      '<span class="ms-time-wrap"><button type="button" class="ms-tbtn" data-k="' + k + '" data-m="-15">−</button>' +
      '<input type="time" class="ms-time" data-k="' + k + '" data-off="' + off + '" value="' + medSlotTime(k, off) + '" />' +
      '<button type="button" class="ms-tbtn" data-k="' + k + '" data-m="15">＋</button></span>' +
      '<span class="ms-count">' + (inSlot.length ? inSlot.length + ' 種' : '') + '</span></div>' + rows + '</div>';
  }).join('');
}

const POINTS = { total: 0, used: 0,    // 方案與雲端錢包載入後再填入，不預設舊方案額度
  get bought() { try { return +localStorage.getItem('munea.ptsBought') || 0; } catch (e) { return 0; } } };
const LOW_PTS = 30;
window.__ptsTest = { setUsed: v => { POINTS.used = v; renderPoints(); }, ff: s => { _callSec = s; } };
window.__medRefresh = () => updateMedCount();
function ptsLeft() { return POINTS.total - POINTS.used + POINTS.bought; }
function refreshLowState() {
  const pts = document.querySelector('.hud-pill.pts');
  if (pts) pts.classList.toggle('low', ptsLeft() < LOW_PTS);
  const strip = document.getElementById('lowPtsStrip');
  if (strip) strip.style.display = ptsLeft() < LOW_PTS ? '' : 'none';
}
function pushWallet() { syncPush('wallet', { grant: POINTS.total, used: POINTS.used, bought: POINTS.bought }); }
function renderPoints() {
  const left = POINTS.total - POINTS.used + POINTS.bought;
  const hud = document.querySelector('.hud-pill.pts');
  if (hud) hud.textContent = '剩 ' + left + ' 點';
  if ($('#ptsLeft')) $('#ptsLeft').textContent = left;
  if ($('#ptsUsed')) $('#ptsUsed').textContent = POINTS.used;
  if ($('#ptsBar')) $('#ptsBar').style.width = (POINTS.total > 0 ? Math.round(POINTS.used / POINTS.total * 100) : 0) + '%';
  refreshLowState();
}

let _callTimerInt = null, _callSec = 0;
let _lowWarned = false, _zeroSaid = false, _freeWarned = false;
let _brainDegraded = false;
function callBudgetTick() {
  if (window.MMPLAN && window.MMPLAN.isFree()) return;   // 免費用「單次時間試用」、不吃點數
  const left = ptsLeft() - Math.floor(_callSec / 60);
  if (!_lowWarned && left <= 15 && left > 0) {
    _lowWarned = true;
    setCaption('點數快用完了，大概還能聊 ' + left + ' 分鐘', '用完聊天會先停，補點數就能繼續');
  }
  if (!_zeroSaid && left <= 0) {
    _zeroSaid = true;
    __muneaPointsOut();                                  // 點數用完 → 停止聊天 + 跳補點數
  }
}
function __muneaShowPointsPopup(){
  var old=document.getElementById('mm-pts'); if(old) old.remove();
  var m=document.createElement('div'); m.id='mm-pts';
  m.style.cssText='position:fixed;inset:0;z-index:10060;display:flex;align-items:center;justify-content:center;background:rgba(30,26,22,.5);-webkit-backdrop-filter:blur(3px);backdrop-filter:blur(3px)';
  m.innerHTML='<div style="width:min(320px,84vw);background:#F4F0E8;border-radius:24px;padding:26px 22px 18px;text-align:center;box-shadow:0 24px 60px -14px rgba(0,0,0,.5)">'
    +'<div style="width:54px;height:54px;border-radius:16px;margin:0 auto 16px;background:linear-gradient(135deg,#E0B354,#C79A3B);display:grid;place-items:center"><svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7.5v9M9 10h4.5a1.5 1.5 0 0 1 0 3h-3a1.5 1.5 0 0 0 0 3H15"/></svg></div>'
    +'<div style="font-family:\'Noto Serif TC\',Georgia,serif;font-weight:900;font-size:19px;color:#3A352E;margin-bottom:10px">點數用完了</div>'
    +'<div style="font-size:14px;line-height:1.75;color:#5A6963;margin-bottom:20px">聊天會用到點數，這批剛好用完囉。補一些點數，就能繼續跟沐寧聊。</div>'
    +'<button id="mm-pts-go" style="width:100%;border:none;background:#3AA8A0;color:#fff;font-weight:700;font-size:15.5px;padding:14px;border-radius:14px;cursor:pointer;margin-bottom:6px">補充點數</button>'
    +'<button id="mm-pts-no" style="width:100%;border:none;background:none;color:#8A9691;font-weight:600;font-size:14px;padding:9px;cursor:pointer">先不用</button>'
    +'</div>';
  document.body.appendChild(m);
  m.addEventListener('click',function(e){ if(e.target===m||e.target.id==='mm-pts-no') m.remove(); });
  var go=document.getElementById('mm-pts-go');
  if(go) go.addEventListener('click',function(){ m.remove(); var tm=document.getElementById('topUpModal'); if(tm) tm.classList.add('show'); });
}
function __muneaPointsOut(){
  try { if (typeof LiveVoice !== 'undefined' && LiveVoice && LiveVoice.stop) LiveVoice.stop(); } catch (e) {}
  try { completeChatSession('out_of_points'); } catch (e) {}
  try { chatOpened = false; } catch (e) {}
  try { setCallToggle(false); } catch (e) {}
  stopCallTimer();
  __muneaShowPointsPopup();
}
function __muneaFreeChatOut__setCool() { try { localStorage.setItem('munea.reviewCoolOff', '1'); setTimeout(() => localStorage.removeItem('munea.reviewCoolOff'), 3600000); } catch (e) {} }
function __muneaFreeChatOut(){ __muneaFreeChatOut__setCool();
  try { if (typeof LiveVoice !== 'undefined' && LiveVoice && LiveVoice.stop) LiveVoice.stop(); } catch (e) {}
  try { completeChatSession('free_signup_trial_exhausted'); } catch (e) {}
  try { chatOpened = false; } catch (e) {}
  try { setCallToggle(false); } catch (e) {}
  stopCallTimer();
  toast('免費帳號的一次性 5 點體驗已用完');
  try { FaceIdle.start(); } catch (e) {}   // 收線後回到待機輪播
  if (window.MMPLAN) window.MMPLAN.upsell('chat-daily');
}
function startCallTimer() {
  stopCallTimer(); _callSec = 0;
  const el = $('#callTimer');
  _callTimerInt = setInterval(() => {
    callBudgetTick();
    if (window.MMPLAN && window.MMPLAN.isFree()) {
      window.MMPLAN.chatTick();
      const _rem = window.MMPLAN.chatRemainSec();
      // 快到了先溫柔預告（剩 1 分鐘）：畫面提示＋悄悄請角色自然收尾，不再無預警斷線
      if (_rem > 0 && _rem <= 60 && !_freeWarned) {
        _freeWarned = true;
        toast('免費體驗剩約 1 點，慢慢說完沒關係');
        try {
          if (LiveVoice && LiveVoice.on && LiveVoice.ws && LiveVoice.ws.readyState === 1) {
            LiveVoice.ws.send(JSON.stringify({ type: 'text', text: '（系統悄悄話，請不要唸出這段、也不要提到系統或倒數：免費體驗只剩大約一分鐘，請自然地把話題暖心收尾，溫柔說今天先聊到這。）' }));
          }
        } catch (e) {}
      }
      if (_rem <= 0) { __muneaFreeChatOut(); return; }
    }
    _callSec++;
    const m = String(Math.floor(_callSec / 60)).padStart(2, '0');
    const s = String(_callSec % 60).padStart(2, '0');
    if (el) el.textContent = m + ':' + s;
  }, 1000);
}
function stopCallTimer() {
  _lowWarned = false; _zeroSaid = false; _freeWarned = false; _brainDegraded = false; if (_callTimerInt) { clearInterval(_callTimerInt); _callTimerInt = null; } const el = $('#callTimer'); if (el) el.textContent = '00:00'; }
// 字幕（逐字稿）預設「關」——依產品規劃，聊聊像視訊通話、只留必要狀態；字幕是給重聽長輩的可選輔助。
let captionsOn = false;
try { captionsOn = localStorage.getItem('munea.captions') === '1'; } catch (e) {}
function applyCaptionState() {
  const b = document.getElementById('captionToggle');
  const chat = document.getElementById('chat');
  if (b) { b.classList.toggle('off', !captionsOn); b.setAttribute('aria-pressed', captionsOn ? 'true' : 'false'); }
  if (chat) chat.classList.toggle('captions-on', captionsOn);
  const ih = document.getElementById('faceIdleHi'); if (ih) ih.style.display = captionsOn ? '' : 'none';  // 字幕關→開場那串招呼字也不顯示（Edward 2026-07-07）
  if (!captionsOn) { const box = document.querySelector('.face-caption-box'); if (box) box.remove(); }
}
function setCaption(text, hint) {
  if (!captionsOn) return;                 // 字幕關閉時不顯示逐字稿
  let box = document.querySelector('.face-caption-box');
  if (!box) {
    box = document.createElement('div');
    box.className = 'face-caption-box';
    document.getElementById('chat')?.appendChild(box);
  }
  box.innerHTML = text + (hint ? '<small>' + hint + '</small>' : '');
}

let _toastTimer = null;
// 每台裝置一個身份、每個家庭一個編號：同步時帶上，別人家的動態不會混進來（真帳號上線後改綁帳號）
function muneaDeviceId() {
  try {
    let d = localStorage.getItem('munea.deviceId');
    if (!d) { d = 'dev-' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36); localStorage.setItem('munea.deviceId', d); }
    return d;
  } catch (e) { return 'dev-anon'; }
}
function famGroupId() {
  try {
    let g = localStorage.getItem('munea.familyGroupId');
    if (!g) { g = 'fam-' + muneaDeviceId(); localStorage.setItem('munea.familyGroupId', g); }
    return g;
  } catch (e) { return 'fam-anon'; }
}
function myFeedName() { try { const p2 = JSON.parse(localStorage.getItem('munea.personProfile') || '{}'); return (p2.nick || p2.name || '').trim() || '家人'; } catch (e) { return '家人'; } }
function myProfileName() {
  try { const p = JSON.parse(localStorage.getItem('munea.personProfile') || '{}'); return (p.name || p.nick || '').trim(); } catch (e) { return ''; }
}
function syncPush(key, value) {
  try {
    // 用藥照片只留本機、不上雲（隱私修正 7/9）：meds 同步前把 base64 照片欄位剝掉，其餘欄位照送
    const payload = (key === 'meds' && Array.isArray(value))
      ? value.map(m => { const rest = Object.assign({}, m); delete rest.photo; return rest; })
      : value;
    muneaAuthHeaders({ 'Content-Type': 'application/json' }).then(headers => {
      fetch(brainURL('/family/state'), { method: 'POST', headers, body: JSON.stringify({ action: 'save', key, value: payload, familyGroupId: famGroupId(), personId: muneaCloudPersonId() }) }).catch(() => {});
    }).catch(() => {});
  } catch (e) {}
}
async function syncPullAll() {
  try {
    const r = await fetch(brainURL('/family/state'), { method: 'POST', headers: await muneaAuthHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify({ action: 'load', familyGroupId: famGroupId() }) });
    if (!r.ok) return;
    const st = (await r.json()).state || {};
    const map = { activities: 'munea.activities', familyFeed: 'munea.familyFeed2', meds: 'munea.meds', visit: 'munea.visit', visits: 'munea.visits', routine: 'munea.routine', vitals: 'munea.famVitals' };
    for (const k in map) {
      if (st[k] !== undefined && st[k] !== null) {
        try { localStorage.setItem(map[k], JSON.stringify(st[k])); } catch (e) {}
      }
    }
    const ownVitals = st.vitals && st.vitals[muneaCloudPersonId()];
    if (ownVitals && ownVitals.log && typeof ownVitals.log === 'object') {
      const days = Object.keys(ownVitals.log).map(date => Object.assign({ date }, ownVitals.log[date] || {}));
      mergeHealthHistory(days, false);
    }
    // 圈名單同步（雲端不存「本人」標記，各裝置用自己的名字對回去）
    if (Array.isArray(st.circle) && st.circle.length) {
      try {
        const mine = myProfileName();
        const arr = st.circle.map(m => ({ name: m.name, init: m.init, tint: m.tint, self: !!mine && m.name === mine }));
        if (!arr.some(m => m.self)) {
          const p = JSON.parse(localStorage.getItem('munea.personProfile') || '{}');
          arr.unshift({ name: mine || p.nick || '我', init: (p.nick || mine || '我')[0], tint: 'p-ama', self: true });
        }
        localStorage.setItem('munea.circleMembers', JSON.stringify(arr));
        if (typeof window.__muneaAfterCircleSync === 'function') window.__muneaAfterCircleSync();
      } catch (e) {}
    }
    if (st.wallet && typeof st.wallet.used === 'number') {
      POINTS.used = st.wallet.used;
      try { localStorage.setItem('munea.ptsBought', String(st.wallet.bought || 0)); } catch (e) {}
    }
    if (typeof updateMedCount === 'function') updateMedCount();
    if (typeof renderPoints === 'function') renderPoints();
    if (typeof renderVisitRow === 'function') try { renderVisitRow(); } catch (e) {}
    renderCareCarousel();
  } catch (e) {}
}
function streakLine(n) {
  if (n >= 10) return '這個月有 <b>' + n + ' 天</b>準時吃藥，很穩，繼續保持';
  if (n >= 3) return '這個月有 <b>' + n + ' 天</b>準時吃藥，節奏出來了';
  return '開始把吃藥記下來了，好的開始';
}
const CARE_ICONS = {
  msg: '<svg class="ic" viewBox="0 0 24 24"><path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8z"/></svg>',
  walk: '<svg class="ic" viewBox="0 0 24 24"><path d="M13 4a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zM8 21l3-6M14 21v-5l-2.5-3 1-5.5M8.5 9 11 6.5l2.5 1 2 3H18"/></svg>',
  cal: '<svg class="ic" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>',
  medal: '<svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="8" r="6"/><path d="M15.5 12.9 17 22l-5-3-5 3 1.5-9.1"/></svg>'
};
let _careIdx = 0, _careTimer = null;
// 留意卡文案規則（Edward 7/6）：標題 ≤12 字（一行放得下）、副標最多兩行（約 26 字內）完整顯示
function plain(s) { return String(s == null ? '' : s).replace(/<[^>]+>/g, ''); }
function buildCareItems() {
  const items = [];
  let feed = [];
  try { feed = JSON.parse(localStorage.getItem('munea.familyFeed2')) || []; } catch (e) {}
  const relayMsg = feed.find(x => /要我提醒你|帶話/.test(String(x)));
  let _rTitle = '家人帶話給你', _rSub = '';
  if (relayMsg) { const _p = plain(relayMsg); const _m = _p.match(/^(.+?)要我提醒你[：:]?\s*(.*)$/); if (_m) { _rTitle = _m[1].trim() + ' 要我提醒你'; _rSub = _m[2].trim(); } else { _rSub = _p; } }
  // 蘋果 UGC 審核要求（7/9）：這則若真的來自家人 feed（傳話/愛心/塗鴉…），記下它在陣列裡的位置，卡片才能掛「移除／檢舉」；示範文案（feed 是空的）不算數
  const _feedIdx = relayMsg ? feed.indexOf(relayMsg) : (feed.length ? 0 : -1);
  const familyItem = relayMsg
    ? { k: 'family', tone: '', icon: 'msg', title: _rTitle, sub: _rSub, btn: '知道了', feedIdx: _feedIdx }
    : { k: 'family', tone: '', icon: 'msg', title: '家人帶話給你', sub: feed[0] ? plain(feed[0]) : '美華說週末回去看你，' + cname() + '都幫你收著了', btn: '去看看', feedIdx: _feedIdx };
  let acts = [];
  try { acts = JSON.parse(localStorage.getItem('munea.activities')) || []; } catch (e) {}
  const act = acts.find(a => a && !a.done && !a.archived);
  if (act && (act.type === 'walk' || /走|步/.test(act.title || ''))) {
    const goal = +(act.steps || act.goal || 8000);
    const gap = Math.max(0, goal - (+(act.mySteps || act.progress || 3000)));
    items.push({ k: 'family', tone: 'coral', icon: 'walk', title: (act.owner || '家人') + '發起的走路活動', sub: gap > 0 ? '還差 ' + gap.toLocaleString() + ' 步就達標，今晚一起走走？' : '目標達成了，去看看大家的成績', btn: '去看看' });
  } else if (act) {
    items.push({ k: 'family', tone: 'coral', icon: 'walk', title: (act.owner || '家人') + '發起了活動', sub: '「' + (act.title || '家庭活動') + '」進行中，看看大家的進度', btn: '去看看' });
  } else {
    items.push({ k: 'family', tone: 'coral', icon: 'walk', title: '外婆發起的走路活動', sub: '還差 5,000 步就達標，今晚一起走走？', btn: '去看看' });
  }
  items.push(familyItem);
  let v = null;
  try {
    let arr = JSON.parse(localStorage.getItem('munea.visits') || 'null');
    if (!Array.isArray(arr)) { const old = JSON.parse(localStorage.getItem('munea.visit') || 'null'); arr = (old && old.dateISO) ? [old] : []; }
    const today = isoOf(new Date());
    v = arr.filter(x => x && x.dateISO && x.dateISO >= today).sort((a, b) => a.dateISO.localeCompare(b.dateISO))[0] || null;
  } catch (e) {}
  if (v && v.dateISO) items.push({ k: 'status', tone: '', icon: 'cal', title: (v.title ? v.title : (v.label || '回診')) + '快到了', sub: (v.label || String(v.dateISO).slice(5).replace('-', '/')) + ' · 想問醫生的，' + cname() + '都幫你記著', btn: '看安排' });
  items.push({ k: 'status', tone: 'gold', icon: 'medal', title: '準時吃藥有節奏', sub: plain(streakLine(Math.max(1, new Date().getDate() - 1))) });
  return items;
}
function renderCareCarousel() {
  const body = document.getElementById('careBody');
  const dots = document.getElementById('careDots');
  if (!body || !dots) return;
  const items = buildCareItems();
  body.innerHTML = items.map((it, i) =>
    '<div class="care-item' + (i === 0 ? ' on' : '') + '" data-k="' + it.k + '">' +
    '<span class="care-ico ' + it.tone + '">' + CARE_ICONS[it.icon] + '</span>' +
    '<div class="care-txt"><p>' + (String(it.title).length > 12 ? String(it.title).slice(0, 12) : it.title) + '</p>' + (it.sub ? '<small>' + it.sub + '</small>' : '') +
    (typeof it.feedIdx === 'number' && it.feedIdx > -1 ? '<div class="care-mod"><button type="button" class="care-mod-btn" data-remove="' + it.feedIdx + '">移除這則</button><button type="button" class="care-mod-btn" data-report="' + it.feedIdx + '">檢舉</button></div>' : '') +
    '</div>' +
    (it.btn ? '<button type="button" class="care-btn" data-go="' + it.k + '">' + it.btn + '</button>' : '') +
    '</div>').join('');
  dots.innerHTML = items.map((_, i) => '<i class="' + (i === 0 ? 'on' : '') + '"></i>').join('');
  _careIdx = 0;
  if (_careTimer) clearInterval(_careTimer);
  _careTimer = setInterval(() => careAdvance(1), 5200);
  // 首輪起轉延後 1.4 秒：讓進場動畫先走完、不疊影
  clearInterval(_careTimer);
  _careTimer = null;
  setTimeout(() => { if (!_careTimer) _careTimer = setInterval(() => careAdvance(1), 5200); }, 1400);
}
function careAdvance(step) {
  const its = document.querySelectorAll('#careBody .care-item');
  const dots = document.querySelectorAll('#careDots i');
  if (!its.length) return;
  its[_careIdx].classList.remove('on');
  if (dots[_careIdx]) dots[_careIdx].classList.remove('on');
  _careIdx = (_careIdx + step + its.length) % its.length;
  its[_careIdx].classList.add('on');
  if (dots[_careIdx]) dots[_careIdx].classList.add('on');
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
  renderCareCarousel();
}
function restoreFamilyFeed() { renderCareCarousel(); }
// 蘋果 UGC 審核要求（7/9）：家人動態/傳話/塗鴉要能「移除」「檢舉」——都是真動作，不是假成功
function removeFamilyFeedItem(idx) {
  const a = loadFeed();
  if (idx < 0 || idx >= a.length) return;
  a.splice(idx, 1);
  try { localStorage.setItem('munea.familyFeed2', JSON.stringify(a)); } catch (e) {}
  syncPush('familyFeed', a);
  renderCareCarousel();
  toast('已經移除這則了');
}
function reportFamilyFeedItem(idx) {
  const a = loadFeed();
  if (idx < 0 || idx >= a.length) return;
  const content = plain(a[idx]);
  try {
    const log = JSON.parse(localStorage.getItem('munea.feedReported') || '[]');
    log.unshift({ text: content, at: Date.now() });
    localStorage.setItem('munea.feedReported', JSON.stringify(log.slice(0, 50)));
  } catch (e) {}
  // 真的送進引擎既有的意見收件箱（會叮 #munea-營運、進 /admin/feedback 清單），不是假送出
  brainPost('/feedback', { type: 'bug', category: '檢舉動態', text: '【檢舉家人動態】' + content, appVersion: (window.MuneaVersion && window.MuneaVersion.current) || '', plan: (window.MMPLAN && window.MMPLAN.get()) || '' });
  a.splice(idx, 1);
  try { localStorage.setItem('munea.familyFeed2', JSON.stringify(a)); } catch (e) {}
  syncPush('familyFeed', a);
  renderCareCarousel();
  toast('已收到，我們會處理；這則也先收起來了');
}

function toast(text, duration = 2600) {
  const t = $('#toast');
  if (!t) return;
  t.textContent = text;
  t.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => t.classList.remove('show'), duration);
}

// 版本顯示 + 「版本更新」彈窗（讀 window.MuneaVersion 這個單一真相）
function applyAppVersion() {
  const V = window.MuneaVersion; if (!V) return;
  const n = document.getElementById('verRowNum'); if (n) n.textContent = V.current;
}
function openVersionSheet() {
  const V = window.MuneaVersion || { current: '—', channel: '', changelog: [] };
  const cur = document.getElementById('verCurrent'); if (cur) cur.textContent = V.current;
  const ch = document.getElementById('verChannel'); if (ch) ch.textContent = V.channel || '';
  const list = document.getElementById('changelogList');
  if (list) {
    list.innerHTML = (V.changelog || []).map(rel =>
      '<div class="cl-rel"><div class="cl-head"><b>v' + rel.version + '</b>' +
      (rel.title ? '<span class="cl-title">' + rel.title + '</span>' : '') +
      '<span class="cl-date">' + (rel.date || '') + '</span></div><ul>' +
      (rel.items || []).map(i => '<li>' + i + '</li>').join('') + '</ul></div>'
    ).join('');
  }
  const m = document.getElementById('versionSheet'); if (m) m.classList.add('show');
}

// ===== 健康頁：分層排版（今日總結＋想提醒你＋都很穩）· 對應「健康照護-數據告警AI提醒-設計」=====
// [ENGINE] 正式版：值/燈號由守護腦判定＋真 Apple 健康帶入；read 由管家腦生成。
const METRIC_ICON = {
  bp:     '<path d="M19 14c1.5-1.5 3-3.2 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.8 0-3 .5-4.5 2-1.5-1.5-2.7-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4 3 5.5l7 7Z"/><path d="M3.2 12H9l.5-1 2 4.5 2-7 1.5 3.5h5.3"/>',
  hr:     '<path d="M3 12h4l2-6 4 12 2-6h6"/>',
  spo2:   '<path d="M12 3s6 6 6 11a6 6 0 0 1-12 0c0-5 6-11 6-11z"/>',
  steady: '<path d="M13 4a2 2 0 1 0 0 0M8 21l2-6 3 2 1 4M14 11l-3-2-3 2-2 4M15 13l3 1"/>',
  sleep:  '<path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/>',
  act:    '<path d="M4 16v-2.4c0-2.1-1-3.1-1-5.6 0-2.7 1.5-6 4.5-6C9.4 2 10 3.8 10 5.5c0 3.1-2 5.7-2 8.7V16a2 2 0 1 1-4 0Z"/><path d="M20 20v-2.4c0-2.1 1-3.1 1-5.6 0-2.7-1.5-6-4.5-6C14.6 6 14 7.8 14 9.5c0 3.1 2 5.7 2 8.7V20a2 2 0 1 0 4 0Z"/>',
  med:    '<path d="M10.5 20.5 3.5 13.5a5 5 0 0 1 7-7l7 7a5 5 0 0 1-7 7z"/><path d="M8.5 8.5l7 7"/>',
};
const HEALTH_METRICS = {
  bp:     { name: '血壓', val: '128', unit: '/82', status: 'ok',   read: '這週血壓都很穩，維持得很好。', trend: [126,130,128,124,128,127,128] },
  hr:     { name: '心率', val: '72',  unit: ' 次', status: 'ok',   read: '心跳平穩，沒有不規則的狀況。', trend: [70,72,71,73,72,70,72] },
  spo2:   { name: '血氧', val: '97',  unit: '%',   status: 'ok',   read: '血氧很足，呼吸順順的。', trend: [97,98,97,96,97,97,97] },
  steady: { name: '走路穩定度', val: '偏低', unit: '', status: 'warn', read: '這週走路穩定度有點降，走慢些、扶著點。要不要我提醒美華多留意？', trend: [3,3,2,2,2,2,2] },
  sleep:  { name: '睡眠', val: '7.5', unit: ' 時', status: 'ok',   read: '睡得不錯，這週平均 7.4 小時。', trend: [7.2,7.5,6.8,7.6,7.4,7.5,7.5] },
  act:    { name: '活動', val: '20',  unit: ' 分', status: 'ok',   read: '今天有出門走走，很好；回來記得喝口水。', trend: [12,18,9,20,15,22,20] },
  med:    { name: '用藥', val: '2',   unit: '/3',  status: 'warn', read: '今天還剩 1 次沒吃，到時間我會叫你。', trend: [1,1,1,0,1,1,1] },
};
const METRIC_ORDER = ['bp', 'hr', 'spo2', 'steady', 'sleep', 'act', 'med'];
const STATUS_WORD = { ok: '穩', warn: '注意', alert: '要小心' };
function metricSvg(key) { return '<svg class="ic" viewBox="0 0 24 24">' + (METRIC_ICON[key] || '') + '</svg>'; }
function renderHealthDashboard() {
  const dots = document.getElementById('heroDots'), focus = document.getElementById('focusList'), calm = document.getElementById('calmStrip');
  if (!dots || !focus || !calm) return;
  const warns = METRIC_ORDER.filter(k => HEALTH_METRICS[k].status !== 'ok');
  const oks = METRIC_ORDER.filter(k => HEALTH_METRICS[k].status === 'ok');
  // 寧寧的話隨時段變（招牌記憶點：像記得你的時間）
  const head = document.getElementById('thHead'), sub = document.getElementById('thSub');
  if (head && sub) {
    const h = new Date().getHours();
    const part = h < 11 ? '早安，昨晚睡得不錯。' : h < 17 ? '午後了，記得起來走走。' : '今天辛苦了，早點歇著。';
    if (!warns.length) { head.textContent = '今天一切都好'; sub.textContent = part + '每一項我都看著，放心。'; }
    else { head.textContent = '今天大致都穩'; sub.textContent = part + '有 ' + warns.length + ' 件事我幫你盯著。'; }
  }
  // HERO 燈號：短橫條（綠=穩會呼吸、珊瑚=注意恆亮）
  dots.innerHTML = METRIC_ORDER.map(k => '<i class="' + HEALTH_METRICS[k].status + '"></i>').join('');
  // 想請你留意：大卡
  focus.innerHTML = warns.map(k => {
    const m = HEALTH_METRICS[k];
    return '<button class="focus-card ' + m.status + '" type="button" data-metric="' + k + '">' +
      '<span class="fc-ico">' + metricSvg(k) + '</span>' +
      '<div class="fc-body"><div class="fc-top"><b>' + m.name + '</b><span class="fc-val">' + m.val + '<small>' + m.unit + '</small></span></div>' +
      '<div class="fc-read">' + m.read + '</div></div>' +
      '<span class="fc-chev"><svg class="ic" viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg></span></button>';
  }).join('');
  // 其他都很穩：安靜清單列
  calm.innerHTML = oks.map(k => {
    const m = HEALTH_METRICS[k];
    return '<button class="calm-row" type="button" data-metric="' + k + '">' +
      '<span class="cr-ico">' + metricSvg(k) + '</span>' +
      '<span class="cr-name">' + m.name + '</span>' +
      '<span class="cr-val">' + m.val + '<small>' + m.unit + '</small></span>' +
      '<span class="cr-dot"></span></button>';
  }).join('');
}
function renderMetricDetail(key) {
  const box = document.getElementById('metricDetail');
  if (!box) return;
  document.querySelectorAll('#status [data-metric]').forEach(t => t.classList.toggle('open', t.dataset.metric === key));
  if (box.dataset.open === key) { box.hidden = true; box.dataset.open = ''; document.querySelectorAll('#status [data-metric]').forEach(t => t.classList.remove('open')); return; }
  const m = HEALTH_METRICS[key];
  if (!m) { box.hidden = true; return; }
  const max = Math.max(...m.trend), min = Math.min(...m.trend);
  const bars = m.trend.map((v, i) => {
    const h = max === min ? 60 : 22 + Math.round((v - min) / (max - min) * 58);
    return `<i style="height:${h}%" class="${i === m.trend.length - 1 ? 'now' : ''}"></i>`;
  }).join('');
  const days = ['一', '二', '三', '四', '五', '六', '日'];
  box.innerHTML =
    `<div class="md-head"><b>${m.name} · 這週</b><span class="md-status ${m.status}">${STATUS_WORD[m.status]}</span></div>` +
    `<div class="md-chart">${bars}</div>` +
    `<div class="md-days">${days.map(d => '<span>' + d + '</span>').join('')}</div>` +
    `<div class="md-read"><span class="md-face"><img src="avatars/nening-v2-face.png" alt=""></span><span>${m.read}</span></div>`;
  box.hidden = false; box.dataset.open = key;
  try { box.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); } catch (e) {}
}
function initHealthDashboard() {
  renderHealthDashboard();
  const status = document.getElementById('status');
  if (status) status.addEventListener('click', e => {
    const el = e.target.closest('.focus-card[data-metric], .calm-row[data-metric]');
    if (el) renderMetricDetail(el.dataset.metric);
  });
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
  // 寧寧只用她本人的聲音（真語音 playB64）。沒有真聲音時，絕不用系統的機械聲代打——
  // 改用一則輕量文字提示，不破壞「是寧寧在講話」的感覺。
  toast(text);
}

// 今天一起完成：打勾 → 寧寧鼓勵（不是賺幣，是被看見）
const CHEERS = {
  pill: '藥吃了，你真棒，我幫你記到存摺裡，美華也看得到。',
  visit: '回診辛苦了，醫生說的我幫你記著，回家歇一下。',
  walk: '出去走走最好了，回來記得喝口水。',
  chat: '謝謝你跟我說這些，我都記下來了。',
  mood: '今天的心情記好了，謝謝你願意照顧自己的感受。',
};
function refreshMoodTask() {
  const item = document.querySelector('.task-item[data-task="mood"]');
  if (!item) return;
  const done = !!(window.MM && typeof window.MM.hasSelfReportToday === 'function' && window.MM.hasSelfReportToday());
  item.classList.toggle('done', done);
  const sub = document.getElementById('moodTaskSub');
  const chip = document.getElementById('moodTaskChip');
  if (sub) sub.textContent = done ? '今天的心情已記錄' : '記錄今天的心情';
  if (chip) chip.textContent = done ? '完成' : '隨時';
  refreshTaskProgress();
}
window.__muneaMoodRecorded = function () { refreshMoodTask(); };
window.__muneaPostMood = function (body) { return brainPost('/wellbeing/log', body || {}); };
window.__muneaPullMood = function (body) { return brainPost('/wellbeing/recent', body || { limit: 400 }); };
function refreshTaskProgress() {
  const items = $$('#taskCard .task-item').filter(i => i.style.display !== 'none');
  const done = items.filter(i => i.classList.contains('done')).length;
  const tp = document.querySelector('.task-progress');
  if (tp) tp.classList.toggle('full', done === items.length && items.length > 0);
  if (done === items.length && items.length && !window.__celebrated) {
    window.__celebrated = true;
    setTimeout(() => toast('今天' + items.length + '件都完成了，我跟家人說一聲'), 250);
    if (typeof pushFamilyFeed === 'function') pushFamilyFeed('<b>' + myFeedName() + '</b>今天把該做的都完成了，給他一個讚');
  }
  const pillTask = document.querySelector('.task-item[data-task="pill"]');
  const pv = $('#statPillVal');
  const pdone = pillTask && pillTask.classList.contains('done');
  if (pv && pillTask) pv.innerHTML = (pdone ? '3' : '2') + '<small>/3</small>';
  const dots = document.querySelectorAll('#pillDots i');
  if (dots.length) dots.forEach((d2, i2) => d2.classList.toggle('f', i2 < (pdone ? 3 : 2)));
  const hint = $('#statPillHint');
  if (hint) { hint.textContent = pdone ? '都吃了' : '剩 1 次'; hint.className = 'st-trend ' + (pdone ? 'ok' : 'warn'); }
  const prog = $('.task-progress');
  if (!prog) return;
  const label = prog.childNodes[prog.childNodes.length - 1];
  if (label) label.textContent = ` ${done} / ${items.length}`;
  const bar = prog.querySelector('.bar i');
  if (bar) bar.style.width = items.length ? `${Math.round(done / items.length * 100)}%` : '0%';
}

let _uncheckArm = null;
function toggleTask(item) {
  if (item.dataset.task === 'mood') {
    showView('status');
    try { if (window.MM && typeof window.MM.renderMood === 'function') window.MM.renderMood('today'); } catch (e) {}
    setTimeout(() => {
      const card = document.getElementById('moodCheckinCard');
      if (card) card.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 80);
    return;
  }
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
    const r = await fetch(brainURL('/wellbeing/trend'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ days: 7 }) });
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

async function connectCall() {
  // 撥通中＝保持角色的待機動畫（Edward 2026-07-09 二次拍板：不定格照片、也不動照片）。
  // 硬規則：聲音＋會動的臉「兩邊都真的就緒」才一起開場——寧可讓用戶等，也不要開場後像當機。
  // 同線聲音的 iPhone 解鎖（2026-07-11）：iPhone 不准「沒經過使用者手指」的聲音自動播——
  // 同線那軌之前一直被擋、每通都退回本地播放。趁「開始通話」這根手指先讓 faceAud 播一下取得許可。
  try {
    Avatar._callT0 = Date.now(); Avatar._diagTrail = [];   // 黑盒子每通歸零
    Avatar._diagNote('按下開始通話');
    if (faceSameLineOn()) {
      const _fv = document.getElementById('faceVid');
      if (_fv) {
        // 趁「這根手指」餵一段無聲的真聲音給影像播放器並播——iPhone 才會把「出聲許可」記在它身上；
        // 之前只對「還沒裝聲音的空播放器」喊 play 不算數（真串流一秒後到、手指許可已過期又被擋）＝延遲根因之一。
        try {
          const AC = window.AudioContext || window.webkitAudioContext;
          Avatar._primeCtx = Avatar._primeCtx || new AC();
          try { if (Avatar._primeCtx.state === 'suspended') Avatar._primeCtx.resume(); } catch (e2) {}
          const dst = Avatar._primeCtx.createMediaStreamDestination();
          const g = Avatar._primeCtx.createGain(); g.gain.value = 0;
          const osc = Avatar._primeCtx.createOscillator(); osc.connect(g); g.connect(dst); osc.start();
          _fv.srcObject = dst.stream; _fv.muted = false;   // 無聲音軌、不影響待機影片（待機片在另一層）
          const _p2 = _fv.play();
          if (_p2 && _p2.then) _p2.then(() => Avatar._diagNote('解鎖影像播放器:成功')).catch((er) => Avatar._diagNote('解鎖:被擋(' + (er && er.name) + ')', true));
        } catch (e3) { try { _fv.muted = false; const _p3 = _fv.play(); if (_p3 && _p3.catch) _p3.catch(() => {}); } catch (e4) {} Avatar._diagNote('解鎖:改用簡易法'); }
      }
      const _fa = document.getElementById('faceAud');
      if (_fa) { _fa.muted = false; const _p = _fa.play(); if (_p && _p.catch) _p.catch(() => {}); }
    }
  } catch (e) {}
  // Keep the iOS user gesture alive before the queue/network wait starts.
  if (!LiveVoice.prime()) {
    setCallHint(LiveVoice._micUnavailableReason === 'https_required'
      ? '手機／區網測試需要 HTTPS 才能開麥，請改用公開測試連結'
      : '拿不到麥克風，請到瀏覽器設定允許');
    return;
  }
  if (typeof FaceIdle !== 'undefined' && !FaceIdle.active) FaceIdle.start();   // 進頁已在播就延續、不重啟（免重播招呼）
  setCallDialing(true);   // 按鈕「撥通中···」；兩邊都就緒才變「結束通話」＋開始計時
  if (CallControl.url()) {
    setCallHint('正在安排語音與影像席位…', true);
    try {
      await CallControl.acquire(typeof currentChar === 'string' ? currentChar : 'default');
    } catch (e) {
      LiveVoice.stop(); setCallDialing(false); stopCallTimer();
      const reason = String(e && e.message || e);
      setCallHint(reason.indexOf('queue_full') >= 0 ? '目前等待人數已滿，請稍後再撥' :
        (reason.indexOf('insufficient_credits') >= 0 ? '點數不足，補充後就能繼續聊' : '目前通話服務忙碌中，請稍後再試'));
      try { trackProductEvent('call_control_rejected', { reason }); } catch (e2) {}
      return;
    }
  }
  let _connectedOnce = false;
  const markConnected = () => { if (_connectedOnce) return; _connectedOnce = true; setCallToggle(true); startCallTimer(); };
  const capOff = $('#captionToggle') && $('#captionToggle').classList.contains('off');
  const box = document.querySelector('.face-caption-box');
  if (box) box.style.display = capOff ? 'none' : '';
  // 真即時語音（Gemini 3.1 Live）：麥克風即時串流、寧寧真聲音即時回、可打斷
  if (getLiveVoiceUrl()) {
    chatOpened = true;
    activeChatSessionId = makeSessionId('voice');
    activeChatStartedAt = Date.now();
    activeChatTurnCount = 0;
    setFaceState('idle');
    // 新引擎首通冷開機較久（喚醒優化交先鋒車道）——誠實預告、不讓人以為當機（Edward 2026-07-11「等20秒」）
    setCallHint(faceEngine() === 'flashhead' && !Avatar.warm ? '新引擎暖身中，首次約需半分鐘…' : '連線中…', true);
    trackProductEvent('voice_session_started', { locale: muneaLocale(), mode: 'live' });
    const chatEl = document.getElementById('chat');
    if (chatEl) chatEl.dataset.state = 'connecting';   // 撥通中：待機動畫照播、收音波頻不出現

    // ===== 兩邊都就緒才開場（Edward 2026-07-09 二次拍板）=====
    let _voiceReady = false, _faceReady = false, _started = false, _faceUnavailable = false;
    const noFace = !getAvatarUrl();          // 沒接雲端臉的角色（或關閉）＝不必等臉
    if (noFace) _faceReady = true;
    const beginConversation = () => {
      if (_started || !_voiceReady || !_faceReady) return;
      if (!callDialing && !callConnected) { clearTimeout(_gateTimeout); return; }   // 已取消/掛斷 → 別誤開場
      _started = true;
      clearTimeout(_gateTimeout);
      try { localStorage.setItem('munea.callCount', String((parseInt(localStorage.getItem('munea.callCount') || '0', 10) || 0) + 1)); } catch (e) {}   // 聊過幾通＋1 → 下通開場更像老朋友（熟識度）
      // 三條管線（腦、影像、Avatar 聲音上行）都就緒後再多等 1.5 秒才開口。
      // 待機動畫在這段時間繼續播，避免第一批招呼聲先於聲畫管線到達而變形或被吃掉。
      const _greetDelay = 1500;
      setTimeout(() => {
        if (!callConnected && !callDialing) return;   // 這 1 秒內掛斷了就別開口
        markConnected();                    // 暖身也完成，現在才從「撥通中」切成真正接通並開始計時
        if (!noFace && !_faceUnavailable) { const bg = document.querySelector('#chat .face-bg'); if (bg) bg.classList.add('livevid'); }   // 亮出會動的臉
        try { FaceIdle.stop(); } catch (e) {}
        LiveVoice.greet();                   // 管線穩了才請她主動開口（招呼講完才開麥）
      }, _greetDelay);
      setTimeout(() => { if (LiveVoice._openMicAfterGreet) { LiveVoice._setMicOpen(true); LiveVoice._openMicAfterGreet = false; } }, 6000 + _greetDelay);   // 開麥保底順延（別在她還沒開口就開麥）
      try { if (window.MuneaAvSyncMeter && typeof Avatar !== 'undefined' && Avatar.on) MuneaAvSyncMeter.start(); } catch (e) {}   // 接了會動的臉才量延遲（左下角讀數 · Edward 2026-07-10）
      // 省點提醒（Edward 2026-07-10）：通話開著卻一直沒人講話 → 寧寧兩段式溫柔提醒、再久自動掛斷、不浪費點數。
      // 時鐘只算「真沉默」（使用者＋AI 都沒講）；使用者一開口整個歸零。11 秒一階。
      const _autoEndCall = () => {
        setCallHint('先幫你把通話收起來囉，想聊再找我');
        try { LiveVoice.stop(); } catch (e) {} try { FaceWave.stop(); } catch (e) {}
        try { completeChatSession('idle_timeout'); } catch (e) {}
        chatOpened = false; setCallToggle(false); stopCallTimer();
        const ce = document.getElementById('chat'); if (ce) ce.dataset.state = 'idle';
        setFaceState('idle'); if (window.__muneaStopListen) window.__muneaStopListen();
        try { FaceIdle.start(); } catch (e) {}
      };
      let _idleLast = Date.now(), _idleStage = 0;
      const _idleGapMs = 30000;   // Edward 2026-07-10 拍板：第一次提醒 30 秒、第二次再過 30 秒（自動收線再 30 秒）
      const _idleMon = setInterval(() => {
        if (!callConnected && !callDialing) { clearInterval(_idleMon); return; }      // 通話結束 → 自我終止
        if (LiveVoice.micLevel > 0.08) { _idleLast = Date.now(); _idleStage = 0; return; }   // 使用者在講 → 全歸零
        if (speechActive()) { _idleLast = Date.now(); return; }   // AI 在講（單一真相 speechActive：本地喇叭或臉那條線都認）→ 時鐘後推、階段保留
        if (Date.now() - _idleLast < _idleGapMs) return;                               // 還沒到 30 秒真沉默
        // Edward 2026-07-11 拍板：提醒做不好就拿掉、不要再吵——兩段提醒全停（nudge 不再呼叫），
        // 只留第三段「沉默 90 秒安靜收線」。要復原提醒＝把下兩行換回 LiveVoice.nudge(1)/nudge(2)。
        if (_idleStage === 0) { _idleStage = 1; _idleLast = Date.now(); }
        else if (_idleStage === 1) { _idleStage = 2; _idleLast = Date.now(); }
        else { clearInterval(_idleMon); _autoEndCall(); }                              // 第三段沉默 → 自動收線
      }, 1500);
    };
    const tryStart = () => beginConversation();
    window.__muneaOnFaceReady = () => { _faceReady = true; tryStart(); };
    // 準備逾時絕不「假裝就緒」硬開場。舊規則 25 秒後強制放行，正是顯卡未好就撥通、首句變形的來源。
    const _gateTimeout = setTimeout(() => {
      if (_started) return;
      try { LiveVoice.stop(); } catch (e) {}
      chatOpened = false; setCallDialing(false); stopCallTimer();
      const ce = document.getElementById('chat'); if (ce) ce.dataset.state = 'idle';
      setFaceState('idle'); setCallHint('目前連線還沒準備好，請稍後再試');
      try { completeChatSession('readiness_timeout'); } catch (e) {}
      try { FaceIdle.start(); } catch (e) {}
      try { trackProductEvent('voice_readiness_timeout', { voiceReady: _voiceReady, faceReady: _faceReady }); } catch (e) {}
    }, 30000);

    LiveVoice.onReady = () => { _voiceReady = true; tryStart(); };   // 語音伺服器接上腦＝語音就緒
    LiveVoice.onConnecting = () => { if (chatEl) chatEl.dataset.state = 'connecting'; setCallHint('連線中…', true); };
    // 開場後才顯示狀態（撥通中維持待機動畫、不搶戲）
    const onListen = () => { if (!_started) return; if (chatEl) chatEl.dataset.state = 'listening'; setFaceState('listening'); setCallHint('我在聽，你說吧'); FaceWave.start(() => LiveVoice.micLevel); };
    const onSpeak = () => { if (!_started) return; if (chatEl) chatEl.dataset.state = 'speaking'; setFaceState('speaking'); setCallHint('正在說話'); FaceWave.start(() => LiveVoice.playLevel); avatarRuntime.startLiveViseme(() => LiveVoice.playLevel); };
    LiveVoice.onCaption = (t) => setCaption(t);   // 字幕開啟時，寧寧說的話逐字上字幕
    // 斷線自動接回：掉了就自動重連；多次失敗則收整通，不退成純語音。
    let _reconnects = 0;
    const onDrop = () => {
      if (!callConnected && !callDialing) return;         // 使用者已掛斷/取消 → 不重連
      if (_reconnects++ > 6) {                            // Voice＋Avatar 是同一項服務；任一邊斷線就收整通
        try { LiveVoice.stop(); } catch (e) {}
        try { completeChatSession('reconnect_failed'); } catch (e) {}
        chatOpened = false; setCallDialing(false); setCallToggle(false); stopCallTimer();
        if (chatEl) chatEl.dataset.state = 'idle';
        setFaceState('idle'); setCallHint('連線中斷了，請再撥一次');
        try { FaceIdle.start(); } catch (e) {}
        return;
      }
      setCallHint('接回來中', true);
      setTimeout(() => {
        if (!callConnected && !callDialing) return;
        const resume = CallControl.active ? CallControl.refreshToken() : Promise.resolve();
        resume.then(() => LiveVoice.start(onListen, onSpeak, onDrop)).catch(() => onDrop());
      }, 500);
    };
    LiveVoice.start(onListen, onSpeak, onDrop);
    Avatar.start().then(ok => {
      if (ok || Avatar._lastError !== 'capacity_full') return;
      try { LiveVoice.stop(); } catch (e) {}
      chatOpened = false; setCallDialing(false); stopCallTimer();
      if (chatEl) chatEl.dataset.state = 'idle';
      setFaceState('idle'); setCallHint('目前 3 個通話席都在使用中，請稍後再撥');
      try { completeChatSession('avatar_capacity_full'); } catch (e) {}
      try { trackProductEvent('avatar_capacity_full', { mode: 'voice_avatar_required' }); } catch (e) {}
      try { FaceIdle.start(); } catch (e) {}
    }).catch(() => {});   // 影像滿載不退純語音；下一版接 Gateway 後顯示排隊位置
    return;
  }
  setCaption('接通了，直接說話就可以', '想到什麼就說，我在聽');
  markConnected();   // 簡單陪聊模式（無雲端語音）＝立即可講
  openVoiceSession();
  setTimeout(() => { if (window.__muneaStartListen) window.__muneaStartListen(); }, 400);
}

function init() {
  if (new URLSearchParams(location.search).get('debug')) document.body.classList.add('debug');
  // 體驗捷徑：網址帶 ?voiceUrl= / ?avatarUrl= → 寫進本機設定後生效（一鍵體驗 bat 用）
  try {
    const _q = new URLSearchParams(location.search);
    if (_q.get('voiceUrl') !== null) localStorage.setItem('munea.liveVoiceUrl', _q.get('voiceUrl'));
    if (_q.get('avatarUrl') !== null) localStorage.setItem('munea.avatarUrl', _q.get('avatarUrl'));
    if (_q.get('brainUrl') !== null) localStorage.setItem('munea.brainUrl', _q.get('brainUrl'));
    if (_q.get('faceEngine') !== null) localStorage.setItem('munea.faceEngine', _q.get('faceEngine'));   // 換臉引擎捷徑：?faceEngine=flashhead / ditto（空字串=回預設）
    // 視覺檢查台（機器人測試員的眼睛）：?callmock=1 ＝ 直接擺出「通話中」畫面（全身合成+live 狀態），
    // 拍照模式瀏覽器拍圖驗「滿版/無紗/無框」——不連線、不出聲、純畫面。
    if (_q.get('callmock') === '1' || _q.get('photomock') === '1') setTimeout(() => { try {
      document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
      const _c = document.getElementById('chat'); _c.classList.add('active'); _c.dataset.state = 'speaking';
      if (_q.get('callmock') === '1') {   // callmock=活臉層；photomock=純底圖照片層（看有沒有上下漸層紗）
        const _f = document.getElementById('fhFrame'); if (_f) _f.hidden = false;
        document.querySelector('#chat .face-bg').classList.add('livevid');
      }
    } catch (e) {} }, 600);
  } catch (e) {}
  try { const _vs = document.getElementById('webVerStamp'); if (_vs && window.MuneaVersion) _vs.textContent = '內頁 v' + MuneaVersion.current; } catch (e) {}   // 內頁真版印章：通話畫面角落顯示網頁內容真版本（防 iOS 外殼標籤新、內頁舊）
  const __pullPromise = syncPullAll();
  refreshServerPlanEntitlement();
  setInterval(() => { try { syncPullAll(); } catch (e) {} }, 120000);   // 家人動態每 2 分鐘拉一次（傳話/告警跨裝置到達）
  document.querySelectorAll('#taskCard svg').forEach(s2 => s2.setAttribute('aria-hidden', 'true'));
  document.querySelectorAll('#taskCard .task-check').forEach(s2 => s2.setAttribute('aria-label', '完成打勾'));
  syncCompanionUI();
  setupHscrollHints();
  renderPoints();
  updateMedCount();
  renderVisitTask();
  if (window.MuneaHealth) window.MuneaHealth.boot(); // 之前連過 Apple 健康就靜默帶回今天步數
  renderCareCarousel();
  if ($('#careBody')) $('#careBody').addEventListener('click', e => {
    const rm = e.target.closest('[data-remove]');
    if (rm) { removeFamilyFeedItem(+rm.dataset.remove); return; }
    const rp = e.target.closest('[data-report]');
    if (rp) { reportFamilyFeedItem(+rp.dataset.report); return; }
    const b = e.target.closest('.care-btn');
    if (b) showView(b.dataset.go === 'status' ? 'status' : 'family');
  });
  if (location.hash.slice(1) === 'pick') {
    const sheet = $('#companionSheet');
    const mask = sheet && sheet.closest('.modal-mask');
    if (mask) { showView('settings'); mask.classList.add('show'); }
  }
  // 關閉聊聊（X）＝有通話先掛斷結算，再回首頁；沒通話就直接回
  if ($('#chatExit')) $('#chatExit').addEventListener('click', () => {
    if (callConnected || callDialing) {
      const wasConnected = callConnected;
      LiveVoice.stop(); completeChatSession(wasConnected ? 'user_ended' : 'user_cancelled'); chatOpened = false; setCallToggle(false); if (window.__muneaStopListen) window.__muneaStopListen();
      if (wasConnected) {
        try { const n = +(localStorage.getItem('munea.stat.chatsCompleted') || 0) + 1; localStorage.setItem('munea.stat.chatsCompleted', String(n)); } catch (e2) {}
        setTimeout(() => window.__muneaMaybeAskReview('chat_completed'), 800);   // 自己掛斷＝好好聊完 → 開心時刻
      }
    }
    FaceWave.stop();
    showView('home');
  });
  // 滑掉/切走 App＝自動掛斷（Edward 2026-07-10）：離開畫面就走「結束通話」完整收線（停聲音/停臉/停計時/記點），不讓通話在背景白燒點數
  const _hangupOnLeave = () => { try { if ((callConnected || callDialing) && $('#callToggle')) $('#callToggle').click(); } catch (e) {} };
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') _hangupOnLeave(); });
  window.addEventListener('pagehide', _hangupOnLeave);
  if ($('#callToggle')) $('#callToggle').addEventListener('click', () => {
    // 撥通中再按一次＝取消撥號、回到待機
    if (callDialing && !callConnected) {
      LiveVoice.stop(); FaceWave.stop(); completeChatSession('user_cancelled'); chatOpened = false;
      setCallToggle(false); stopCallTimer();
      const chatEl = document.getElementById('chat'); if (chatEl) chatEl.dataset.state = 'idle';
      setFaceState('idle'); if (window.__muneaStopListen) window.__muneaStopListen();
      FaceIdle.start();
      return;
    }
    if (!callConnected && !localStorage.getItem('munea.consent.crossborder')) { $('#consentSheet').classList.add('show'); return; }
    // 第一次開聊前輕問一次「想聊什麼話題」（可跳過、之後在設定隨時改；只問這一次）
    if (!callConnected && !localStorage.getItem('munea.interestsAsked') && !loadInterests().length && window.__muneaOpenInterests) { window.__muneaOpenInterests(true); return; }
    if (!callConnected) { connectCall(); }
    else { LiveVoice.stop(); FaceWave.stop(); completeChatSession('user_ended'); chatOpened = false; setCallToggle(false); if (window.__muneaStopListen) window.__muneaStopListen(); FaceIdle.start(); }
  });
  if ($('#captionToggle')) $('#captionToggle').addEventListener('click', () => {
    captionsOn = !captionsOn;
    try { localStorage.setItem('munea.captions', captionsOn ? '1' : '0'); } catch (e) {}
    applyCaptionState();
    toast(captionsOn ? '字幕開啟：會顯示逐字' : '字幕關閉');
  });
  applyCaptionState();
  enableSheetDrag();               // 所有彈窗支援下拉關閉手勢
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
      try { if (window.MuneaHealth && typeof window.MuneaHealth.refresh === 'function') window.MuneaHealth.refresh(); } catch (e) {}
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

  // 首頁「跟寧寧聊聊」＝ 進全屏臉「待命」；使用者自己按「開始通話」才啟動、才開始扣點（Edward 7/7：不自動通話）
  if ($('#startCall')) $('#startCall').addEventListener('click', () => {
    if (!requireLogin('請先登入或註冊才能使用聊聊；免費帳號會收到一次性 5 點，約 5 分鐘', 'chat')) return;
    if (window.MMPLAN && window.MMPLAN.isFree()) { if (window.MMPLAN.chatRemainSec() <= 0) { window.MMPLAN.upsell('chat-daily'); return; } }
    else if (typeof ptsLeft === 'function' && ptsLeft() <= 0) { __muneaShowPointsPopup(); return; }
    showView('chat');
  });
  // （提醒改為彈窗版；埋點併入 B1 排程處理器）

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
  function saveRoutine(rt) { try { localStorage.setItem('munea.routine', JSON.stringify(rt)); } catch (e) {} syncPush('routine', rt); if (window.MuneaNotify) window.MuneaNotify.sync(); }
  function shiftTime(t, mins) {
    let [h, m] = t.split(':').map(Number);
    let total = (h * 60 + m + mins + 1440) % 1440;
    return String(Math.floor(total / 60)).padStart(2, '0') + ':' + String(total % 60).padStart(2, '0');
  }
  let _pfPendingAvatar = '';
  const PF_DEF = { name: '', nick: '', birth: '', city: '' };   // 7/9 正式化：不再預設示範身分（陳秀英/阿嬤）——空欄位＋提示字自己填
  function loadPersonProfile() { try { return Object.assign({}, PF_DEF, JSON.parse(localStorage.getItem('munea.personProfile') || '{}')); } catch (e) { return Object.assign({}, PF_DEF); } }
  // 所在地＝縣市→區 兩層下拉（iPhone 原生滾輪、長輩好按、零錯字 · 2026-07-09 Edward 改用選單）
  function pfCountyList() { return (window.TW_DISTRICTS ? Object.keys(window.TW_DISTRICTS) : []); }
  function fillPfDistricts(county, selDist) {
    const ds = $('#pfDistrict'); if (!ds) return;
    const list = (window.TW_DISTRICTS && window.TW_DISTRICTS[county]) || [];
    let h = '<option value="">（區）</option>';
    for (const d of list) h += '<option value="' + d + '">' + d + '</option>';
    ds.innerHTML = h;
    ds.disabled = !county;
    if (selDist && list.indexOf(selDist) >= 0) ds.value = selDist;
  }
  function parsePfCity(city) {   // 舊資料/自由輸入相容：把「台北市大安區」拆回 縣市＋區
    city = (city || '').trim();
    for (const c of pfCountyList()) {
      if (city.indexOf(c) === 0) {
        const rest = city.slice(c.length);
        const list = window.TW_DISTRICTS[c] || [];
        return { county: c, district: (list.indexOf(rest) >= 0 ? rest : '') };
      }
    }
    return { county: '', district: '' };
  }
  function fillPfLocation(city) {
    const cs = $('#pfCounty'); if (!cs) return;
    if (!cs.options.length) {
      let h = '<option value="">（縣市）</option>';
      for (const c of pfCountyList()) h += '<option value="' + c + '">' + c + '</option>';
      cs.innerHTML = h;
      cs.addEventListener('change', () => fillPfDistricts(cs.value, ''));
    }
    const parsed = parsePfCity(city);
    cs.value = parsed.county;
    fillPfDistricts(parsed.county, parsed.district);
  }
  function pfLocationValue() {   // 存檔：縣市＋區 合成一個字串（只選縣市也可、有區更準）
    const c = ($('#pfCounty') && $('#pfCounty').value) || '';
    const d = ($('#pfDistrict') && $('#pfDistrict').value) || '';
    return c ? (c + d) : '';
  }
  function fillPersonProfile() {
    const p = loadPersonProfile();
    if ($('#pfName')) $('#pfName').value = p.name;
    if ($('#pfNick')) $('#pfNick').value = p.nick;
    const ys = $('#pfBirthY'), ms = $('#pfBirthM');
    if (ys && !ys.options.length) {
      const nowY = new Date().getFullYear();
      let yh = '';
      for (let y = nowY - 5; y >= 1920; y--) yh += '<option value="' + y + '">' + y + ' 年</option>';
      ys.innerHTML = yh;
      let mh = '';
      for (let m = 1; m <= 12; m++) mh += '<option value="' + m + '">' + m + ' 月</option>';
      ms.innerHTML = mh;
    }
    const mt = String(p.birth || '').match(/(19|20)(\d{2}).*?(\d{1,2})/);
    if (ys) ys.value = mt ? mt[1] + mt[2] : '1954';
    if (ms) ms.value = mt ? String(+mt[3]) : '3';
    fillPfLocation(p.city);
    _pfPendingAvatar = p.avatar || '';
    if (typeof renderPfAvatar === 'function') renderPfAvatar(p.avatar, p.nick);
  }
  if ($('#pfSaveBtn')) $('#pfSaveBtn').addEventListener('click', () => {
    const p = {
      name: ($('#pfName').value || '').trim() || PF_DEF.name,
      nick: ($('#pfNick').value || '').trim() || PF_DEF.nick,
      birth: ($('#pfBirthY') && $('#pfBirthY').value ? $('#pfBirthY').value + ' 年 ' + $('#pfBirthM').value + ' 月' : PF_DEF.birth),
      city: pfLocationValue() || PF_DEF.city,
      avatar: _pfPendingAvatar,
    };
    try { localStorage.setItem('munea.personProfile', JSON.stringify(p)); } catch (e) {}
    if (typeof applyUserAvatar === 'function') applyUserAvatar();
    $('#profileModal').classList.remove('show');
    toast(p.name ? ('存好了，' + p.name + '，資料我記著。') : '存好了，資料我記著。');
  });
  if ($('#profileRow')) $('#profileRow').addEventListener('click', () => { fillPersonProfile(); $('#profileModal').classList.add('show'); });
  if ($('#profileClose')) $('#profileClose').addEventListener('click', () => $('#profileModal').classList.remove('show'));
  if ($('#profileModal')) $('#profileModal').addEventListener('click', e => { if (e.target === $('#profileModal')) $('#profileModal').classList.remove('show'); });
  function renderPfAvatar(av, nick) {
    const box = $('#pfAvatar'); if (!box) return;
    box.style.backgroundImage = av ? 'url(' + av + ')' : '';
    box.classList.toggle('has-photo', !!av);
    if ($('#pfAvatarClear')) $('#pfAvatarClear').hidden = !av;
  }
  function resizeAvatar(file, cb, onErr) {
    if (!looksLikeImage(file)) { if (onErr) onErr(); return; }
    const r = new FileReader();
    r.onerror = () => { if (onErr) onErr(); };
    r.onload = () => { const img = new Image(); img.onload = () => { try { const max = 320; let w = img.width, h = img.height; const sc = Math.min(max / w, max / h, 1); const cv = document.createElement('canvas'); cv.width = Math.max(1, Math.round(w * sc)); cv.height = Math.max(1, Math.round(h * sc)); cv.getContext('2d').drawImage(img, 0, 0, cv.width, cv.height); cb(canvasToJpeg(cv)); } catch (e) { if (onErr) onErr(); } }; img.onerror = () => { if (onErr) onErr(); }; img.src = r.result; };
    r.readAsDataURL(file);
  }
  function applyUserAvatar() {
    let av = ''; try { av = (JSON.parse(localStorage.getItem('munea.personProfile') || '{}')).avatar || ''; } catch (e) {}
    document.querySelectorAll('.init-ava.p-ama').forEach(el => {
      if (av) { el.style.backgroundImage = 'url(' + av + ')'; el.style.backgroundSize = 'cover'; el.style.backgroundPosition = 'center'; el.style.color = 'transparent'; }
      else { el.style.backgroundImage = ''; el.style.color = ''; }
    });
    renderAuthAvatar(authState(), isLoggedIn());
  }
  window.__muneaApplyUserAvatar = applyUserAvatar;
  if ($('#pfAvatarBtn')) $('#pfAvatarBtn').addEventListener('click', () => { if ($('#pfAvatarFile')) $('#pfAvatarFile').click(); });
  if ($('#pfAvatarFile')) $('#pfAvatarFile').addEventListener('change', e => { const f = e.target.files && e.target.files[0]; e.target.value = ''; if (!f) return; const box = $('#pfAvatar'); if (box) box.classList.add('processing'); resizeAvatar(f, dataUrl => { if (box) box.classList.remove('processing'); _pfPendingAvatar = dataUrl; renderPfAvatar(dataUrl); }, () => { if (box) box.classList.remove('processing'); toast('這張照片讀不到，換一張相簿裡的照片試試'); }); });
  if ($('#pfAvatarClear')) $('#pfAvatarClear').addEventListener('click', () => { _pfPendingAvatar = ''; renderPfAvatar('', ($('#pfNick') && $('#pfNick').value) || '我'); });
  applyUserAvatar();
  // 家庭照護圈
  const CIRCLE_LIMITS = { free: 1, plus: 4, pro: 12 };                       // 免費只含本人；Plus 4 人、Pro 12 人
  const CIRCLE_PLAN_LABEL = { free: '免費', plus: 'Plus', pro: 'Pro' };
  const PLAN_POINTS = { free: 0, plus: 150, pro: 300 };                       // 每月贈點
  function circlePlan() { try { return localStorage.getItem('munea.plan') || 'free'; } catch (e) { return 'free'; } }
  // 全家健康圈：就是一個家庭、大家平等（不分發起人/付款人/照護對象）；本人只標「本人」、其他人可移除
  // 7/9 正式化：不再預設示範四人家庭——圈子從「只有本人」開始，家人用邀請碼真的加進來
  function circleSelfMember() {
    let nm = '', ini = '我';
    try { const p = JSON.parse(localStorage.getItem('munea.personProfile') || '{}'); nm = (p.name || p.nick || '').trim(); ini = ((p.nick || nm || '我')[0]) || '我'; } catch (e) {}
    return { name: nm || '我', init: ini, tint: 'p-ama', self: true };
  }
  function loadCircle() { try { const v = JSON.parse(localStorage.getItem('munea.circleMembers')); return Array.isArray(v) && v.length ? v : [circleSelfMember()]; } catch (e) { return [circleSelfMember()]; } }
  function saveCircle(a2) {
    try { localStorage.setItem('munea.circleMembers', JSON.stringify(a2)); } catch (e) {}
    syncPush('circle', a2.map(m => ({ name: m.name, init: m.init, tint: m.tint })));   // 圈名單上雲（不帶「本人」標記）
  }
  window.__muneaAfterCircleSync = function () { try { renderFamRoster(); renderFcRoster(); updateSafetyCount(); } catch (e) {} };
  function renderFcRoster() {
    const box = $('#fcRoster'); if (!box) return;
    const members = loadCircle(); const plan = circlePlan(); const limit = CIRCLE_LIMITS[plan] || 4;
    const cnt = $('#fcCount'); if (cnt) cnt.textContent = members.length + '/' + limit + ' · ' + CIRCLE_PLAN_LABEL[plan];
    box.innerHTML = members.map(m => {
      const action = m.self ? '<span class="fc-you">本人</span>' : '<button type="button" class="fc-remove" data-name="' + m.name + '">移除</button>';
      return '<div class="rl"><span class="init-ava ' + m.tint + '">' + m.init + '</span><b>' + m.name + '</b>' + action + '</div>';
    }).join('');
    if (typeof window.__muneaApplyUserAvatar === 'function') window.__muneaApplyUserAvatar();
    const inv = $('#fcInviteBtn');
    if (inv) { const full = members.length >= limit; inv.textContent = full ? ('已達 ' + CIRCLE_PLAN_LABEL[plan] + ' 上限 · 升級可加更多') : '邀請家人加入'; inv.dataset.full = full ? '1' : ''; }
    const note = $('#invLimitNote'); if (note) note.textContent = '目前 ' + CIRCLE_PLAN_LABEL[plan] + ' 方案 · 家庭健康圈最多 ' + limit + ' 人';
  }
  // 移除家人：點一下「移除」→變紅「確定移除」、再點才移（App 內確認、不用系統醜彈窗）
  if ($('#fcRoster')) $('#fcRoster').addEventListener('click', e => {
    const rm = e.target.closest('.fc-remove'); if (!rm) return;
    if (rm.dataset.arm !== '1') { rm.dataset.arm = '1'; rm.classList.add('arm'); rm.textContent = '確定移除'; setTimeout(() => { rm.dataset.arm = ''; rm.classList.remove('arm'); rm.textContent = '移除'; }, 3000); return; }
    saveCircle(loadCircle().filter(m => m.name !== rm.dataset.name));
    renderFcRoster(); renderFamRoster(); updateSafetyCount();   // 家人頁與緊急聯絡人跟著同步（單一名單）
    toast('已把 ' + rm.dataset.name + ' 移出全家健康圈。');
  });
  if ($('#fcJoinBtn')) $('#fcJoinBtn').addEventListener('click', () => { if (!requireLoginForFamily('要加入家人的照護圈，先登入一下（換手機也找得回來）')) return; if (window.MMPLAN && window.MMPLAN.isFree()) { window.MMPLAN.upsell('join-circle'); return; } $('#famCircleModal').classList.remove('show'); if ($('#joinCircleModal')) $('#joinCircleModal').classList.add('show'); });
  if ($('#joinCircleClose')) $('#joinCircleClose').addEventListener('click', () => $('#joinCircleModal').classList.remove('show'));
  if ($('#joinCircleModal')) $('#joinCircleModal').addEventListener('click', e => { if (e.target === $('#joinCircleModal')) $('#joinCircleModal').classList.remove('show'); });
  if ($('#joinCircleBtn')) $('#joinCircleBtn').addEventListener('click', async () => {
    if (!requireLoginForFamily('要加入家人的照護圈，先登入一下')) return;   // 雙保險：訪客不能入別人的圈
    if (window.MMPLAN && window.MMPLAN.isFree()) { window.MMPLAN.upsell('join-circle'); return; }   // 雙保險：免費不能入別人的圈
    const code = ($('#joinCodeInput').value || '').trim();
    if (!code || code.replace(/\D/g, '').length < 4) { toast('把家人給你的邀請碼打進去（例：MUNEA-284753）'); return; }
    const btn = $('#joinCircleBtn');
    if (typeof setBtnBusy === 'function') setBtnBusy(btn, '加入中');
    try {
      const p = loadPersonProfile();
      // Use the common API helper so the verified bearer token is sent.  A
      // join code proves an invitation, never the caller's identity.
      const j = await brainPost('/family/invitations', { action: 'accept', shortCode: code, inviteeName: p.nick || p.name || '' });
      if (j && j.ok && j.invitation && j.invitation.familyGroupId) {
        try { localStorage.setItem('munea.familyGroupId', j.invitation.familyGroupId); } catch (e) {}
        // 把自己掛進這家的圈名單（雲端），對方裝置拉回來就看得到你
        await syncPullAll();
        const mem = loadCircle();
        const meName = p.nick || p.name || '我';
        if (!mem.some(m => m.name === meName)) { mem.push({ name: meName, init: meName[0], tint: 'p-bao', self: true }); saveCircle(mem); }
        renderFamRoster(); renderFcRoster();
        $('#joinCircleModal').classList.remove('show'); $('#joinCodeInput').value = '';
        toast('加入了！你們現在在同一個照護圈，動態會互相看得到。');
      } else if (j && j.error === 'invitation_expired') {
        toast('這組邀請碼過期了，請家人重新產一組給你。');
      } else if (j && j.error === 'circle_full') {
        toast('這個照護圈人數已滿，請家人升級方案後再邀請你。');
      } else {
        toast('找不到這組邀請碼，跟家人核對一下數字。');
      }
    } catch (e) {
      toast('現在連不上雲端，等網路好一點再試一次。');
    }
    if (typeof clearBtnBusy === 'function') clearBtnBusy(btn); else if (btn) btn.textContent = '加入照護圈';
  });
  if ($('#fcLeaveBtn')) $('#fcLeaveBtn').addEventListener('click', () => {
    const b = $('#fcLeaveBtn');
    if (b.dataset.arm !== '1') { b.dataset.arm = '1'; b.classList.add('arm'); b.textContent = '再按一次確認退出'; setTimeout(() => { b.dataset.arm = ''; b.classList.remove('arm'); b.textContent = '退出這個健康圈'; }, 4000); return; }
    b.dataset.arm = ''; b.classList.remove('arm'); b.textContent = '退出這個健康圈';
    $('#famCircleModal').classList.remove('show');
    toast('已退出這個健康圈。想再回來，請家人重新邀請你。');
  });
  if ($('#famCircleRow')) $('#famCircleRow').addEventListener('click', () => { renderFcRoster(); $('#famCircleModal').classList.add('show'); });
  // 移除家人／封鎖入口也放在家人頁顯眼處（不用鑽進設定才找得到，Edward 7/9 UGC 審核要求）——開的是同一個管理視窗
  if ($('#famManageBtn')) $('#famManageBtn').addEventListener('click', () => { renderFcRoster(); $('#famCircleModal').classList.add('show'); });
  if ($('#famCircleClose')) $('#famCircleClose').addEventListener('click', () => $('#famCircleModal').classList.remove('show'));
  if ($('#famCircleModal')) $('#famCircleModal').addEventListener('click', e => { if (e.target === $('#famCircleModal')) $('#famCircleModal').classList.remove('show'); });
  if ($('#fcInviteBtn')) $('#fcInviteBtn').addEventListener('click', e => { if (!requireLoginForFamily('要邀請家人連上你，先登入一下（這樣家人才連得到你）')) return; if (window.MMPLAN && window.MMPLAN.isFree()) { window.MMPLAN.upsell('family-invite'); return; } if (e.currentTarget.dataset.full) { toast('照護圈滿了，升級方案可以邀請更多家人。'); return; } $('#famCircleModal').classList.remove('show'); if ($('#inviteFamModal')) { fillInvCode(true); $('#inviteFamModal').classList.add('show'); } });
  // 邀請碼：跟雲端拿真的（6 位數、72 小時內有效、綁自己的家庭編號）；連不上雲端就先給本機碼並提示
  async function ensureCloudInvite() {
    // 已有 48 小時內拿到的雲端碼就沿用（雲端碼 72 小時有效，留 24 小時緩衝）
    try {
      const at = +(localStorage.getItem('munea.inviteCodeAt') || 0);
      const cached = localStorage.getItem('munea.inviteCode') || '';
      if (/^MUNEA-\d{6}$/.test(cached) && Date.now() - at < 172800000) return cached;
    } catch (e) {}
    try {
      // Plan, circle id, owner and member limit are derived on the server.
      // Do not send client-controlled authority fields with an invite request.
      const j = await brainPost('/family/invitations', { action: 'create' });
      if (j && j.ok && j.invitation && j.invitation.shortCode) {
        const code = 'MUNEA-' + j.invitation.shortCode;
        try { localStorage.setItem('munea.inviteCode', code); localStorage.setItem('munea.inviteCodeAt', String(Date.now())); } catch (e) {}
        return code;
      }
    } catch (e) {}
    return null;   // 連不上雲端
  }
  function fillInvCode(withCloud) {
    const el = $('#invCode'); if (!el) return;
    const note = $('#invTempNote');
    // There is no offline invitation mode: a locally generated code cannot
    // carry verified identity, entitlement or membership provisioning.
    el.textContent = withCloud ? '建立中…' : '—';
    if (note) note.style.display = 'none';
    if (!withCloud) return;
    ensureCloudInvite().then(code => {
      if (code) { el.textContent = code; if (note) note.style.display = 'none'; }             // 拿到正式碼＝乾淨顯示
      else {
        el.textContent = '—';
        if (note) { note.textContent = '需要連上雲端並完成帳號驗證，才能建立安全的邀請碼。'; note.style.display = ''; }
      }
    });
  }
  if ($('#inviteFamModal')) $('#inviteFamModal').addEventListener('click', e => { if (e.target === $('#inviteFamModal')) $('#inviteFamModal').classList.remove('show'); });
  if ($('#inviteCloseX')) $('#inviteCloseX').addEventListener('click', () => $('#inviteFamModal').classList.remove('show'));
  function shownInvCode() {
    const code = ((($('#invCode') || {}).textContent) || '').trim();
    return /^MUNEA-\d{6}$/.test(code) ? code : '';
  }
  if ($('#invShareBtn')) $('#invShareBtn').addEventListener('click', () => {
    if (!shownInvCode()) { toast('邀請碼還沒建立好，請確認網路與登入狀態。'); return; }
    const text = '我在用「沐寧 Munea」，AI 健康管家陪全家顧健康。我的家庭圈邀請碼是 ' + shownInvCode() + '，在沐寧的「家人 → 加入照護圈」輸入，我們就連上了！';
    if (navigator.share) { navigator.share({ text }).catch(() => {}); }
    else { location.href = 'sms:?&body=' + encodeURIComponent(text); }
  });
  if ($('#invCopyBtn')) $('#invCopyBtn').addEventListener('click', () => {
    const code = shownInvCode();
    if (!code) { toast('邀請碼還沒建立好，請確認網路與登入狀態。'); return; }
    (navigator.clipboard && navigator.clipboard.writeText ? navigator.clipboard.writeText(code) : Promise.reject()).then(
      () => toast('邀請碼複製好了，貼給家人'),
      () => toast('你的邀請碼：' + code)
    );
  });
  fillInvCode(false);
  if ($('#connectBack')) $('#connectBack').addEventListener('click', () => showView(window.__connectFrom || 'status'));
  $$('#connect .cn-btn').forEach(b => b.addEventListener('click', async () => {
    // Apple 健康：在 App 裡就真的去要 iPhone 授權；網頁預覽則走原本示範切換
    if (b.id === 'cnHealthBtn' && window.MuneaHealth && window.MuneaHealth.available()) {
      setBtnBusy(b, '連接中');
      const r = await window.MuneaHealth.connect();
      if (r && r.ok) {
        clearBtnBusy(b, '✓ 已連接');
        b.classList.add('done');
        trackProductEvent('health_connected', {});
        hint('好，連上 Apple 健康了，步數和身體數據我會自動幫你留意。');
      } else {
        clearBtnBusy(b, b.dataset.label || '連接');
        hint(r && r.reason === 'unavailable' ? '這台裝置沒有健康資料可讀。' : '沒有連上，晚點在「連接裝置」再試一次也可以。');
      }
      return;
    }
    const on = b.classList.toggle('done');
    b.textContent = on ? '✓ 已連接' : (b.dataset.label || '連接');
    if (on) { hint('好，連上了，之後健康資料我會自動留意。'); try { localStorage.setItem('munea.devicesOn', '1'); } catch (e2) {} }
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
    hint(`送出去了，${cname()}會在家人動態幫你帶到。`);
    const who = document.getElementById('ptName')?.textContent || '家人';
    pushFamilyFeed(`<b>你</b>給${who}${b.dataset.react || '送上心意'}，${cname()}會在下次聊天時帶到`);
  });

  // 全家健康圈：切換成員看健康（7/9 正式化：示範看板已拆、一律吃真同步數據）
  // 家人真數據（7/9 Edward「數據真同步」）：從家人水管拉回的 munea.famVitals 依名字對人
  function famVitalsFor(name) {
    try {
      const all = JSON.parse(localStorage.getItem('munea.famVitals') || '{}');
      let best = null;
      for (const pid in all) {
        const v = all[pid];
        if (!v || typeof v !== 'object') continue;
        if ((v.name && v.name === name) || (v.nick && v.nick === name)) {
          if (!best || (v.updatedAt || 0) > (best.updatedAt || 0)) best = v;
        }
      }
      return best;
    } catch (e) { return null; }
  }
  // 真數據 → 顯示格式（門檻白話跟狀態頁同一套規則）
  function vitalsToDisplay(v) {
    if (!v) return null;
    const sys = +v.bpSys || 0, dia = +v.bpDia || 0, hr = +v.hr || 0, spo2 = +v.spo2 || 0, sleep = +v.sleepHours || 0, steps = +v.steps || 0;
    const d = { bp: null, hr: null, spo2: null, sleep: null, steps: null, med: null, day: v.day || '' };
    if (sys && dia) {
      const hi = sys >= 140 || dia >= 90, lo = sys < 90;
      d.bp = { n: String(Math.round(sys)), u: '/' + Math.round(dia) + ' mmHg', chip: hi ? '偏高' : lo ? '偏低' : '穩定', warn: (hi || lo) ? 1 : 0, sub: hi ? '比平常高一點，多留意' : lo ? '偏低一些，起身動作放慢' : '正常範圍內' };
    }
    if (hr) {
      const odd = hr < 50 || hr > 100;
      d.hr = { n: String(Math.round(hr)), chip: odd ? '注意' : '正常', warn: odd ? 1 : 0, sub: '靜息心率' };
    }
    if (spo2) d.spo2 = String(Math.round(spo2));
    if (sleep) d.sleep = String(Math.round(sleep * 10) / 10);
    if (steps) d.steps = Math.round(steps).toLocaleString();
    return (d.bp || d.hr || d.spo2 || d.sleep || d.steps) ? d : null;
  }
  function renderPersonStats(p) {
    const grid = $('#personGrid');
    if (!grid) return;
    const d = vitalsToDisplay(famVitalsFor(p));   // 只認真數據；沒有＝老實說還沒有
    if (!d) { grid.innerHTML = '<div class="card" style="padding:16px;margin-bottom:16px;font-size:14.5px;color:var(--muted);text-align:center;line-height:1.7">等' + (p || '家人') + '連上沐寧，健康數據就會出現在這裡</div>'; return; }
    if (!d.bp) d.bp = { n: '—', u: '', chip: '未提供', warn: 0, sub: '他的裝置還沒帶到血壓' };
    if (!d.hr) d.hr = { n: '—', chip: '未提供', warn: 0, sub: '他的裝置還沒帶到心率' };
    if (!d.spo2) d.spo2 = '—';
    if (!d.sleep) d.sleep = '—';
    if (!d.steps) d.steps = '—';
    // 標籤配色照狀態頁規範：警示=珊瑚、血壓正常=薄荷綠、心率正常=淡珊瑚（7/9 Edward 對齊設計規範）
    const chip = (t, warn, tone) => { const coral = warn || tone === 'coral'; return '<span class="chip" style="flex-shrink:0;background:' + (coral ? 'var(--coral-soft)' : 'var(--mint)') + ';color:' + (coral ? 'var(--coral-d)' : 'var(--teal-dd)') + '">' + t + '</span>'; };
    const medCard = d.med
      ? '<div class="card" style="padding:14px 15px;margin-bottom:11px"><div class="row" style="justify-content:space-between;gap:10px">' +
        '<div class="row" style="gap:11px;min-width:0"><span style="flex:0 0 38px;width:38px;height:38px;border-radius:12px;background:' + (d.med.warn ? 'var(--coral)' : 'var(--teal)') + ';display:grid;place-items:center;color:#fff"><svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M10.5 20.5 20 11a4.95 4.95 0 1 0-7-7l-9.5 9.5a4.95 4.95 0 1 0 7 7Z"/><path d="m8.5 8.5 7 7"/></svg></span>' +
        '<div style="min-width:0"><div style="font-weight:700;font-size:14.5px">用藥狀態</div><div style="font-size:14px;color:var(--muted);margin-top:1px">' + d.med.sub + '</div></div></div>' + chip(d.med.chip, d.med.warn) + '</div></div>'
      : '';
    grid.innerHTML = medCard +
      '<div class="row" style="gap:11px;margin-bottom:11px;align-items:stretch">' +
        '<div class="card" style="padding:15px;flex:1">' +
          '<div class="row" style="justify-content:space-between;margin-bottom:12px"><span style="width:32px;height:32px;border-radius:10px;background:var(--teal);display:grid;place-items:center;color:#fff"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg></span>' + chip(d.bp.chip, d.bp.warn) + '</div>' +
          '<div style="font-size:14px;color:var(--muted);margin-bottom:3px">血壓</div>' +
          '<div><span class="mnum" style="font-size:26px;color:var(--teal-dd)">' + d.bp.n + '</span><span style="font-size:14px;color:var(--muted)">' + d.bp.u + '</span></div>' +
          '<div style="font-size:14px;color:var(--muted);margin-top:6px">' + d.bp.sub + '</div></div>' +
        '<div class="card" style="padding:15px;flex:1">' +
          '<div class="row" style="justify-content:space-between;margin-bottom:12px"><span style="width:32px;height:32px;border-radius:10px;background:var(--coral);display:grid;place-items:center;color:#fff"><svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M20.8 8.6c0-3.2-2.5-5.4-5.3-5.4-1.6 0-2.9.7-3.5 1.9-.6-1.2-1.9-1.9-3.5-1.9-2.8 0-5.3 2.2-5.3 5.4C3.2 14 12 20 12 20s8.8-6 8.8-11.4Z"/></svg></span>' + chip(d.hr.chip, d.hr.warn, 'coral') + '</div>' +
          '<div style="font-size:14px;color:var(--muted);margin-bottom:3px">心率</div>' +
          '<div><span class="mnum" style="font-size:26px;color:var(--coral-d)">' + d.hr.n + '</span><span style="font-size:14px;color:var(--muted)"> bpm</span></div>' +
          '<div style="font-size:14px;color:var(--muted);margin-top:6px">' + d.hr.sub + '</div></div>' +
      '</div>' +
      '<div class="card" style="display:flex;align-items:stretch;padding:0;overflow:hidden;margin-bottom:16px">' +
        '<div style="flex:1;padding:13px 14px"><div style="display:flex;align-items:center;gap:6px;margin-bottom:8px"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--teal)" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11Z"/></svg><span style="font-size:14px;color:var(--muted)">血氧</span></div><div><span class="mnum" style="font-size:21px;color:var(--teal-dd)">' + d.spo2 + '</span><span style="font-size:14px;color:var(--muted)"> %</span></div></div>' +
        '<div style="width:1px;background:var(--line);margin:12px 0"></div>' +
        '<div style="flex:1;padding:13px 14px"><div style="display:flex;align-items:center;gap:6px;margin-bottom:8px"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#C79A3B" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/></svg><span style="font-size:14px;color:var(--muted)">昨晚睡眠</span></div><div><span class="mnum" style="font-size:21px;color:#8A6410">' + d.sleep + '</span><span style="font-size:14px;color:var(--muted)"> 時</span></div></div>' +
        '<div style="width:1px;background:var(--line);margin:12px 0"></div>' +
        '<div style="flex:1;padding:13px 14px"><div style="display:flex;align-items:center;gap:6px;margin-bottom:8px"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--teal-dd)" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 16v-2.4c0-2.1-1-3.1-1-5.6 0-2.7 1.5-6 4.5-6C9.4 2 10 3.8 10 5.5c0 3.1-2 5.7-2 8.7V16a2 2 0 1 1-4 0Z"/><path d="M20 20v-2.4c0-2.1 1-3.1 1-5.6 0-2.7-1.5-6-4.5-6C14.6 6 14 7.8 14 9.5c0 3.1 2 5.7 2 8.7V20a2 2 0 1 0 4 0Z"/></svg><span style="font-size:14px;color:var(--muted)">運動量</span></div><div><span class="mnum" style="font-size:21px;color:var(--teal-dd)">' + d.steps + '</span><span style="font-size:14px;color:var(--muted)"> 步</span></div></div>' +
      '</div>';
  }
  function renderPersonMood(p) {
    // 正式版（7/9 Edward 拆示範）：心情觀察只認真資料；跨裝置的心情摘要水管還沒接、一律誠實空狀態
    if ($('#mcTitle')) $('#mcTitle').textContent = '還沒有觀察';
    if ($('#mcSub')) $('#mcSub').textContent = '等' + (p || '家人') + '開始用沐寧聊天，觀察會出現在這裡';
    if ($('#mcObs')) $('#mcObs').innerHTML = '';
    if ($('#mcTopics')) $('#mcTopics').innerHTML = '';
  }

  // 家人頁名單跟「設定 → 全家健康圈」吃同一份資料（兩本帳合一）：圈裡移除了人，這裡自動跟著消失
  // （7/9 拆示範：稱謂/狀態不再寫死——狀態從真數據推、稱謂一律「家人」）
  let FAM_ORDER = [];   // 本人資料在「狀態」頁，家人頁不重複顯示；實際名單由 renderFamRoster 重算
  let currentPerson = '';
  function famInit(m) { return m.init || (m.name || '')[0] || ''; }
  function renderFamRoster() {
    const mem = loadCircle().filter(m => !m.self);
    FAM_ORDER = mem.map(m => m.name);
    const fs = $('#famSwitch');
    if (fs) {
      const allBtn = fs.querySelector('[data-person="all"]');
      const invBtn = fs.querySelector('[data-person="invite"]');
      fs.innerHTML = (allBtn ? allBtn.outerHTML : '') + mem.map(m =>
        '<button class="fam-switch-item" data-person="' + m.name + '" data-rel="家人" data-init="' + famInit(m) + '" data-tint="' + (m.tint || '') + '"><span class="fs-av"><span class="init-ava ' + (m.tint || '') + '">' + famInit(m) + '</span></span><span class="fs-name">' + m.name + '</span></button>'
      ).join('') + (invBtn ? invBtn.outerHTML : '');
    }
    const hl = $('#healthList');
    if (hl) hl.innerHTML = mem.length ? mem.map(m => {
      // 7/9 正式化：狀態從真同步數據推（有數據＝安好＋最後更新日；沒有＝老實說等他連上）
      const rv = famVitalsFor(m.name);
      const s = rv
        ? { pill: 'calm', pillT: '平穩', txt: '數據更新於 ' + (rv.day || '近日'), st: 'ok', stT: '安好' }
        : { pill: 'calm', pillT: '—', txt: '等他加入連上，就看得到狀態', st: 'ok', stT: '未連' };
      return '<div class="health-row" data-person="' + m.name + '" data-rel="家人" data-init="' + famInit(m) + '" data-tint="' + (m.tint || '') + '">' +
        '<span class="hr-av"><span class="init-ava ' + (m.tint || '') + '">' + famInit(m) + '</span></span>' +
        '<div class="hr-info"><div class="hr-name">' + m.name + '</div><div class="hr-state"><em class="mood-pill ' + s.pill + '">' + s.pillT + '</em>' + s.txt + '</div></div>' +
        '<div class="hr-status ' + s.st + '"><span class="hr-dot"></span><span class="hr-slabel">' + s.stT + '</span></div></div>';
    }).join('') : '<p class="modal-sub" style="margin:6px 2px">圈裡還沒有家人，點上面「邀請」把家人拉進來。</p>';
    if (currentPerson && !FAM_ORDER.includes(currentPerson)) { currentPerson = FAM_ORDER[0] || ''; if ($('#viewPerson') && $('#viewPerson').classList.contains('active')) showFamAll(); }
    renderFamDots();
  }
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
    const v = $('#viewPerson');
    const wasActive = v && v.classList.contains('active');
    $('#viewAll').classList.remove('active');
    if (v) v.classList.add('active');
    if ($('#ptName')) $('#ptName').textContent = p;   // 名字只在這裡出現一次（不再放稱謂副標、不放說明文字）
    renderPersonStats(p);
    renderPersonMood(p);   // 心情監測每個人都有（Edward 7/9）
    renderFamTrends();     // 活動量/睡眠/心情圖表跟著換人（跟狀態頁同款圖）
    if ($('#moodToday')) $('#moodToday').style.display = '';
    const pa = $('#ptAv');
    if (pa) { pa.textContent = init || (p || '')[0] || ''; pa.className = 'init-ava init-ava-lg ' + (tint || ''); }
    $$('.fam-switch-item').forEach(b => b.classList.toggle('active', b.dataset.person === p));
    // 左右切換鍵：到邊就變淡（美華在最左、小寶在最右）
    const idx = FAM_ORDER.indexOf(p);
    if ($('#ptPrev')) $('#ptPrev').disabled = idx <= 0;
    if ($('#ptNext')) $('#ptNext').disabled = idx < 0 || idx >= FAM_ORDER.length - 1;
    // 從全家頁進來＝整頁置頂（第一眼就看到這是誰）；左右換人保持原捲動位置（治晃動 · Edward 7/9）
    if (!wasActive) { const sc = $('#family'); if (sc) sc.scrollTop = 0; }
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
  // 左右切換鍵＝跟左右滑同一件事（看得到的入口 · Edward 7/9）
  if ($('#ptPrev')) $('#ptPrev').addEventListener('click', () => switchPerson(-1));
  if ($('#ptNext')) $('#ptNext').addEventListener('click', () => switchPerson(1));
  if ($('#moodTrendBtn')) $('#moodTrendBtn').addEventListener('click', () => {
    $('#viewPerson').classList.remove('active');
    $('#viewMood').classList.add('active');
    const n = $('#ptName') ? $('#ptName').textContent : '家人';
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
  if ($('#medSlots')) $('#medSlots').addEventListener('click', e => {
    const thumb = e.target.closest('.ms-thumb');
    if (thumb) { const _m = loadMeds().find(x => x.name === thumb.dataset.name); if (_m && _m.photo) showMedPhoto(_m.photo, _m.name); return; }
    const tb = e.target.closest('.ms-tbtn');
    if (tb) {
      const rt = loadRoutine();
      rt[tb.dataset.k] = shiftTime(rt[tb.dataset.k], +tb.dataset.m);
      saveRoutine(rt);
      renderMedSlots();
      return;
    }
    const del = e.target.closest('.ms-del');
    if (del) {
      let meds = loadMeds();
      let changedMed = null, archivedMed = null;
      meds = meds.map(m => {
        if (m.name !== del.dataset.name) return m;
        const rest = String(m.time).split('、').map(x => x.trim()).filter(x => x && x !== del.dataset.slot);
        if (rest.length) {
          changedMed = Object.assign({}, m, { time: rest.join('、') });
          return changedMed;
        }
        archivedMed = m;
        return null;
      }).filter(Boolean);
      try { localStorage.setItem('munea.meds', JSON.stringify(meds)); syncPush('meds', meds); } catch (e2) {}
      if (changedMed) syncMedicationReminder(changedMed);
      if (archivedMed) archiveRoutineReminder(archivedMed.id || stableReminderId('med_', [archivedMed.name, archivedMed.time, archivedMed.days, archivedMed.by].join('|')));
      updateMedCount();
      renderMedSlots();
      toast('拿掉了，這個時段不再提醒這種藥。');
    }
  });
  if ($('#medSlots')) $('#medSlots').addEventListener('change', e => {
    const ti = e.target.closest('input.ms-time');
    if (ti && ti.value) {
      const rt = loadRoutine();
      rt[ti.dataset.k] = shiftTime(ti.value, -(+ti.dataset.off || 0));
      saveRoutine(rt);
      renderMedSlots();
      updateMedCount();
    }
  });
  let _medPendingPhoto = '';
  if ($('#medPhotoBtn')) $('#medPhotoBtn').addEventListener('click', () => { if ($('#medPhotoFile')) $('#medPhotoFile').click(); });
  if ($('#medPhotoFile')) $('#medPhotoFile').addEventListener('change', e => { const f = e.target.files && e.target.files[0]; e.target.value = ''; if (!f) return; const box = $('#medPhotoBox'); if (box) box.classList.add('processing'); resizeSquare(f, url => { if (box) box.classList.remove('processing'); _medPendingPhoto = url; if (box) { box.style.backgroundImage = 'url(' + url + ')'; box.classList.add('has'); } }, () => { if (box) box.classList.remove('processing'); toast('這張照片讀不到，換一張相簿裡的照片試試'); }); });
  if ($('#medAddBtn')) $('#medAddBtn').addEventListener('click', () => {
    const name = $('#medName').value.trim();
    const times = [...document.querySelectorAll('#medTimeChips .mchip.on')].map(b => b.dataset.t);
    const days = document.querySelector('#medDayChips .mchip.on')?.dataset.d || '長期';
    if (!name) { toast('先寫藥名（照藥袋抄就好）'); return; }
    if (!times.length) { toast('點一下什麼時候吃（可以選好幾個）'); return; }
    const meds = loadMeds();
    const med = { name, time: times.join('、'), days, by: '美華', photo: _medPendingPhoto };
    ensureMedReminderId(med);
    meds.push(med);
    try { localStorage.setItem('munea.meds', JSON.stringify(meds)); syncPush('meds', meds); } catch (e) {}
    syncMedicationReminder(med);
    $('#medName').value = '';
    _medPendingPhoto = ''; { const _b = $('#medPhotoBox'); if (_b) { _b.style.backgroundImage = ''; _b.classList.remove('has'); } }
    document.querySelectorAll('#medTimeChips .mchip.on').forEach(x => x.classList.remove('on'));
    renderMedList();
    updateMedCount();
    toast('好，' + cname() + '會在' + times.join('、') + '提醒吃「' + name + '」，時間照你的作息');
  });
  if ($('#medEntryStatus')) $('#medEntryStatus').addEventListener('click', () => { renderMedList(); $('#medMgrModal').classList.add('show'); });
  if ($('#medTileBtn')) $('#medTileBtn').addEventListener('click', () => { renderMedList(); $('#medMgrModal').classList.add('show'); });
  initHealthDashboard();
  
  if ($('#topUpBtn')) $('#topUpBtn').addEventListener('click', () => $('#topUpModal').classList.add('show'));
  if ($('#topUpClose')) $('#topUpClose').addEventListener('click', () => $('#topUpModal').classList.remove('show'));
  if ($('#topUpModal')) $('#topUpModal').addEventListener('click', e => {
    if (e.target === $('#topUpModal')) { $('#topUpModal').classList.remove('show'); return; }
    const card = e.target.closest('.tu-card');
    if (card) { document.querySelectorAll('.tu-card').forEach(x => x.classList.remove('on')); card.classList.add('on'); }
  });
  if ($('#tuBuyBtn')) $('#tuBuyBtn').addEventListener('click', async () => {
    const selCard = document.querySelector('.tu-card.on');
    const p = selCard ? +selCard.dataset.p : 0;
    if (!p) { toast('先選一包點數'); return; }
    // App 裡走真蘋果付款；點數入帳由 __muneaApplyPurchase 統一做
    if (window.MuneaStore && window.MuneaStore.available()) {
      const b = $('#tuBuyBtn');
      setBtnBusy(b, '連到 App Store');
      const r = await window.MuneaStore.purchase(window.MuneaStore.ptsId(p));
      clearBtnBusy(b);
      if (r.ok) $('#topUpModal').classList.remove('show');
      else if (r.reason !== 'cancelled') toast('付款沒有完成，晚點再試一次就好。');
      return;
    }
    try { localStorage.setItem('munea.ptsBought', String((POINTS.bought || 0) + p)); } catch (e2) {}
    pushWallet();
    renderPoints();
    $('#topUpModal').classList.remove('show');
    toast('買好了，' + p.toLocaleString() + ' 點入帳（餘額已更新），這批不會過期');
  });
  // ===== 訂閱頁：比較表 + 月/年繳切換 + 訂閱鈕（金額為暫定、待 Edward 拍板）=====
  // 年繳＝月費 ×12 打 8 折（省 20%）；金額暫定、待 Edward 拍板
  const SUB_PRICE = { plus: { month: 599, year: 5750 }, pro: { month: 1199, year: 11500 } };
  const PT_PRICE = { 150: 500, 300: 1000, 600: 2000, 1000: 3000 };
  let _subPlan = 'pro', _subCyc = 'month', _planPick = null;
  function fmtPrice(plan, cyc) { return 'NT$' + SUB_PRICE[plan][cyc].toLocaleString() + (cyc === 'year' ? '／年' : '／月'); }
  function renderSubUI() {
    const cur = circlePlan();
    [['plus', 'Plus'], ['pro', 'Pro']].forEach(([pl, Cap]) => {
      const priceEl = $('#price' + Cap);
      if (priceEl) priceEl.innerHTML = 'NT$' + SUB_PRICE[pl][_subCyc].toLocaleString() + '<small>' + (_subCyc === 'year' ? '/年' : '/月') + '</small>';
      const saveEl = $('#save' + Cap);
      if (saveEl) {
        if (_subCyc === 'year') { const save = SUB_PRICE[pl].month * 12 - SUB_PRICE[pl].year; saveEl.textContent = '一年省 NT$' + save.toLocaleString(); saveEl.style.display = ''; }
        else saveEl.style.display = 'none';
      }
    });
    document.querySelectorAll('.ppk').forEach(c => { c.classList.toggle('sel', c.dataset.t === _subPlan); c.classList.toggle('is-cur', c.dataset.t === cur); });
    const cta = $('#subCta');
    if (cta) {
      if (_subPlan === cur) cta.textContent = '你目前就是 ' + CIRCLE_PLAN_LABEL[_subPlan] + ' 方案';
      else cta.textContent = (PLAN_POINTS[_subPlan] > PLAN_POINTS[cur] ? '升級 ' : '改用 ') + CIRCLE_PLAN_LABEL[_subPlan] + ' · ' + fmtPrice(_subPlan, _subCyc);
    }
  }
  function renderPlanState() {
    const plan = circlePlan();
    const label = CIRCLE_PLAN_LABEL[plan] || 'Plus';
    const pts = Object.prototype.hasOwnProperty.call(PLAN_POINTS, plan) ? PLAN_POINTS[plan] : PLAN_POINTS.plus;
    const sn = $('#setPlanName'); if (sn) sn.textContent = label + ' 方案';
    // 帳號卡右上角唯一的身份標籤（開發測試帳號會蓋成 TEST）
    renderMemBadge(plan);
    const sg = $('#setPlanGrant'); if (sg) sg.textContent = pts;
    if (POINTS.total !== pts) { POINTS.total = pts; if (POINTS.used > pts) POINTS.used = Math.round(pts * 0.3); }
    if (typeof renderPoints === 'function') renderPoints();
    const _isFreeP = plan === 'free';
    const _card = document.querySelector('.plan-card');
    if (_card) {
      const _lbl = _card.querySelector('.pts-label'), _bar = _card.querySelector('.pts-bar'), _note = _card.querySelector('.pts-note');
      if (_lbl) _lbl.style.display = _isFreeP ? 'none' : '';
      if (_bar) _bar.style.display = _isFreeP ? 'none' : '';
      if (_note) _note.textContent = _isFreeP
        ? '目前是免費方案 · 綁定帳號送單次 5 分鐘聊天體驗。升級 Plus／Pro 改用點數聊、看更久的紀錄、邀家人進照護圈。'
        : (pts + ' 點約可聊 ' + pts + ' 分鐘；聊天用點數，用完補一下就能繼續。');
    }
    const _tBtn = $('#topUpBtn'); if (_tBtn) _tBtn.style.display = _isFreeP ? 'none' : '';
    const _mBtn = $('#managePlanBtn'); if (_mBtn) _mBtn.textContent = _isFreeP ? '升級方案' : '訂閱方案';
    renderSubUI();
  }
  // 分段 tab（訂閱方案 / 點數購買）
  document.querySelectorAll('.sseg-btn').forEach((b, i) => b.addEventListener('click', () => {
    document.querySelectorAll('.sseg-btn').forEach(x => x.classList.toggle('on', x === b));
    const th = $('#ssegThumb'); if (th) th.style.transform = 'translateX(' + (i * 100) + '%)';
    const pane = b.dataset.pane;
    if ($('#subPlans')) $('#subPlans').style.display = pane === 'plans' ? '' : 'none';
    if ($('#subPoints')) $('#subPoints').style.display = pane === 'points' ? '' : 'none';
  }));
  // 月/年繳
  document.querySelectorAll('.scyc-btn').forEach((b, i) => b.addEventListener('click', () => {
    document.querySelectorAll('.scyc-btn').forEach(x => x.classList.toggle('on', x === b));
    const th = $('#scycThumb'); if (th) th.style.transform = 'translateX(' + (i * 100) + '%)';
    _subCyc = b.dataset.cyc; renderSubUI();
  }));
  // 選方案欄
  document.querySelectorAll('.ppk').forEach(c => c.addEventListener('click', () => { _subPlan = c.dataset.t; renderSubUI(); }));
  // 訂閱鈕
  if ($('#subCta')) $('#subCta').addEventListener('click', () => {
    const cur = circlePlan();
    if (_subPlan === cur) { toast('你目前就是 ' + CIRCLE_PLAN_LABEL[_subPlan] + ' 方案'); return; }
    _planPick = _subPlan;
    $('#planConfirmText').innerHTML = '訂閱「<b>' + CIRCLE_PLAN_LABEL[_subPlan] + '</b>」· ' + fmtPrice(_subPlan, _subCyc) + '<br>每月 ' + PLAN_POINTS[_subPlan] + ' 點、家庭健康圈最多 ' + CIRCLE_LIMITS[_subPlan] + ' 人。';
    $('#planConfirm').style.display = '';
  });
  if ($('#planYes')) $('#planYes').addEventListener('click', async () => {
    if (!_planPick) return;
    // App 裡走真蘋果付款（StoreKit）；網頁預覽維持示範切換
    if (window.MuneaStore && window.MuneaStore.available()) {
      const pid = window.MuneaStore.subId(_planPick, _subCyc);
      const b = $('#planYes');
      setBtnBusy(b, '連到 App Store');
      const r = await window.MuneaStore.purchase(pid);
      clearBtnBusy(b, '確認變更');
      if (r.ok) { $('#planConfirm').style.display = 'none'; _planPick = null; } // 生效與提示由 __muneaApplyPurchase 統一做
      else if (r.reason === 'cancelled') toast('沒關係，想好再訂就好。');
      else if (r.reason === 'pending') { toast('付款送出了，等核准後會自動生效。'); $('#planConfirm').style.display = 'none'; _planPick = null; }
      else toast('付款沒有完成，晚點再試一次就好。');
      return;
    }
    try { localStorage.setItem('munea.plan', _planPick); localStorage.removeItem('munea.planNext'); } catch (e2) {}
    $('#planConfirm').style.display = 'none';
    renderPlanState();
    if (typeof renderFcRoster === 'function') { try { renderFcRoster(); } catch (e3) {} }
    toast(subscriptionSuccessMessage(_planPick), 4200);
    _planPick = null;
  });
  if ($('#planNo')) $('#planNo').addEventListener('click', () => { $('#planConfirm').style.display = 'none'; _planPick = null; });
  if ($('#planCancelBtn')) $('#planCancelBtn').addEventListener('click', async () => {
    const b = $('#planCancelBtn');
    if (window.MuneaStore && window.MuneaStore.available() && typeof window.MuneaStore.manageSubscriptions === 'function') {
      setBtnBusy(b, '開啟 Apple 訂閱');
      const result = await window.MuneaStore.manageSubscriptions();
      clearBtnBusy(b, '取消訂閱');
      if (!result.ok) toast('暫時無法開啟 Apple 訂閱管理，請到 iPhone「設定 → Apple 帳戶 → 訂閱項目」操作');
      return;
    }
    toast('請到 iPhone「設定 → Apple 帳戶 → 訂閱項目」管理或取消訂閱');
  });
  if ($('#managePlanBtn')) $('#managePlanBtn').addEventListener('click', () => {
    renderSubUI();
    $('#planModal').classList.add('show');
    void refreshServerPlanEntitlement();
  });
  if ($('#planClose')) $('#planClose').addEventListener('click', () => $('#planModal').classList.remove('show'));
  // 恢復購買（蘋果硬規定）：原生付款層在（真機）→ 交給它；不在（網頁預覽）→ 誠實說明
  // 真機直接走 MuneaStore.restore；每筆交易仍須先經伺服器驗證才套用權益。
  if ($('#restoreBtn')) $('#restoreBtn').addEventListener('click', async () => {
    const b = $('#restoreBtn');
    if (!(window.MuneaStore && window.MuneaStore.available() && typeof window.MuneaStore.restore === 'function')) {
      toast('恢復購買只能在 iPhone App 內使用');
      return;
    }
    setBtnBusy(b, '正在向 Apple 查詢');
    const result = await window.MuneaStore.restore();
    clearBtnBusy(b, '恢復購買');
    if (result.ok) toast('購買已恢復，方案與帳號權益正在同步');
    else if (result.reason === 'signin_required') toast('請先登入原本購買時使用的沐寧帳號');
    else if (result.reason === 'none') toast('這個 Apple 帳號目前沒有可恢復的訂閱');
    else toast('恢復購買沒有完成，請確認網路後再試一次');
  });
  if ($('#legalTermsLink')) $('#legalTermsLink').addEventListener('click', e => { e.preventDefault(); openReader('terms'); });
  if ($('#legalPrivacyLink')) $('#legalPrivacyLink').addEventListener('click', e => { e.preventDefault(); openReader('privacy'); });
  // 點數購買
  if ($('#subPoints')) $('#subPoints').addEventListener('click', e => {
    const card = e.target.closest('.tu-card'); if (!card) return;
    $('#subPoints').querySelectorAll('.tu-card').forEach(x => x.classList.remove('on')); card.classList.add('on');
    const p = +card.dataset.p; const cta = $('#tuBuyBtn2'); if (cta) cta.textContent = '直接購買 ' + p.toLocaleString() + ' 點 · NT$' + (PT_PRICE[p] || 0).toLocaleString();
  });
  if ($('#tuBuyBtn2')) $('#tuBuyBtn2').addEventListener('click', async () => {
    const sel = document.querySelector('#subPoints .tu-card.on');
    const p = sel ? +sel.dataset.p : 0;
    if (!p) { toast('先選一包點數'); return; }
    if (window.MuneaStore && window.MuneaStore.available()) {
      const b = $('#tuBuyBtn2');
      setBtnBusy(b, '連到 App Store');
      const r = await window.MuneaStore.purchase(window.MuneaStore.ptsId(p));
      clearBtnBusy(b);
      if (!r.ok && r.reason !== 'cancelled') toast('付款沒有完成，晚點再試一次就好。');
      return;
    }
    try { localStorage.setItem('munea.ptsBought', String((POINTS.bought || 0) + p)); } catch (e2) {}
    pushWallet(); renderPoints();
    toast('買好了，' + p.toLocaleString() + ' 點入帳，這批不會過期');
  });
  renderPlanState();
  // 蘋果內購（StoreKit）購買成功 → 前端生效的唯一入口。
  // Mac 原生端付款成功（含沙盒測試）就呼叫這支，傳 App Store Connect 的產品 ID（見金流步驟單第 4 步表）。
  // 回傳 true=已生效、false=不認得的產品 ID。示範按鈕之後換真金流時，也一律改走這支。
  window.__muneaApplyPurchase = function (productId, purchase) {
    const pid = String(productId || '');
    const SUB_PID = {
      'net.munea.app.plus.monthly': 'plus', 'net.munea.app.plus.yearly': 'plus',
      'net.munea.app.pro.monthly': 'pro', 'net.munea.app.pro.yearly': 'pro'
    };
    const PT_PID = { 'net.munea.app.points.200': 150, 'net.munea.app.points.500': 300, 'net.munea.app.points.1000': 600, 'net.munea.app.points.1800': 1000 };
    if (SUB_PID[pid]) {
      try { localStorage.setItem('munea.plan', SUB_PID[pid]); localStorage.removeItem('munea.planNext'); } catch (e) {}
      trackProductEvent('subscription_purchased', { productId: pid, plan: SUB_PID[pid] });
      renderSubscriptionEndDate(purchase && purchase.billing && purchase.billing.subscription);
      renderPlanState();
      if (typeof renderFcRoster === 'function') { try { renderFcRoster(); } catch (e2) {} }
      void refreshServerPlanEntitlement();
      toast(subscriptionSuccessMessage(SUB_PID[pid], purchase && purchase.billing && purchase.billing.subscription), 4200);
      return true;
    }
    if (PT_PID[pid]) {
      try { localStorage.setItem('munea.ptsBought', String((POINTS.bought || 0) + PT_PID[pid])); } catch (e3) {}
      trackProductEvent('points_purchased', { productId: pid, points: PT_PID[pid] });
      pushWallet(); renderPoints();
      toast('買好了，' + PT_PID[pid].toLocaleString() + ' 點入帳，這批不會過期');
      return true;
    }
    return false;
  };
  const famSwitch = $('#famSwitch');
  if (famSwitch) famSwitch.addEventListener('click', e => {
    const b = e.target.closest('.fam-switch-item'); if (!b) return;
    const p = b.dataset.person;
    if (p === 'all') showFamAll();
    else if (p === 'invite') {
      // 家人頁的邀請入口也要守門：免費不能邀、滿了不能再邀（跟設定頁同一套規則）
      if (window.MMPLAN && window.MMPLAN.isFree()) { window.MMPLAN.upsell('family-invite'); return; }
      if (loadCircle().length >= (CIRCLE_LIMITS[circlePlan()] || 4)) { toast('照護圈滿了，升級方案可以邀請更多家人。'); return; }
      if ($('#inviteFamModal')) { fillInvCode(true); $('#inviteFamModal').classList.add('show'); }
    }
    else showFamPerson(p, b.dataset.rel, b.dataset.init, b.dataset.tint);
  });
  const healthList = $('#healthList');
  if (healthList) healthList.addEventListener('click', e => {
    const r = e.target.closest('.health-row'); if (!r) return;
    showFamPerson(r.dataset.person, r.dataset.rel, r.dataset.init, r.dataset.tint);
  });
  renderFamRoster();   // 開頁就以家庭圈名單為準重建家人頁（兩本帳合一）
  // 狀態頁底部「接上 Apple 健康」卡 → 點了直接進「連接裝置」頁（Edward 7/9：綠字連結要真的能走）
  if ($('#stConnectCard')) $('#stConnectCard').addEventListener('click', () => { window.__connectFrom = 'status'; showView('connect'); });
  // ===== 家人頁圖表：跟狀態頁同一款長相（柱狀＋目標虛線），活動量/睡眠/心情 週月直接切 =====
  function famBarsHTML(labels, values, goal, colorFn, hiIdx) {
    const max = Math.max(goal, Math.max.apply(null, values)) * 1.15;
    const goalPct = Math.min(96, Math.round((goal / max) * 100));
    const bars = values.map((v, i) => {
      const h = Math.max(6, Math.round((v / max) * 100));
      const isHi = i === hiIdx;
      return '<div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;gap:6px;position:relative;z-index:1">' +
        '<div style="width:100%;max-width:24px;height:' + h + '%;border-radius:7px 7px 3px 3px;background:' + colorFn(v) + '"></div>' +
        '<div style="font-size:14px;color:' + (isHi ? 'var(--coral-d)' : 'var(--muted)') + ';font-weight:' + (isHi ? '900' : '700') + '">' + labels[i] + '</div></div>';
    }).join('');
    return '<div style="position:relative;display:flex;align-items:flex-end;gap:8px;height:96px">' +
      '<div style="position:absolute;left:0;right:0;bottom:' + goalPct + '%;border-top:1.5px dashed rgba(90,105,99,.4)"></div>' + bars + '</div>';
  }
  // 家人示範數據（正式版＝那位家人自己的沐寧經雲端同步；頁面上方已標「示範資料」）
  const FAM_WD = ['一', '二', '三', '四', '五', '六', '日'];
  const FAM_WL = ['第1週', '第2週', '第3週', '第4週'];
  // 7/9 正式化：家人趨勢改吃真同步的 35 天日記帳（沒有資料＝誠實空狀態）
  function famTrendFor(p) {
    const v = famVitalsFor(p);
    const log = v && v.log && typeof v.log === 'object' ? v.log : null;
    if (!log) return null;
    const days = Object.keys(log).sort();
    if (!days.length) return null;
    const pick = (arr, field) => arr.map(k => +((log[k] || {})[field]) || 0);
    const w = days.slice(-7);
    const stepsW = pick(w, 'steps'), sleepW = pick(w, 'sleepHours');
    // 月＝最近 28 天切 4 週取均（不足老實少幾根）
    const m = days.slice(-28);
    const chunk = (arr) => { const out = []; for (let i = 0; i < arr.length; i += 7) { const seg = arr.slice(i, i + 7).filter(Boolean); out.push(seg.length ? Math.round(seg.reduce((a, b) => a + b, 0) / seg.length) : 0); } return out; };
    const stepsM = chunk(pick(m, 'steps'));
    const sleepM = chunk(pick(m, 'sleepHours')).map(x => Math.round(x * 10) / 10);
    const wd = w.map(k => FAM_WD[(new Date(k + 'T12:00:00').getDay() + 6) % 7] || '');
    if (!stepsW.some(Boolean) && !sleepW.some(Boolean)) return null;
    return { stepsW, sleepW, stepsM, sleepM, wd };
  }
  const FAM_STEP_GOAL = 7000, FAM_SLEEP_GOAL = 7.5;
  function famAvg(a, dec) { let s = 0; a.forEach(v => s += v); const m = s / a.length; return dec ? +m.toFixed(dec) : Math.round(m); }
  function famEmptyChart(box, note, name) {
    if (box) box.innerHTML = '<div style="padding:16px 2px;font-size:14.5px;color:var(--muted);text-align:center;line-height:1.7">等' + name + '連上沐寧，這裡就會長出他的真數據</div>';
    if (note) note.textContent = '';
  }
  let _famActRange = 'week', _famSleepRange = 'week', _famMoodRange = 'week';
  function renderFamAct() {
    const box = $('#famActChart'), note = $('#trendNote');
    const t = famTrendFor(currentPerson);
    if (!t || !(_famActRange === 'week' ? t.stepsW : t.stepsM).some(Boolean)) return famEmptyChart(box, note, currentPerson || '家人');
    const wk = _famActRange === 'week';
    const vals = wk ? t.stepsW : t.stepsM;
    if (box) box.innerHTML = famBarsHTML(wk ? t.wd : FAM_WL.slice(0, vals.length), vals, FAM_STEP_GOAL, v => v >= FAM_STEP_GOAL ? 'var(--teal)' : 'var(--gold)', vals.length - 1);
    if (note) note.innerHTML = '日均 <b>' + famAvg(vals).toLocaleString() + ' 步</b> · 達標 ' + vals.filter(v => v >= FAM_STEP_GOAL).length + '/' + vals.length + (wk ? ' 天' : ' 週') + (vals.length < (wk ? 7 : 4) ? ' · 累積中' : '');
  }
  function renderFamSleep() {
    const box = $('#famSleepChart'), note = $('#famSleepNote');
    const t = famTrendFor(currentPerson);
    if (!t || !(_famSleepRange === 'week' ? t.sleepW : t.sleepM).some(Boolean)) return famEmptyChart(box, note, currentPerson || '家人');
    const wk = _famSleepRange === 'week';
    const vals = wk ? t.sleepW : t.sleepM;
    if (box) box.innerHTML = famBarsHTML(wk ? t.wd : FAM_WL.slice(0, vals.length), vals, FAM_SLEEP_GOAL, v => v >= 7.5 ? 'var(--teal)' : (v >= 6.5 ? 'var(--gold)' : 'var(--coral)'), vals.length - 1);
    if (note) note.innerHTML = '平均 <b>' + famAvg(vals.filter(Boolean), 1) + ' 小時</b>' + (famAvg(vals.filter(Boolean), 1) >= 7 ? ' · 睡得穩' : ' · 睡得偏少，多留意');
  }
  // 心情週/月：色點跟狀態頁情緒球同一套顏色
  const FAM_MOOD_COLS = ['#F4B63A', '#2FB7A8', '#5B8FB3', '#6D7F91', '#D98A32', '#E95B4F'];
  const FAM_MOOD_NAME = ['開心', '愉悅', '平靜', '低落', '焦慮', '生氣'];
  function renderFamMoodRange() {
    const box = $('#mcRangeBody'), note = $('#mcRangeNote');
    const seq = null;   // 7/9 正式化：心情軌跡只認真資料；跨裝置心情水管還沒接、一律誠實空狀態
    if (!seq) { if (box) box.innerHTML = ''; if (note) note.textContent = '等' + (currentPerson || '家人') + '開始用沐寧聊天，這裡會長出他的心情軌跡。'; return; }
    if (_famMoodRange === 'week') {
      if (box) box.innerHTML = '<div class="mood-mini">' + seq.map((mi, i) =>
        '<div class="mm-day"><div class="mm-dot" style="background:' + FAM_MOOD_COLS[mi] + '"></div><div class="mm-lab">' + FAM_WD[i] + '</div></div>').join('') + '</div>';
      const cnt = {}; seq.forEach(x => cnt[x] = (cnt[x] || 0) + 1);
      const main = FAM_MOOD_NAME[+Object.keys(cnt).sort((a, b) => cnt[a] - cnt[b]).pop()];
      if (note) note.innerHTML = '過去 7 天多在<b>' + main + '</b>；顏色跟狀態頁的情緒球同一套。';
    } else {
      const cells = Array.from({ length: 30 }, (_, i) => seq[i % seq.length]);
      if (box) box.innerHTML = '<div class="mood-grid">' + cells.map(mi => '<i style="background:' + FAM_MOOD_COLS[mi] + '"></i>').join('') + '</div>';
      if (note) note.innerHTML = '過去 30 天的心情地圖；一格一天、顏色跟情緒球同一套。';
    }
  }
  function renderFamTrends() { renderFamAct(); renderFamSleep(); renderFamMoodRange(); }
  function bindFamTabs(id, setter) {
    const el = $(id);
    if (!el) return;
    el.addEventListener('click', e => {
      const b = e.target.closest('button'); if (!b) return;
      el.querySelectorAll('button').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      setter(b.dataset.range || b.dataset.r);
    });
  }
  bindFamTabs('#trendTabs', r => { _famActRange = r; renderFamAct(); });
  bindFamTabs('#sleepTabs', r => { _famSleepRange = r; renderFamSleep(); });
  bindFamTabs('#mcRangeTabs', r => { _famMoodRange = r; renderFamMoodRange(); });

  // 一鍵回診摘要
  const rep = $('#reportBtn');
  if (rep) rep.addEventListener('click', () => $('#reportModal').classList.add('show'));
  if ($('#reportClose')) $('#reportClose').addEventListener('click', () => $('#reportModal').classList.remove('show'));
  if ($('#reportModal')) $('#reportModal').addEventListener('click', e => { if (e.target === $('#reportModal')) $('#reportModal').classList.remove('show'); });
  if ($('#rptSendBtn')) $('#rptSendBtn').addEventListener('click', () => {
    // 真的分享出去（系統分享面板：LINE／簡訊／任何家人在用的），不再假裝「已傳送」
    const rows = [...document.querySelectorAll('#reportModal .rpt-row')].map(r => {
      const k = r.querySelector('.rpt-k'), b = r.querySelector('b');
      return (k ? k.textContent : '') + '：' + (b ? b.textContent : '');
    });
    const text = '沐寧 · 回診摘要\n' + rows.join('\n');
    const done = () => { $('#reportModal').classList.remove('show'); pushFamilyFeed('<b>你</b>把回診摘要分享給了家人'); };
    if (navigator.share) {
      navigator.share({ text }).then(() => { toast('摘要分享出去了，回診那天記得帶著'); done(); }).catch(() => {});
    } else {
      (navigator.clipboard && navigator.clipboard.writeText ? navigator.clipboard.writeText(text) : Promise.reject()).then(
        () => { toast('摘要複製好了，貼給家人就行'); done(); },
        () => toast('這台裝置不支援分享，晚點在手機上試')
      );
    }
  });

  // 發起挑戰面板
  const chalModal = $('#chalModal');
  const closeChal = () => chalModal && chalModal.classList.remove('show');
  if ($('#newChalBtn')) $('#newChalBtn').addEventListener('click', () => {
    if (!chalModal) return;
    const cur = document.querySelector('.chal-type.active');
    applyChalKind(cur ? (cur.dataset.kind || 'walk') : 'walk');
    // 預填日期：運動=今天開始、問答=後天截止、揪一攤=這週六、抽獎=今天（時間欄各有預設）
    try {
      const t0 = new Date();
      const sat = new Date(t0); sat.setDate(sat.getDate() + (((6 - sat.getDay() + 7) % 7) || 7));
      const due = new Date(t0); due.setDate(due.getDate() + 2);
      const w7 = new Date(t0); w7.setDate(w7.getDate() + 7);
      if ($('#walkDue') && !$('#walkDue').value) { $('#walkDue').value = isoOf(w7); if (typeof syncWalkDays === 'function') syncWalkDays(); }
      if ($('#quizDue') && !$('#quizDue').value) $('#quizDue').value = isoOf(due);
      if ($('#voteDue') && !$('#voteDue').value) $('#voteDue').value = isoOf(due);
      if ($('#evDate') && !$('#evDate').value) $('#evDate').value = isoOf(sat);
      if ($('#drawDate') && !$('#drawDate').value) $('#drawDate').value = isoOf(t0);
    } catch (e) {}
    chalModal.classList.add('show');
  });
  const WD = ['週日', '週一', '週二', '週三', '週四', '週五', '週六'];
  function fmtDay(d) { return (d.getMonth() + 1) + '/' + d.getDate() + '（' + WD[d.getDay()] + '）'; }
  function isoOf(d) { return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }
  function buildCalGrid(boxSel) {
    const box = boxSel ? $(boxSel) : null;
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
  function saveActs(a) { try { localStorage.setItem('munea.activities', JSON.stringify(a)); } catch (e) {} syncPush('activities', a); if (window.MuneaNotify) window.MuneaNotify.sync(); }
  const FAM_AVA = { '阿嬤': ['嬤', 'p-ama'], '美華': ['華', 'p-mei'], '志明': ['明', 'p-zhi'], '小寶': ['寶', 'p-bao'], '你': ['我', 'p-me'] };
  function buildRankList(act) {
    const rows = Object.entries(act.answers).sort((x, y) => y[1] - x[1]);
    return '<div class="rank-list">' + rows.map((r2, i3) => {
      const av = FAM_AVA[r2[0]] || [r2[0][0], 'p-me'];
      const noCls = i3 === 0 ? 'n1' : i3 === 1 ? 'n2' : i3 === 2 ? 'n3' : '';
      return '<div class="rank-row"><span class="rank-no ' + noCls + '">' + (i3 + 1) + '</span>' +
        '<span class="rank-av"><span class="init-ava ' + av[1] + '">' + av[0] + '</span></span>' +
        '<b>' + r2[0] + '</b><span class="rank-score">答對 ' + r2[1] + ' 題</span></div>';
    }).join('') + '</div><div class="qc-life">排名保留一天，明天自動收進記錄簿</div>';
  }
  // 揪一攤：我要去／我沒空 ＋ 名單（Edward 7/9：補完整互動）
  function renderEventBody(act, box) {
    const my = act.rsvp && act.rsvp['你'];
    const going = Object.entries(act.rsvp || {}).filter(([, v]) => v === 'go').map(([n]) => n);
    const no = Object.entries(act.rsvp || {}).filter(([, v]) => v === 'no').map(([n]) => n);
    // 活動時間過了就鎖住（時間點以前才能選、之後只看結果）— Edward 7/9
    let locked = false;
    try { if (act.dateISO) { const dt = new Date(act.dateISO + 'T' + (act.time || '23:59')); if (!isNaN(dt) && dt < new Date()) locked = true; } } catch (e) {}
    box.innerHTML =
      '<div class="ad-note"><b>' + act.title + '</b>' + (act.place ? ' · ' + act.place : '') + (act.dateLabel ? '<br>' + act.dateLabel : '') + '</div>' +
      '<div class="rsvp-btns"><button type="button" class="rsvp-btn go' + (my === 'go' ? ' on' : '') + '" data-r="go"' + (locked ? ' disabled' : '') + '>我要去</button>' +
      '<button type="button" class="rsvp-btn no' + (my === 'no' ? ' on' : '') + '" data-r="no"' + (locked ? ' disabled' : '') + '>我沒空</button></div>' +
      '<div class="qc-num">' + (going.length ? '要去的：' + going.join('、') : '還沒有人回「要去」') + (no.length ? '　·　沒空：' + no.join('、') : '') +
      '；' + (locked ? '活動時間到了，不能再改。' : (my ? '想改隨時再點另一個就好；' : '點一下回覆；') + cname() + '會幫你問阿嬤跟其他人。') + '</div>';
    if (!locked) box.querySelector('.rsvp-btns').addEventListener('click', e => {
      const b = e.target.closest('.rsvp-btn'); if (!b || b.disabled) return;
      act.rsvp = act.rsvp || {}; act.rsvp['你'] = b.dataset.r;
      const acts = loadActs(); const t = acts.find(a => a.id === act.id); if (t) t.rsvp = act.rsvp; saveActs(acts);
      renderEventBody(act, box);
      toast(b.dataset.r === 'go' ? '好，記下你要去了' : '好，記下你這次沒空');
    });
  }
  // 一起運動：進度條 ＋ 每人步數（你的自動吃 Apple 健康、其他人吃帶回的數據）
  function renderWalkBody(act, box) {
    const goal = +act.goal || 30000;
    const parts = actParts(act);
    const steps = {};
    parts.forEach(n => {
      if (n === '你') {
        let mine = 0;
        try { const h = JSON.parse(localStorage.getItem('munea.health.last') || 'null'); if (h && h.s && typeof h.s.steps === 'number') mine = h.s.steps; } catch (e) {}
        steps[n] = mine || +(act._steps && act._steps['你']) || 0;
      } else {
        let s = 0; try { const v = famVitalsFor(n); if (v && v.steps) s = +v.steps; } catch (e) {}
        steps[n] = s;
      }
    });
    const sum = parts.reduce((s, n) => s + (+steps[n] || 0), 0);
    const pct = Math.min(100, goal ? Math.round(sum / goal * 100) : 0);
    const gap = Math.max(0, goal - sum);
    box.innerHTML =
      '<div class="walk-bar"><i style="width:' + pct + '%"></i></div>' +
      '<div class="walk-sum"><b>' + sum.toLocaleString() + '</b> / ' + goal.toLocaleString() + ' 步 · ' + (gap > 0 ? '還差 ' + gap.toLocaleString() + ' 步' : '達標了！') + '</div>' +
      '<div class="walk-people">' + parts.map(n => {
        const av = FAM_AVA[n] || [(n || '')[0] || '', 'p-me'];
        return '<div class="walk-p"><span class="init-ava ' + av[1] + '">' + av[0] + '</span><b>' + n + '</b><span>' + (+steps[n] || 0).toLocaleString() + ' 步</span></div>';
      }).join('') + '</div>' +
      '<div class="qc-num">你的步數自動從 Apple 健康帶入；' + cname() + '會問其他人今天走多少，' + (act.dueLabel || (act.days + ' 天內')) + '結算。</div>';
  }
  // 活動結束時，依種類公布結果進記錄簿（不再只是「結束了」）
  function announceActEnd(a) {
    try {
      if (a.kind === 'quiz' && a.answers && Object.keys(a.answers).length) {
        const top = Object.entries(a.answers).sort((x, y) => y[1] - x[1])[0];
        pushFamilyFeed('「' + a.title + '」結算了——<b>' + top[0] + '</b> 答對最多（' + top[1] + ' 題），收進<b>家庭記錄簿</b>');
      } else if (a.kind === 'vote' && a.votes && Object.keys(a.votes).length) {
        const tally = {}; Object.values(a.votes).forEach(o => tally[o] = (tally[o] || 0) + 1);
        const win = Object.entries(tally).sort((x, y) => y[1] - x[1])[0];
        pushFamilyFeed('「' + a.title + '」投票結束——<b>' + win[0] + '</b> 最多票，收進<b>家庭記錄簿</b>');
      } else if (a.kind === 'event' && a.rsvp) {
        const going = Object.entries(a.rsvp).filter(([, v]) => v === 'go').map(([n]) => n);
        pushFamilyFeed('「' + a.title + '」結束了' + (going.length ? '（' + going.join('、') + ' 有去）' : '') + '，收進<b>家庭記錄簿</b>');
      } else {
        pushFamilyFeed('「' + a.title + '」結束了，收進<b>家庭記錄簿</b>');
      }
    } catch (e) { pushFamilyFeed('「' + (a.title || '活動') + '」結束了，收進<b>家庭記錄簿</b>'); }
  }
  function renderActCard(act) {
    const list = document.querySelector('#newChalBtn')?.closest('.pad')?.querySelector('.quest-card');
    if (!list) return;
    const card = document.createElement('div');
    card.className = 'quest-card pending';
    let chip, goal, note;
    if (act.status === 'done') {
      chip = '已結束';
      if (act.kind === 'quiz' && act.answers && Object.keys(act.answers).length) {
        act._rankHtml = buildRankList(act);
        goal = '';
        note = '';
      } else {
        goal = act.kind === 'quiz' ? ('你答對 ' + act.score + ' / ' + (act.q || 5) + ' 題') : (act.title + ' 結束了');
        note = '等大家都看過就收進記錄簿 · 最多留 3 天，還沒看的，寧寧會親口告訴';
      }
    } else if (act.kind === 'walk') {
      chip = act.days + ' 天內';
      goal = '大家一起走 ' + (+act.goal).toLocaleString() + ' 步';
      note = cname() + '會親口問阿嬤要不要一起；開始後每個人走多少都看得到';
    } else if (act.kind === 'quiz') {
      chip = act.q + ' 題';
      if (act.myDone && act.answers && act.answers['你'] !== undefined) {
        goal = '你答對 ' + act.answers['你'] + ' / ' + act.q + ' 題';
        note = '等 ' + act.names.join('、') + ' 作答完看排名，' + cname() + '會去找他們玩';
      } else {
        goal = '你的 ' + act.q + ' 題準備好了';
        note = '點這張卡先作答；' + cname() + '會找其他人玩，都答完看排名';
      }
    } else if (act.kind === 'vote') {
      chip = act.names.length + 1 + ' 人';
      goal = '';
      note = '';
    } else if (act.kind === 'draw') {
      chip = act.when + '開獎';
      goal = '';
      note = '';
    } else {
      chip = act.dateLabel;
      goal = act.title + (act.place ? ' · ' + act.place : '') + '，誰能到？';
      note = cname() + '會親口問阿嬤、幫大家收「去 / 沒空」；過了那天卡片會自動收進記錄簿';
    }
    const rwLine = act.rewards && act.rewards.some(Boolean)
      ? '<div class="qc-prize"><span class="qp-ico">🏅</span><div class="qp-txt">' + act.rewards.map((r, i2) => r ? '第 ' + (i2 + 1) + ' 名 ' + r : '').filter(Boolean).join('、') + '<small>獎品提供：' + (act.owner || '你') + '</small></div></div>'
      : '';
    if (act._rankHtml) {
      card.innerHTML = '<div class="qc-kicker"><svg class="ic" viewBox="0 0 24 24"><path d="M8 21h8M12 17v4M17 5H7v5a5 5 0 0 0 10 0V5z"/><path d="M17 6h3a1 1 0 0 1 1 1c0 2-1.5 3.5-3.5 3.8M7 6H4a1 1 0 0 0-1 1c0 2 1.5 3.5 3.5 3.8"/></svg>機智問答 · 排名出來了<span class="qc-days">' + (act.q || 5) + ' 題</span></div>' + act._rankHtml + rwLine;
      delete act._rankHtml;
    } else {
      card.innerHTML = '<div class="qc-kicker"><svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg>' +
        (act.kind === 'event' ? '揪一攤 · ' + act.title : act.kind === 'vote' ? '投票 · ' + act.title : act.kind === 'draw' ? '抽獎 · ' + act.prize : '邀請已送出 · ' + act.title) +
        '<span class="qc-days">' + chip + '</span></div>' +
        (goal ? '<div class="qc-goal">' + goal + '</div>' : '') +
        (note ? '<div class="qc-num">' + note + '</div>' : '') + rwLine;
    }
    // 點整張卡片＝打開完整活動詳情頁（投票／作答／開獎／管理／刪除都在裡面）
    card.style.cursor = 'pointer';
    card.dataset.actId = act.id;
    card.addEventListener('click', () => openActDetail(act, card));
    list.parentNode.insertBefore(card, list);
  }
  function actParts(act) { return ['你'].concat(act.names || []); }
  function avatarsHtml(names) {
    return names.map(n => { const a = FAM_AVA[n] || [(n || '')[0] || '', 'p-me']; return '<span class="init-ava ' + a[1] + '">' + a[0] + '</span>'; }).join('');
  }
  // 完整活動詳情頁：看完整資訊＋參與者，並在裡面投票／作答／開獎／刪除（Edward 7/7 拍板「做完整詳情頁」）
  function openActDetail(act, card) {
    const sheet = $('#actDetailModal'), body = $('#actDetailBody');
    if (!sheet || !body) return;
    const done = act.status === 'done';
    const chip = done ? '已結束'
      : act.kind === 'walk' ? '進行中 · ' + (act.dueLabel || act.days + ' 天內')
      : act.kind === 'quiz' ? (act.q + ' 題' + (act.dueLabel ? ' · ' + act.dueLabel : ''))
      : act.kind === 'draw' ? (act.when + '開獎')
      : act.kind === 'event' ? (act.dateLabel || '進行中')
      : act.kind === 'vote' ? (act.dueLabel || '進行中') : '進行中';
    const kindName = act.kind === 'walk' ? '一起運動' : act.kind === 'quiz' ? '機智問答' : act.kind === 'vote' ? '投票' : act.kind === 'draw' ? '抽獎' : '揪一攤';
    const title = act.kind === 'draw' ? act.prize : (act.title || kindName);
    body.innerHTML =
      '<div class="ad-kind">' + kindName + '</div>' +
      '<div class="ad-title">' + title + '</div>' +
      '<div><span class="ad-chip">' + chip + '</span></div>' +
      '<div class="ad-sec"><div class="ad-lbl">一起的人（' + actParts(act).length + ' 人）</div><div class="ad-avs">' + avatarsHtml(actParts(act)) + '</div></div>' +
      '<div class="ad-interact"></div>';
    const box = body.querySelector('.ad-interact');
    if (act.kind === 'vote') { renderVoteBody(act, box); }
    else if (act.kind === 'draw') { renderDrawBody(act, box); }
    else if (act.kind === 'quiz') {
      if (act.myDone && act.answers && act.answers['你'] !== undefined) { box.innerHTML = '<div class="ad-note">你答對 ' + act.answers['你'] + ' / ' + act.q + ' 題，等 ' + (act.names || []).join('、') + ' 答完看排名。</div>'; }
      else {
        box.innerHTML = '<div class="ad-note">你的 ' + act.q + ' 題準備好了，點下面開始作答；' + cname() + '會找其他人玩，都答完看排名。</div>';
        const qb = document.createElement('button'); qb.className = 'modal-btn'; qb.style.marginTop = '14px'; qb.textContent = '開始作答';
        qb.addEventListener('click', () => { sheet.classList.remove('show'); startQuiz(act, card || document.querySelector('[data-act-id="' + act.id + '"]')); });
        box.appendChild(qb);
      }
    }
    else if (act.kind === 'walk') { renderWalkBody(act, box); }
    else if (act.kind === 'event') { renderEventBody(act, box); }
    if (act.rewards && act.rewards.some(Boolean)) {
      box.insertAdjacentHTML('beforeend', '<div class="ad-sec"><div class="ad-lbl">小獎勵</div><div class="ad-rewards">' + act.rewards.map((r, i) => r ? '<div>第 ' + (i + 1) + ' 名 · ' + r + '</div>' : '').filter(Boolean).join('') + '</div></div>');
    }
    const del = document.createElement('button');
    del.className = 'ad-del'; del.type = 'button';
    del.innerHTML = '<svg class="ic" viewBox="0 0 24 24"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v5M14 11v5"/></svg><span>刪除這個活動</span>';
    del.addEventListener('click', () => {
      if (del.dataset.arm !== '1') { del.dataset.arm = '1'; del.classList.add('arm'); del.querySelector('span').textContent = '確定刪除？再點一下'; setTimeout(() => { del.dataset.arm = ''; del.classList.remove('arm'); const s = del.querySelector('span'); if (s) s.textContent = '刪除這個活動'; }, 3200); return; }
      const acts = loadActs().filter(a => a.id !== act.id); saveActs(acts);
      const c = card || document.querySelector('[data-act-id="' + act.id + '"]'); if (c) c.remove();
      sheet.classList.remove('show');
      toast('活動刪除了');
    });
    body.appendChild(del);
    if (typeof window.__muneaApplyUserAvatar === 'function') window.__muneaApplyUserAvatar();   // 有上傳帳號照片的（本人）→ 圓形頭像帶照片
    if (!sheet.dataset.wired) { sheet.dataset.wired = '1'; sheet.addEventListener('click', e => { if (e.target === sheet) sheet.classList.remove('show'); }); }
    sheet.classList.add('show');
  }
  function renderVoteBody(act, card) {
    const my = act.votes && act.votes['你'];
    const total = Object.keys(act.votes || {}).length;
    const wrap = document.createElement('div');
    wrap.className = 'vote-body';
    wrap.innerHTML = act.opts.map((o, i) => {
      const n = Object.values(act.votes || {}).filter(v => v === o).length;
      const pct = total ? Math.round(n / total * 100) : 0;
      return '<button type="button" class="vote-opt' + (my === o ? ' mine' : '') + (my ? ' voted' : '') + '" data-o="' + o + '">' +
        '<i style="width:' + (my ? pct : 0) + '%"></i><span class="vo-txt">' + o + '</span>' +
        (my ? '<span class="vo-n">' + n + ' 票</span>' : '') + (my === o ? '<span class="vo-check">✓</span>' : '') + '</button>';
    }).join('') + '<div class="qc-num">' + (my ? cname() + '去問其他人了，誰投了什麼會直接亮在這裡' : '點一個選項投下你的票') + '</div>';
    if (!my) wrap.addEventListener('click', e => {
      const b = e.target.closest('.vote-opt');
      if (!b) return;
      act.votes = act.votes || {}; act.votes['你'] = b.dataset.o;
      const acts = loadActs(); const t = acts.find(a => a.id === act.id); if (t) t.votes = act.votes; saveActs(acts);
      wrap.remove(); renderVoteBody(act, card);
      toast('投好了，' + cname() + '去收其他人的票');
    });
    card.appendChild(wrap);
  }
  function renderDrawBody(act, card) {
    // 開獎儀式（Edward 7/9）：按「現在開獎」→ 名字輪盤轉快轉慢 → 定格 → 彩帶＋中獎卡（獎品＋找誰領）
    const wrap = document.createElement('div');
    wrap.className = 'draw-body';
    const all = ['你'].concat(act.names || []);
    const AWARD = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:26px;height:26px"><circle cx="12" cy="8" r="6"/><path d="M15.5 13 17 22l-5-3-5 3 1.5-9"/></svg>';
    const GIFT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%;height:100%"><rect x="3" y="8" width="18" height="4" rx="1"/><path d="M12 8v13M5 12v9h14v-9"/><path d="M7.5 8a2.5 2.5 0 1 1 0-5C10 3 12 5.5 12 8c0-2.5 2-5 4.5-5a2.5 2.5 0 1 1 0 5"/></svg>';
    function winCardHtml(pop) {
      const claim = act.winner === '你' ? '獎品就是你的了，跟家人說一聲' : '獎品請找阿嬤領';
      return '<div class="draw-stage"><div class="draw-confetti"></div><div class="draw-win-card' + (pop ? '' : ' nopop') + '">' +
        '<span class="dw-ico">' + AWARD + '</span>' +
        '<div class="dw-name">' + act.winner + ' 抽中了</div>' +
        '<div class="dw-prize">「' + act.prize + '」</div>' +
        '<div class="dw-claim">' + claim + '；' + cname() + '已經去恭喜' + (act.winner === '你' ? '你' : '他') + '了，記錄收進家庭記錄簿。</div>' +
        '</div></div>';
    }
    function throwConfetti() {
      const conf = wrap.querySelector('.draw-confetti');
      if (!conf) return;
      const colors = ['#E0B354', '#D98841', '#3AA8A0', '#D9EFE8'];   // 暖金/珊瑚/療癒綠/薄荷（自家色盤）
      for (let k = 0; k < 26; k++) {
        const p = document.createElement('i');
        p.style.left = (4 + Math.random() * 92) + '%';
        p.style.background = colors[k % colors.length];
        p.style.animationDelay = (Math.random() * 0.5).toFixed(2) + 's';
        conf.appendChild(p);
      }
    }
    if (act.winner) {
      wrap.innerHTML = winCardHtml(false);
    } else {
      wrap.innerHTML = '<div class="qc-num">' + all.join('、') + ' 都有份，' + act.when + '由' + cname() + '開獎</div>' +
        '<button type="button" class="draw-now">現在開獎</button>';
      wrap.querySelector('.draw-now').addEventListener('click', () => {
        const winner = all[Math.floor(Math.random() * all.length)];
        act.winner = winner;
        const acts = loadActs(); const t = acts.find(a => a.id === act.id); if (t) t.winner = winner; saveActs(acts);
        // 儀式①：禮物盒搖＋名字輪盤（轉快轉慢）
        wrap.innerHTML = '<div class="draw-stage"><div class="ds-gift">' + GIFT + '</div><div class="draw-roll"><span class="dr-name">…</span><small>看看是誰…</small></div></div>';
        const nameEl = wrap.querySelector('.dr-name');
        let i = 0, delay = 70;
        const spin = () => {
          nameEl.textContent = all[i % all.length]; i++;
          if (delay < 330) { delay *= 1.14; setTimeout(spin, delay); }
          else {
            nameEl.textContent = winner;   // 定格在中獎者
            setTimeout(() => {
              // 儀式②：彩帶＋中獎卡（中了什麼、找誰領）
              wrap.innerHTML = winCardHtml(true);
              throwConfetti();
              pushFamilyFeed('「' + act.prize + '」開獎了——<b>' + winner + '</b> 抽中！');
            }, 620);
          }
        };
        spin();
      });
    }
    card.appendChild(wrap);
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
      act.title = '一起運動';
      // 挑戰截止（跟其他活動同款日期＋時間）：今天開始、到期自動結算 — Edward 7/9
      const wd0 = ($('#walkDue') && $('#walkDue').value) ? new Date($('#walkDue').value + 'T00:00') : null;
      if (!wd0 || isNaN(wd0)) { toast('先選挑戰截止的日期'); return; }
      const wt = ($('#walkDueTime') && $('#walkDueTime').value) || '20:00';
      const start = new Date();
      act.startISO = isoOf(start);
      const day0 = new Date(start.getFullYear(), start.getMonth(), start.getDate());
      act.days = Math.max(1, Math.round((wd0 - day0) / 86400000));
      act.dateISO = isoOf(wd0);
      act.dueTime = wt;
      act.dueLabel = fmtDay(wd0) + ' ' + _clock12(wt) + ' 截止';
    } else if (kind === 'quiz') {
      act.q = +(($('#quizN') && $('#quizN').value) || 10);
      act.title = '機智問答';
      const qd = ($('#quizDue') && $('#quizDue').value) ? new Date($('#quizDue').value + 'T00:00') : null;
      const qt = ($('#quizDueTime') && $('#quizDueTime').value) || '20:00';
      if (qd && !isNaN(qd)) { act.dueISO = isoOf(qd); act.dueTime = qt; act.dueLabel = fmtDay(qd) + ' ' + _clock12(qt) + ' 截止'; }
    } else if (kind === 'vote') {
      act.title = (($('#voteQ') && $('#voteQ').value.trim()) || '家庭投票');
      act.opts = ['#vo1', '#vo2', '#vo3'].map(x => ($(x) && $(x).value.trim()) || '').filter(Boolean);
      if (act.opts.length < 2) { toast('投票至少要兩個選項'); return; }
      // 投票要有截止（到期自動公布結果、收進記錄簿）— Edward 7/9
      const vd0 = ($('#voteDue') && $('#voteDue').value) ? new Date($('#voteDue').value + 'T00:00') : null;
      if (!vd0 || isNaN(vd0)) { toast('先選投票截止的日期'); return; }
      const vt = ($('#voteDueTime') && $('#voteDueTime').value) || '20:00';
      act.dueISO = isoOf(vd0); act.dueTime = vt; act.dateISO = act.dueISO;
      act.dueLabel = fmtDay(vd0) + ' ' + _clock12(vt) + ' 截止';
      act.votes = {};
      ['#voteQ', '#vo1', '#vo2', '#vo3'].forEach(x => { if ($(x)) $(x).value = ''; });
    } else if (kind === 'draw') {
      act.prize = (($('#drawPrize') && $('#drawPrize').value.trim()) || '');
      if (!act.prize) { toast('先填獎品，抽起來才有趣'); return; }
      const dd0 = ($('#drawDate') && $('#drawDate').value) ? new Date($('#drawDate').value + 'T00:00') : new Date();
      const dd = isNaN(dd0) ? new Date() : dd0;
      const dtv = ($('#drawTime') && $('#drawTime').value) || '20:00';
      act.dateISO = isoOf(dd);
      act.when = fmtDay(dd) + ' ' + _clock12(dtv);
      act.title = '幸運抽獎';
      if ($('#drawPrize')) $('#drawPrize').value = '';
    } else {
      const ed0 = ($('#evDate') && $('#evDate').value) ? new Date($('#evDate').value + 'T00:00') : null;
      if (!ed0 || isNaN(ed0)) { toast('先選聚會的日期'); return; }
      const etv = ($('#evTime') && $('#evTime').value) || '18:00';
      act.dateISO = isoOf(ed0);
      act.time = etv;   // 原始時間：給「活動前 30 分提醒」＋「時間過了鎖 RSVP」用
      act.dateLabel = fmtDay(ed0) + ' ' + _clock12(etv);
      act.title = (($('#eventName') && $('#eventName').value.trim()) || '家庭聚會');
      act.place = (($('#eventPlace') && $('#eventPlace').value.trim()) || '');
    }
    const rw = ['#rw1', '#rw2', '#rw3'].map(x => ($(x) && $(x).value.trim()) || '');
    if (rw.some(Boolean)) act.rewards = rw;
    ['#rw1', '#rw2', '#rw3'].forEach(x => { if ($(x)) $(x).value = ''; });
    const acts = loadActs(); acts.push(act); saveActs(acts);
    trackProductEvent('activity_created', { kind: kind });
    closeChal();
    renderActCard(act);
    hint(kind === 'event' ? '好，' + cname() + '幫你問大家，誰能到、誰沒空，回覆齊了告訴你。' : kind === 'vote' ? '好，' + cname() + '把問題送出去了，誰投了什麼馬上看得到。' : kind === 'draw' ? '好，' + cname() + '把抽獎報給大家了，' + (act.when || '') + '開獎！' : '好，邀請發出去了，' + cname() + '會親口問阿嬤，等大家答應就開始。');
  });
  // 一張活動卡是不是「到期該收」（含自己發起的、含問答/投票、含沒設日期的殭屍卡）— Edward 7/9 修卡死
  // 這個活動「哪天算結束」（揪一攤=活動日、問答/投票=截止、運動=截止、抽獎=開獎日）
  function actEndISO(a) {
    if (a.kind === 'quiz' || a.kind === 'vote') return a.dueISO || a.dateISO;
    return a.dateISO || a.dueISO;
  }
  // 到期規則（Edward 7/9）：揪一攤=活動當天過後、隔天 0:00 收；問答/運動=結束後多留一天看成績；殭屍卡放 3 天一律清
  function actExpired(a) {
    if (!a) return false;
    const today = isoOf(new Date());
    const created = a.id ? isoOf(new Date(a.id)) : today;
    const endBase = (a.status === 'done' ? a.doneISO : actEndISO(a)) || created;
    const grace = (a.kind === 'quiz' || a.kind === 'walk') ? 1 : 0;   // 問答/運動：結束後多留一天
    const g = new Date(endBase + 'T00:00'); g.setDate(g.getDate() + grace);
    const removeAfter = isoOf(g);   // 這天(含)之前留著、隔天 0:00 收
    const d3 = new Date(); d3.setDate(d3.getDate() - 3);
    if (removeAfter < today) return true;
    if (created < isoOf(d3)) return true;   // 保險：殭屍卡放超過 3 天一律清
    return false;
  }
  // 開 App 時整理牆面：到期的收進記錄簿、其餘重畫
  function restoreActsBoot() {
    const acts = loadActs();
    const keep = [];
    acts.forEach(a => {
      if (actExpired(a)) {
        announceActEnd(a);
      } else { keep.push(a); renderActCard(a); }
    });
    if (keep.length !== acts.length) saveActs(keep);
  }
  // 進家人頁時再掃一次：不用重開 App，到期卡當場收掉＋公布結果
  function sweepActsOnView() {
    const acts = loadActs();
    const expired = acts.filter(a => actExpired(a));
    if (!expired.length) return;
    expired.forEach(a => { announceActEnd(a); const c = document.querySelector('[data-act-id="' + a.id + '"]'); if (c) c.remove(); });
    saveActs(acts.filter(a => !actExpired(a)));
  }
  window.__muneaSweepActs = sweepActsOnView;
  __pullPromise.finally(() => restoreActsBoot());
  if (chalModal) chalModal.addEventListener('click', e => { if (e.target === chalModal) closeChal(); });
  // 邀請勾選 → 依人數+能力動態算目標
  const inviteList = $('#inviteList');
  function paintRange(el) {
    if (!el) return;
    const p = (el.value - el.min) / (el.max - el.min) * 100;
    el.style.setProperty('--fill', p.toFixed(1) + '%');
  }
  function updateWalkLabels() {
    paintRange($('#walkGoal')); paintRange($('#walkDays')); paintRange($('#quizN'));
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
  const INVITE_NOTES = () => ({ walk: '阿嬤那份，' + cname() + '會親口問她', quiz: '阿嬤用說的就能玩；其他人手機作答', event: cname() + '親口問阿嬤；其他人回「去／沒空」', vote: '阿嬤那票，' + cname() + '會唸選項給她聽、幫她投', draw: '人人有機會；開獎時' + cname() + '會告訴每個人' });
  function applyChalKind(kind) {
    if ($('#inviteNote')) $('#inviteNote').textContent = INVITE_NOTES()[kind] || '';
    if ($('#walkFields')) $('#walkFields').style.display = kind === 'walk' ? '' : 'none';
    if ($('#quizFields')) $('#quizFields').style.display = kind === 'quiz' ? '' : 'none';
    if ($('#eventFields')) $('#eventFields').style.display = kind === 'event' ? '' : 'none';
    if ($('#voteFields')) $('#voteFields').style.display = kind === 'vote' ? '' : 'none';
    if ($('#drawFields')) $('#drawFields').style.display = kind === 'draw' ? '' : 'none';
    if ($('#rewardFields')) $('#rewardFields').style.display = (kind === 'walk' || kind === 'quiz') ? '' : 'none';
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
  // 挑戰截止一改 → 換算天數（給目標步數建議用）
  function syncWalkDays() {
    const el = $('#walkDue');
    if (!el || !el.value) return;
    const due = new Date(el.value + 'T00:00');
    if (isNaN(due)) return;
    const t = new Date();
    const day0 = new Date(t.getFullYear(), t.getMonth(), t.getDate());
    const d = Math.min(30, Math.max(1, Math.round((due - day0) / 86400000)));
    if ($('#walkDays')) $('#walkDays').value = d;
    recalcWalk(true);
  }
  if ($('#walkDue')) $('#walkDue').addEventListener('change', syncWalkDays);
  if ($('#quizN')) $('#quizN').addEventListener('input', () => {
    paintRange($('#quizN'));
    if ($('#quizNVal')) $('#quizNVal').textContent = $('#quizN').value + ' 題';
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
  // 看診可記多筆、每筆有標題（看什麼診）＋日期＋時間
  function loadVisits() {
    let arr = null; try { arr = JSON.parse(localStorage.getItem('munea.visits') || 'null'); } catch (e) {}
    if (!Array.isArray(arr)) {
      let old = null; try { old = JSON.parse(localStorage.getItem('munea.visit') || 'null'); } catch (e2) {}
      arr = (old && (old.dateISO || old.label)) ? [{ id: 1, title: old.title || '回診', dateISO: old.dateISO || '', time: old.time || '', label: old.label || '' }] : [];
    }
    return arr.filter(v => v && v.dateISO).sort((a, b) => (a.dateISO + (a.time || '')).localeCompare(b.dateISO + (b.time || '')));
  }
  function saveVisits(arr) { try { localStorage.setItem('munea.visits', JSON.stringify(arr)); } catch (e) {} syncPush('visits', arr); if (window.MuneaNotify) window.MuneaNotify.sync(); }
  function nextVisit() { const today = isoOf(new Date()); const arr = loadVisits(); return arr.filter(v => v.dateISO >= today)[0] || arr[0] || null; }
  function fmtVisitTime(tv) {  // "14:30" → "下午 2:30"
    const p = String(tv || '09:00').split(':'); const hh = +p[0] || 9, mm = +p[1] || 0;
    const ap = hh < 12 ? '上午' : '下午'; const h12 = ((hh + 11) % 12) + 1;
    return ap + ' ' + h12 + ':' + String(mm).padStart(2, '0');
  }
  function renderVisitRow() {
    const v = nextVisit();
    const lb = $('#visitLabel');
    if (lb) lb.textContent = v ? _visitDayShort(v) : '';
    // 看診有增減時，同步首頁「今天一起完成」的回診任務（只在當天顯示）
    if (window.__muneaRenderDailyTasks) window.__muneaRenderDailyTasks();
  }
  window.__muneaRefreshVisitRow = renderVisitRow;
  function renderVisitList() {
    const box = $('#visitList'); if (!box) return;
    const arr = loadVisits();
    box.innerHTML = arr.length ? ('<div class="field-label">已排的看診</div>' + arr.map(v =>
      '<div class="visit-item"><div class="vi-info"><b>' + (v.title || '回診') + '</b><span>' + (v.label || '') + '</span></div><button type="button" class="vi-del" data-id="' + v.id + '">刪除</button></div>').join('')) : '';
  }
  if ($('#visitList')) $('#visitList').addEventListener('click', e => {
    const b = e.target.closest('.vi-del'); if (!b) return;
    const currentVisits = loadVisits();
    const removed = currentVisits.find(v => String(v.id) === String(b.dataset.id));
    saveVisits(currentVisits.filter(v => String(v.id) !== String(b.dataset.id)));
    if (removed) archiveRoutineReminder(removed.id);
    renderVisitList(); renderVisitRow();
  });
  if ($('#visitEntry')) $('#visitEntry').addEventListener('click', () => {
    buildCalGrid('#visitDatePick');
    if ($('#visitTitle')) $('#visitTitle').value = '';
    if ($('#visitTime')) $('#visitTime').value = '09:00';
    renderVisitList();
    $('#visitModal').classList.add('show');
  });
  if ($('#visitClose')) $('#visitClose').addEventListener('click', () => $('#visitModal').classList.remove('show'));
  if ($('#visitModal')) $('#visitModal').addEventListener('click', e => { if (e.target === $('#visitModal')) $('#visitModal').classList.remove('show'); });
  if ($('#visitSaveBtn')) $('#visitSaveBtn').addEventListener('click', () => {
    const on = document.querySelector('#visitDatePick .cal-cell.on');
    if (!on) { toast('先選一天'); return; }
    const title = ((($('#visitTitle') && $('#visitTitle').value) || '').trim()) || '回診';
    const tv = ($('#visitTime') && $('#visitTime').value) || '09:00';
    const d = new Date(on.dataset.iso + 'T00:00');
    const label = fmtDay(d) + ' ' + fmtVisitTime(tv);
    const visit = { id: Date.now(), title, dateISO: on.dataset.iso, time: tv, label };
    const arr = loadVisits(); arr.push(visit);
    saveVisits(arr);
    syncVisitReminder(visit);
    renderVisitList(); renderVisitRow();
    if ($('#visitTitle')) $('#visitTitle').value = '';
    document.querySelectorAll('#visitDatePick .cal-cell.on').forEach(x => x.classList.remove('on'));
    toast('好，「' + title + '」' + label + '記下了，' + cname() + '前一天會提醒你');
  });
  renderVisitRow();
  refreshRoutineRemindersFromBackend();
  const FONT_STEPS = [['std', '標準', ''], ['lg', '大', '1.07'], ['xl', '特大', '1.14']];
  function applyFontScale() {
    const cur = localStorage.getItem('munea.fontScale') || 'std';
    const step = FONT_STEPS.find(x => x[0] === cur) || FONT_STEPS[0];
    document.querySelectorAll('.screen .pad, .modal').forEach(el => { el.style.zoom = step[2]; });
    const row = $('#fontNow');
    if (row) row.textContent = step[1] + ' ›';
  }
  function markFontOpt() {
    const cur = localStorage.getItem('munea.fontScale') || 'std';
    document.querySelectorAll('.font-opt').forEach(o => o.classList.toggle('on', o.dataset.f === cur));
  }
  if ($('#fontRow')) $('#fontRow').addEventListener('click', () => { markFontOpt(); $('#fontModal').classList.add('show'); });
  if ($('#fontClose')) $('#fontClose').addEventListener('click', () => $('#fontModal').classList.remove('show'));
  if ($('#fontModal')) $('#fontModal').addEventListener('click', e => {
    if (e.target === $('#fontModal')) { $('#fontModal').classList.remove('show'); return; }
    const o = e.target.closest('.font-opt');
    if (!o) return;
    try { localStorage.setItem('munea.fontScale', o.dataset.f); } catch (e2) {}
    applyFontScale();
    markFontOpt();
    const nm = (FONT_STEPS.find(x => x[0] === o.dataset.f) || [])[1] || '標準';
    toast('好，改成「' + nm + '」了');
  });
  applyFontScale();
  // 條款／隱私：App 內白色內頁（左上返回、內容可滑）
  async function openReader(kind) {
    const page = kind === 'terms' ? 'terms.html' : 'privacy.html';
    $('#readerTitle').textContent = kind === 'terms' ? '使用條款' : '隱私權政策';
    const body = $('#readerBody');
    body.innerHTML = '<p>讀取中…</p>';
    $('#readerPage').classList.add('show');
    try {
      const html = await fetch(page).then(r => r.text());
      const doc = new DOMParser().parseFromString(html, 'text/html');
      const secs = [...doc.querySelectorAll('.privacy-section')];
      body.innerHTML = secs.map(s2 => '<h4>' + s2.querySelector('h2').textContent + '</h4>' +
        [...s2.querySelectorAll('p, ul')].map(x => x.outerHTML.replace(/<h2.*?<\/h2>/, '')).join('')).join('');
      // 防呆：閱讀器裡的連結一律轉純文字（點了會把 App 帶去外頁、回不來）
      body.querySelectorAll('a').forEach(a => { const b2 = document.createElement('strong'); b2.textContent = a.textContent; a.replaceWith(b2); });
    } catch (e2) { body.innerHTML = '<p>暫時讀不到，晚點再試。</p>'; }
    $('#readerBody').closest('.reader-scroll').scrollTop = 0;
  }
  if ($('#readerBack')) $('#readerBack').addEventListener('click', () => $('#readerPage').classList.remove('show'));
  // 安全通知：選 1~3 位家庭圈家人當緊急聯絡人，健康數據危險異常時通知他們確認
  // 名單直接吃「設定 → 全家健康圈」同一份資料（單一真相）；圈裡移除了人，這裡自動跟著消失
  function safetyMembers() { return loadCircle().filter(m => !m.self); }
  function loadSafety() {
    try {
      const raw = JSON.parse(localStorage.getItem('munea.safetyContacts')) || [];
      const valid = new Set(safetyMembers().map(m => m.name));
      const sel = raw.filter(n => valid.has(n));
      if (sel.length !== raw.length) localStorage.setItem('munea.safetyContacts', JSON.stringify(sel));
      return sel;
    } catch (e) { return []; }
  }
  function updateSafetyCount() { const el = $('#safetyCount'); if (el) { const sel = loadSafety(); el.textContent = sel.length ? sel.join('、') : ''; } }
  function renderSafety() {
    const picks = $('#safetyPicks'); if (!picks) return;
    const sel = loadSafety();
    const mem = safetyMembers();
    picks.innerHTML = mem.length ? mem.map(m =>
      '<button type="button" class="safety-pick' + (sel.includes(m.name) ? ' on' : '') + '" data-name="' + m.name + '">' +
      '<span class="init-ava ' + (m.tint || '') + '">' + (m.init || (m.name || '')[0] || '') + '</span><span class="sp-name">' + m.name + '</span>' +
      '<span class="sp-check"><svg class="ic" viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg></span></button>').join('')
      : '<p class="modal-sub" style="margin:4px 0 0">圈裡還沒有家人。先到「家人」頁邀請家人加入，就能選緊急聯絡人。</p>';
    updateSafetyCount();
  }
  if ($('#safetyPicks')) $('#safetyPicks').addEventListener('click', e => {
    const b = e.target.closest('.safety-pick'); if (!b) return;
    let sel = loadSafety(); const name = b.dataset.name;
    if (sel.includes(name)) sel = sel.filter(n => n !== name);
    else { if (sel.length >= 3) { toast('最多選 3 位緊急聯絡人'); return; } sel.push(name); }
    try { localStorage.setItem('munea.safetyContacts', JSON.stringify(sel)); } catch (e2) {}
    b.classList.toggle('on', sel.includes(name));
    updateSafetyCount();
  });
  if ($('#safetyRow')) $('#safetyRow').addEventListener('click', () => { renderSafety(); $('#safetyModal').classList.add('show'); });
  if ($('#safetySave')) $('#safetySave').addEventListener('click', () => {
    $('#safetyModal').classList.remove('show');
    const sel = loadSafety();
    toast(sel.length ? ('名單記好了：' + sel.join('、') + '。異常時我會第一時間讓家人知道。') : '還沒選聯絡人，等你想好再設定就好');
  });
  if ($('#safetyModal')) $('#safetyModal').addEventListener('click', e => { if (e.target === $('#safetyModal')) $('#safetyModal').classList.remove('show'); });
  updateSafetyCount();
  // 想聊的話題：設定入口＋第一次開聊前輕問一次（可跳過、只問一次）
  let _intSel = loadInterests();
  let _intFromCall = false;
  function renderInterestPicks() {
    const box = $('#interestPicks');
    if (box) box.innerHTML = INTEREST_TOPICS.map(t => '<button type="button" class="topic-chip' + (_intSel.includes(t) ? ' on' : '') + '" data-t="' + t + '">' + t + '</button>').join('');
    const now = $('#interestsNow');
    if (now) now.innerHTML = _intSel.length ? ('<b>已挑 ' + _intSel.length + ' 個</b> ›') : '›';
  }
  window.__muneaOpenInterests = function (fromCall) {
    _intSel = loadInterests(); _intFromCall = !!fromCall;
    renderInterestPicks();
    const skip = $('#interestsSkip'); if (skip) skip.style.display = fromCall ? '' : 'none';
    $('#interestsModal').classList.add('show');
  };
  function closeInterests(startAfter) {
    $('#interestsModal').classList.remove('show');
    try { localStorage.setItem('munea.interestsAsked', '1'); } catch (e2) {}
    const goCall = startAfter && _intFromCall;
    _intFromCall = false;
    if (goCall) connectCall();
  }
  if ($('#interestPicks')) $('#interestPicks').addEventListener('click', e => {
    const b = e.target.closest('.topic-chip'); if (!b) return;
    const t = b.dataset.t;
    if (_intSel.includes(t)) _intSel = _intSel.filter(x => x !== t);
    else { if (_intSel.length >= 5) { toast('挑 5 個以內就好，聊得才深'); return; } _intSel.push(t); }
    b.classList.toggle('on', _intSel.includes(t));
  });
  if ($('#interestsRow')) $('#interestsRow').addEventListener('click', () => window.__muneaOpenInterests(false));
  // ===== 意見與建議（回報問題/功能建議/稱讚/NPS）→ 引擎收件箱＋Slack 叮一聲 =====
  let _fbType = 'bug', _fbNps = null;
  function renderNps() {
    // 拉桿 Bar 條打分（Edward 7/9：不要 11 顆按鈕）：拉或點都行、上方大字即時顯示
    const s = $('#npsSlider'); if (!s || s.dataset.built) return; s.dataset.built = '1';
    const WORDS = ['完全不會', '不太會', '不太會', '普通', '普通', '普通', '還可以', '願意', '願意', '非常願意', '非常願意'];
    const paint = () => {
      const v = +s.value;
      s.style.setProperty('--fill', (v * 10) + '%');
      if ($('#npsVal')) $('#npsVal').textContent = String(v);
      if ($('#npsWord')) $('#npsWord').textContent = WORDS[v] || '';
    };
    const pick = () => { _fbNps = +s.value; paint(); };
    s.addEventListener('input', pick);
    s.addEventListener('change', pick);
  }
  function fbApplyType() {
    if ($('#fbCatWrap')) $('#fbCatWrap').style.display = _fbType === 'bug' ? '' : 'none';
    if ($('#fbNpsWrap')) $('#fbNpsWrap').style.display = _fbType === 'nps' ? '' : 'none';
    const lbl = $('#fbTextLabel'), txt = $('#fbText');
    if (lbl) lbl.textContent = _fbType === 'bug' ? '發生了什麼事？（越具體我們修得越快）' : _fbType === 'idea' ? '想要什麼新功能？' : _fbType === 'praise' ? '想稱讚哪裡？我們會轉告寧寧' : '為什麼給這個分數？（可以不填）';
    if (txt) txt.placeholder = _fbType === 'idea' ? '例：希望可以幫我記血糖、想要台語' : _fbType === 'praise' ? '例：寧寧記得我孫子要結婚，好感動' : '例：聊聊講到一半沒聲音了';
    renderNps();
  }
  // 意見回饋附圖（7/9 Edward：文字說不清時附截圖）：選圖→縮到最長邊 1200px、壓成 JPEG→data URL 預覽
  let _fbImage = null;
  function fbClearPhoto() {
    _fbImage = null;
    const inp = $('#fbPhotoInput'); if (inp) inp.value = '';
    const pv = $('#fbPhotoPreview'); if (pv) pv.style.display = 'none';
    const add = $('#fbPhotoAdd'); if (add) add.style.display = '';
  }
  if ($('#fbPhotoAdd')) $('#fbPhotoAdd').addEventListener('click', () => $('#fbPhotoInput') && $('#fbPhotoInput').click());
  if ($('#fbPhotoRemove')) $('#fbPhotoRemove').addEventListener('click', fbClearPhoto);
  if ($('#fbPhotoInput')) $('#fbPhotoInput').addEventListener('change', e => {
    const file = e.target.files && e.target.files[0]; if (!file) return;
    const rd = new FileReader();
    rd.onload = () => {
      const img = new Image();
      img.onload = () => {
        const max = 1200, scale = Math.min(1, max / Math.max(img.width, img.height));
        const w = Math.round(img.width * scale), h = Math.round(img.height * scale);
        const cv = document.createElement('canvas'); cv.width = w; cv.height = h;
        cv.getContext('2d').drawImage(img, 0, 0, w, h);
        _fbImage = cv.toDataURL('image/jpeg', 0.7);   // 壓過通常 <150KB
        const el = $('#fbPhotoImg'); if (el) el.src = _fbImage;
        const pv = $('#fbPhotoPreview'); if (pv) pv.style.display = '';
        const add = $('#fbPhotoAdd'); if (add) add.style.display = 'none';
      };
      img.onerror = () => toast('這張圖讀不了，換一張試試');
      img.src = rd.result;
    };
    rd.readAsDataURL(file);
  });
  if ($('#feedbackRow')) $('#feedbackRow').addEventListener('click', () => { fbApplyType(); fbClearPhoto(); $('#feedbackModal').classList.add('show'); });
  if ($('#fbTypes')) $('#fbTypes').addEventListener('click', e => {
    const b = e.target.closest('.topic-chip'); if (!b) return;
    _fbType = b.dataset.t;
    $('#fbTypes').querySelectorAll('.topic-chip').forEach(x => x.classList.toggle('on', x === b));
    fbApplyType();
  });
  if ($('#fbCats')) $('#fbCats').addEventListener('click', e => {
    const b = e.target.closest('.topic-chip'); if (!b) return;
    $('#fbCats').querySelectorAll('.topic-chip').forEach(x => x.classList.toggle('on', x === b));
  });
  if ($('#fbSend')) $('#fbSend').addEventListener('click', async () => {
    const text = ($('#fbText') && $('#fbText').value.trim()) || '';
    if (_fbType === 'nps' && _fbNps === null) { toast('先拉一下分數條，選個 0～10 的分數'); return; }
    if (_fbType !== 'nps' && !text) { toast('說一句就好，我們想聽'); return; }
    const cat = _fbType === 'bug' ? ((document.querySelector('#fbCats .topic-chip.on') || { dataset: {} }).dataset.c || '其他') : '';
    const body = { type: _fbType, category: cat, text: text, score: _fbNps, appVersion: (window.MuneaVersion && window.MuneaVersion.current) || '', plan: (window.MMPLAN && window.MMPLAN.get()) || '' };
    if (_fbImage) body.image = _fbImage;   // 選填附圖（已壓縮）
    brainPost('/feedback', body);
    trackProductEvent('feedback_submitted', { type: _fbType, category: cat, score: _fbNps, hasImage: !!_fbImage });
    $('#feedbackModal').classList.remove('show');
    if ($('#fbText')) $('#fbText').value = ''; _fbNps = null; fbClearPhoto(); const r = $('#npsRow'); if (r) r.querySelectorAll('.nps-btn').forEach(x => x.classList.remove('on'));
    toast(_fbType === 'praise' ? '收到了，寧寧會很開心！' : '收到了，謝謝你——我們會認真看');
  });

  // ===== App Store 評分彈窗：只在開心時刻、每版最多一次、負面情境絕不跳 =====
  // 對接約定（Mac）：原生實作 window.__muneaRequestReview()（蘋果原生評分視窗、系統自控全年上限）
  window.__muneaMaybeAskReview = function (moment) {
    try {
      const ver = (window.MuneaVersion && window.MuneaVersion.current) || '0';
      if (localStorage.getItem('munea.reviewAsked.' + ver)) return;               // 每版最多一次
      if (localStorage.getItem('munea.reviewCoolOff') === '1') return;            // 負面情境冷卻（斷線/錯誤後設）
      const chats = +(localStorage.getItem('munea.stat.chatsCompleted') || 0);
      const okMoment = (moment === 'chat_completed' && chats >= 3) || moment === 'activity_done';
      if (!okMoment) return;
      localStorage.setItem('munea.reviewAsked.' + ver, '1');
      trackProductEvent('review_prompt_shown', { moment: moment });
      if (typeof window.__muneaRequestReview === 'function') window.__muneaRequestReview();
    } catch (e) {}
  };
  if ($('#interestsSave')) $('#interestsSave').addEventListener('click', () => {
    saveInterests(_intSel);
    trackProductEvent('interests_saved', { count: _intSel.length });
    renderInterestPicks();
    toast(_intSel.length ? '記下了，這些話題我會多幫你留意新鮮事' : '好，不挑也行，想聊什麼直接說');
    closeInterests(true);
  });
  if ($('#interestsSkip')) $('#interestsSkip').addEventListener('click', () => closeInterests(true));
  if ($('#interestsModal')) $('#interestsModal').addEventListener('click', e => { if (e.target === $('#interestsModal')) closeInterests(false); });
  renderInterestPicks();
  // 彈窗通用 X（右上角）：掛 .mx-close 的按鈕一律關掉自己所在的視窗（7/8 Edward 巡檢後補齊）
  document.querySelectorAll('.mx-close').forEach(b => b.addEventListener('click', e => {
    e.stopPropagation();
    const mk = b.closest('.modal-mask');
    if (mk) mk.classList.remove('show');
  }));
  if ($('#termsRow')) $('#termsRow').addEventListener('click', () => openReader('terms'));
  if ($('#privacyPolicyRow')) $('#privacyPolicyRow').addEventListener('click', () => openReader('privacy'));
  if ($('#versionRow')) $('#versionRow').addEventListener('click', openVersionSheet);
  if ($('#verClose')) $('#verClose').addEventListener('click', () => $('#versionSheet').classList.remove('show'));
  applyAppVersion();
  if ($('#privacyRow')) $('#privacyRow').addEventListener('click', () => $('#dataModal').classList.add('show'));
  if ($('#dataClose')) $('#dataClose').addEventListener('click', () => $('#dataModal').classList.remove('show'));
  if ($('#dataModal')) $('#dataModal').addEventListener('click', e => { if (e.target === $('#dataModal')) $('#dataModal').classList.remove('show'); });
  if ($('#dataExportBtn')) $('#dataExportBtn').addEventListener('click', async () => {
    const b = $('#dataExportBtn');
    if (authState().status !== 'signed-in') { toast('請先登入，才能安全匯出只屬於你的資料'); return; }
    setBtnBusy(b, '正在送出申請');
    const result = await brainPost('/privacy-export', { action: 'request' });
    clearBtnBusy(b, '匯出一份給我');
    if (result && result.ok && result.status === 'queued') toast('匯出申請已送出；確認身分後會提供只屬於你的資料');
    else toast('匯出申請沒有送出，請確認網路後再試一次');
  });
  if ($('#dataDeleteBtn')) $('#dataDeleteBtn').addEventListener('click', () => {
    const b = $('#dataDeleteBtn');
    const signedIn = authState().status === 'signed-in';
    if (b.dataset.arm !== '1') {
      b.dataset.arm = '1';
      b.textContent = signedIn ? '再按一次：永久刪除帳號與資料' : '再按一次：清除這台裝置的資料';
      setTimeout(() => { b.dataset.arm = ''; b.textContent = '刪除我的資料'; }, 6000);
      return;
    }
    b.dataset.arm = ''; b.textContent = '刪除我的資料';
    (async () => {
      b.disabled = true;
      b.textContent = signedIn ? '正在永久刪除' : '正在清除';
      let deletion = null;
      if (signedIn) {
        deletion = await brainPost('/account-deletion', { action: 'request', reason: 'user_requested_in_app' });
        if (!(deletion && deletion.ok && deletion.accountDeleted)) {
          b.disabled = false;
          b.textContent = '刪除我的資料';
          toast('帳號與雲端資料尚未刪除，請確認網路後再試一次');
          return;
        }
        if (typeof signOutAuth === 'function') { try { await signOutAuth(); } catch (e) {} }
      }
      try {
        const ks = [];
        for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); if (k && k.indexOf('munea.') === 0) ks.push(k); }
        ks.forEach(k => localStorage.removeItem(k));
      } catch (e) {}
      $('#dataModal').classList.remove('show');
      if (!signedIn) toast('這台裝置上的沐寧資料已清除');
      else if (deletion.authUserDeleted) toast('帳號與雲端資料已永久刪除；Apple 訂閱需另行取消');
      else toast('雲端資料已刪除，登入帳號移除正在完成；Apple 訂閱需另行取消');
      setTimeout(() => { location.reload(); }, 1200);
    })();
  });
  if ($('#consentAgree')) $('#consentAgree').addEventListener('click', () => {
    try { localStorage.setItem('munea.consent.crossborder', new Date().toISOString()); } catch (e) {}
    trackProductEvent('crossborder_consent_given', {});
    $('#consentSheet').classList.remove('show');
    connectCall();
  });
  if ($('#consentDetail')) $('#consentDetail').addEventListener('click', () => { window.open('privacy.html', '_blank'); });
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
    if ($('#medDueDesc')) $('#medDueDesc').textContent = med.time + '的提醒 · 配溫開水就可以';
    if ($('#medDueName')) $('#medDueName').textContent = med.name;
    if ($('#medDueSay')) $('#medDueSay').textContent = med.time + '的藥，時間到囉';
    $('#medRemindModal').classList.add('show');
    // A6：寧寧親口說（App 開著時；打包後升級推播）
    try { if (typeof speakChat === 'function') speakChat(med.time + '的' + med.name + '，時間到囉。吃完跟我說一聲。'); } catch (e) {}
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
      pushFamilyFeed('<b>' + myFeedName() + '</b>' + medShowing.time + '的藥吃了，' + cname() + '有看著');
      trackProductEvent('routine_reminder_completed', { reminderType: 'medication' });
    }
    medShowing = null;
    $('#medRemindModal').classList.remove('show');
    toast('記下了，藥吃了。');
    renderPillTask();
  });
  if ($('#medSnooze')) $('#medSnooze').addEventListener('click', () => {
    medSnoozeUntil = Date.now() + 10 * 60 * 1000;
    medShowing = null;
    $('#medRemindModal').classList.remove('show');
    toast('好，10 分鐘後再提醒你。');
  });
  setInterval(checkDueMeds, 30000);
  setTimeout(checkDueMeds, 1500);
  // 回診前一天：開 app 提醒一次
  (function visitEve() {
    const arr = (typeof loadVisits === 'function') ? loadVisits() : [];
    const t = new Date(); t.setDate(t.getDate() + 1); const tIso = isoOf(t);
    const v = arr.find(x => x && x.dateISO === tIso);
    if (!v || sessionStorage.getItem('visitEveShown')) return;
    sessionStorage.setItem('visitEveShown', '1');
    let _when = ((String(v.label || '').split('）')[1]) || '').trim();
    if (!_when && v.time && typeof fmtVisitTime === 'function') _when = fmtVisitTime(v.time);
    setTimeout(() => toast('明天' + (_when ? _when + ' ' : '') + '回診，回診摘要我準備好了'), 1200);
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
    if (rec) {
      rec.answers = rec.answers || {};
      rec.answers['你'] = st.score;
      rec.myDone = true;
      const everyone = [...(rec.names || [])];
      if (everyone.every(n => rec.answers[n] !== undefined)) { rec.status = 'done'; rec.doneISO = isoOf(new Date()); }
      rec.score = st.score;
      saveActs(acts2);
    }
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
  // 中文時間／日期解析（聊聊自動建提醒用 · Edward 7/7）
  function zhDigit(s) {
    if (s == null) return NaN;
    s = String(s).replace('兩', '二');
    if (/^\d+$/.test(s)) return +s;
    const M = { 零: 0, 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9, 十: 10 };
    if (s in M) return M[s];
    let m = s.match(/^十([一二三四五六七八九])?$/); if (m) return 10 + (m[1] ? M[m[1]] : 0);
    m = s.match(/^([二三四五六七八九])十([一二三四五六七八九])?$/); if (m) return M[m[1]] * 10 + (m[2] ? M[m[2]] : 0);
    return NaN;
  }
  function parseZhClock(t) { // → 'HH:MM' 或 null
    const m = t.match(/(凌晨|清晨|早晨|早上|上午|中午|下午|傍晚|晚上|晚間|夜裡|半夜)?\s*([0-9一二兩三四五六七八九十]{1,3})\s*[點点時](半|[0-9一二兩三四五六七八九十]{1,3})?\s*分?/);
    if (!m) return null;
    let h = zhDigit(m[2]); if (isNaN(h)) return null;
    let mi = 0;
    if (m[3]) { if (m[3] === '半') mi = 30; else { const mm = zhDigit(m[3]); if (!isNaN(mm)) mi = mm; } }
    const p = m[1] || '';
    if (/(下午|傍晚|晚上|晚間|夜裡)/.test(p) && h < 12) h += 12;
    if (/中午/.test(p)) { if (h < 12) h = 12; }
    if (/(凌晨|半夜)/.test(p) && h === 12) h = 0;
    if (/(清晨|早晨|早上|上午)/.test(p) && h === 12) h = 0;
    if (h > 23) h = h % 24;
    return String(h).padStart(2, '0') + ':' + String(mi).padStart(2, '0');
  }
  function clockToSegment(hhmm) { const h = +String(hhmm).split(':')[0]; return h < 10 ? '早餐後' : h < 14 ? '午餐後' : h < 19 ? '晚餐後' : '睡前'; }
  function parseZhDate(t) { // → Date 或 null
    const now = new Date(); const base = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    if (/大後天/.test(t)) { base.setDate(base.getDate() + 3); return base; }
    if (/後天/.test(t)) { base.setDate(base.getDate() + 2); return base; }
    if (/明天|明日/.test(t)) { base.setDate(base.getDate() + 1); return base; }
    if (/今天|今日|等一下|待會/.test(t)) return base;
    const wm = t.match(/(這|本|下|下個|下一)?\s*(週|周|星期|禮拜|拜)\s*([一二三四五六日天末])/);
    if (wm) {
      const map = { 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 日: 0, 天: 0, 末: 6 };
      const target = map[wm[3]]; const d = new Date(base); let add = (target - d.getDay() + 7) % 7;
      if (add === 0) add = 7; if (/(下|下個|下一)/.test(wm[1] || '')) add += 7;
      d.setDate(d.getDate() + add); return d;
    }
    const dm = t.match(/(\d{1,2})\s*[\/月]\s*(\d{1,2})/);
    if (dm) { let d = new Date(now.getFullYear(), +dm[1] - 1, +dm[2]); if (d < base) d = new Date(now.getFullYear() + 1, +dm[1] - 1, +dm[2]); return d; }
    return null;
  }
  function parseChatIntent(t) {
    // 聊聊代辦：講一句、寧寧直接把 app 設定做好（原型版；真腦版走同一批動作）
    // 問點數：用真錢包數字回答、順帶安心話（不推銷）
    if (/(還剩幾點|剩幾點|剩多少點|點數還有|點數剩|我有幾點)/.test(t)) {
      const left = POINTS.total - POINTS.used + POINTS.bought;
      return left > 0
        ? '我看了一下，你還有 ' + left + ' 點，語音陪聊大概還能聊 ' + left + ' 分鐘。放心，就算用完，基本陪伴也不會斷。'
        : '點數用完了喔——補一些點數就能繼續跟我聊，設定裡就能加值。';
    }
    // 傳話：①「提醒／告訴 某人 …」直接算 ②「跟 某人」必須真的接「說」才算（防「有跟誰約好」這種閒聊誤觸發）
    // 7/9 正式化：名單改吃真的照護圈成員（不再寫死示範名）；圈外仍有通用中文名比對兜底
    let KNOWN_FAM = [];
    try { KNOWN_FAM = (typeof loadCircle === 'function' ? loadCircle() : []).map(m => m.name).filter(Boolean); } catch (e) {}
    let relay0 = null;
    for (const nm of KNOWN_FAM) {
      relay0 = t.match(new RegExp('(提醒|告訴)\\s*(' + nm + ')(說|，|要|來)?\\s*(.{2,30})')) || t.match(new RegExp('(跟)\\s*(' + nm + ')(說)\\s*(.{2,30})'));
      if (relay0) break;
    }
    if (!relay0) relay0 = t.match(/(提醒|告訴)\s*([一-龥]{2,3})(說|，|要|來)?\s*(.{2,30})/) || t.match(/(跟)\s*([一-龥]{2,3})(說)\s*(.{2,30})/);
    const relayBadWho = /[我你妳他她誰哪]/;
    if (relay0 && !relayBadWho.test(relay0[2])) {
      let who = relay0[2].replace(/[要說來]$/, '');
      if (who.length < 2) who = relay0[2];
      const _msg = relay0[4].replace(/^[要說來，]/, '').replace(/[。！]$/, '');
      const _pf = (typeof loadPersonProfile === 'function') ? loadPersonProfile() : {};
      const _me = _pf.nick || _pf.name || '家人';   // 暱稱優先、沒暱稱才名字
      pushFamilyFeed('<b>' + _me + '</b>要我提醒你：' + _msg);
      return '好，我幫你把話帶給' + who + '——他打開沐寧就會看到「' + _me + '要我提醒你：' + _msg + '」。';
    }
    // ===== 用藥提醒：聽到「幫我記得／提醒我…吃藥」→ 直接建好 =====
    const medTrig = /(提醒|記得|記錄|紀錄|幫我記|幫我排|安排|叫我)/.test(t);
    const medSig = /(吃藥|用藥|服藥)/.test(t) || (/(吃|服)\s*(「)?[一-龥A-Za-z0-9]{2,6}(」)?/.test(t) && /(藥|錠|膠囊|膜衣錠|優|血壓|糖|膽固醇|降|鈣|鐵|甲狀腺|抗凝)/.test(t));
    if (medTrig && medSig) {
      let name = (t.match(/(吃|服)\s*(「)?([一-龥A-Za-z0-9]{2,6}藥)/) || [])[3]
              || (t.match(/(吃|服)\s*(「)?([一-龥A-Za-z0-9]{2,4})/) || [])[3] || '';
      if (/^(的|一下|一顆|東西|飯|完)$/.test(name) || /(提醒|記得|時候|每天|天天|早上|中午|下午|晚上|睡前|點|要|了)/.test(name)) name = '';
      const clock = parseZhClock(t);
      const seg = (t.match(/(早餐後|午餐後|晚餐後|睡前)/) || [])[1] || (clock ? clockToSegment(clock) : '早餐後');
      const daysM = t.match(/(\d{1,3})\s*[天日]/);
      const days = daysM ? (daysM[1] + ' 天') : '長期';
      const meds = loadMeds();
      const med = { name: name || '藥', time: seg, days, by: '本人' };
      ensureMedReminderId(med);
      meds.push(med);
      try { localStorage.setItem('munea.meds', JSON.stringify(meds)); syncPush('meds', meds); } catch (e) {}
      syncMedicationReminder(med);
      updateMedCount();
      if (window.__medRefresh) { try { window.__medRefresh(); } catch (e3) {} }
      const whenSay = clock ? (clock + '（' + seg + '）') : seg;
      return '好，我幫你記下來了：' + (name ? '「' + name + '」' : '你的藥') + '，' + whenSay + '提醒你吃'
        + (days !== '長期' ? ('，連續 ' + days) : '') + '。到時間我會叫你，也會記下你有沒有吃。想改隨時跟我說。';
    }
    // ===== 回診提醒：聽到「記得我…回診」→ 抓日期＋時間建好 =====
    if (/(回診|看診|門診|複診|回院|要看醫生|去看醫生)/.test(t) && /(提醒|記得|記錄|紀錄|幫我記|排|安排|預約|要去|約|去)/.test(t)) {
      const d = parseZhDate(t);
      const clock = parseZhClock(t);
      if (d) {
        const wd = '日一二三四五六'[d.getDay()];
        const iso2 = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
        const timeStr = clock ? (' ' + clock) : (/(下午)/.test(t) ? ' 下午' : /(晚上|傍晚)/.test(t) ? ' 晚上' : /(上午|早上|早)/.test(t) ? ' 上午' : '');
        const label = (d.getMonth() + 1) + '/' + d.getDate() + '（週' + wd + '）' + timeStr;
        const visit = { id: Date.now(), title: '回診', dateISO: iso2, time: clock || '', label };
        try { localStorage.setItem('munea.visit', JSON.stringify({ dateISO: iso2, label })); } catch (e) {} syncPush('visit', { dateISO: iso2, label });
        try {
          const visits = JSON.parse(localStorage.getItem('munea.visits') || '[]') || [];
          visits.push(visit);
          localStorage.setItem('munea.visits', JSON.stringify(visits));
        } catch (e3) {}
        syncVisitReminder(visit);
        if (typeof renderVisitRow === 'function') try { renderVisitRow(); } catch (e2) {}
        return '記好了，' + label + '回診。我前一天會提醒你，回診要問醫生的、要帶的東西，也會先幫你準備好。';
      }
      return '好，跟我說是哪一天回診就好（像是「明天下午三點」「下週三」或「7 月 10 日」），我馬上幫你設。';
    }
    return null;
  }
  window.__chatTest = t => { const r = parseChatIntent(t); return r || chatReply(t); };
  window.__chatSay = t => chatHandle(t);
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
      if (_brainDegraded) {
        _brainDegraded = false;
        setCaption('接回來了，剛剛說的我都記著', '我們繼續');
        trackProductEvent('voice_brain_recovered', { turnCount: activeChatTurnCount });
      }
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
      if (!_brainDegraded) {
        _brainDegraded = true;
        setCaption('訊號不太穩，我先用簡單的方式陪你', '會自己接回來，聊的內容我都記著');
      }
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
    // 真即時語音模式（LiveVoice/Gemini）：麥克風鈕＝純靜音開關，絕不碰舊的打字/錄音備援（Edward 2026-07-10：不該有藍色狀態變打字）
    if (getLiveVoiceUrl() && typeof LiveVoice !== 'undefined' && LiveVoice.on) {
      micMuted = !micMuted;
      chatMic.classList.toggle('off', micMuted);
      try { LiveVoice.micOpen = !micMuted; } catch (e) {}   // 靜音＝停收音；開啟＝恢復（半雙工仍套用：她說話時本就靜音）
      setCallHint(micMuted ? '麥克風先關著，想說話再點一下' : '我在聽，你說吧');
      return;
    }
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
window.addEventListener('munea:locale-change', () => {
  voiceProvider.close();
  if (storageGet(ACCOUNT_BOOTSTRAP_KEY) === 'true') syncAccountBootstrap('update', { force: true, reason: 'locale_updated' });
});
