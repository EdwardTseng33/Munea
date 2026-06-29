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
const TWO_D_AVATARS = new Set(['munea-2d-xiaoyun', 'munea-2d-ayuan', 'munea-2d-mimi', 'munea-2d-wangcai']);

/* ===== [ENGINE] 真角色腦：頭像 ↔ 角色名、對話狀態、跟伺服器要回話＋語音 ===== */
const AVA_TO_CHAR = {
  'nening-real-female': '寧寧', 'companion-real-male': '阿宏',
  'munea-2d-xiaoyun': '小昀', 'munea-2d-ayuan': '阿原',
  'munea-2d-mimi': '咪咪', 'munea-2d-wangcai': '旺財',
};
let currentChar = '寧寧';        // 設定頁選的角色，決定腦＋聲音
let currentAvatarId = 'nening-real-female';
let chatHistory = [];            // 多輪對話脈絡
let chatOpened = false;          // 這次進聊聊她有沒有先開過口
let chatAudio = null;

/* ===== AvatarRuntime：先把即時 avatar 的共用合約立起來 =====
 * mode=static-css 先用靜態圖 + CSS 呼吸/眨眼/聲波；之後 Ditto / LiveAvatar 只要接這層。 */
let speakTimer = null;
let visemeTimer = null;
const avatarRuntime = {
  modes: AVATAR_ENGINE_MODES,
  mode: AVATAR_ENGINE_MODES.STATIC_CSS,
  state: 'idle',
  viseme: 'rest',
  character: currentChar,
  resolveMode(avatarId = currentAvatarId) {
    const forced = new URLSearchParams(location.search).get('avatar');
    if (forced === '2d') return AVATAR_ENGINE_MODES.TWO_D_VISEME;
    if (forced === 'static') return AVATAR_ENGINE_MODES.STATIC_CSS;
    return TWO_D_AVATARS.has(avatarId) ? AVATAR_ENGINE_MODES.TWO_D_VISEME : AVATAR_ENGINE_MODES.STATIC_CSS;
  },
  setMode(mode) {
    const valid = Object.values(AVATAR_ENGINE_MODES).includes(mode);
    this.mode = valid ? mode : AVATAR_ENGINE_MODES.STATIC_CSS;
    const sc = $('#chat');
    if (sc) sc.dataset.avatarMode = this.mode;
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
    const fimg = $('#faceImg'); if (fimg && avatarId) fimg.src = 'avatars/' + avatarId + '.png';
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
    speakTimer = setTimeout(() => { if (this.state === 'speaking') this.setState('idle'); }, ms);
  },
  onAudioEnd() {
    if (this.state === 'speaking') this.setState('idle');
  },
};
window.MuneaAvatarRuntime = avatarRuntime;

function setFaceState(st) { avatarRuntime.setState(st); }
function faceSpeak(text, audioMs = 0) { avatarRuntime.speak(text, audioMs); }

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
  const isStaticPreview = location.port === '8135' || location.protocol === 'file:';
  if (isStaticPreview) return null;
  // 加超時護欄：語音腦連不上時，不卡死畫面（§6.5 降級鐵律：對話不斷、老實退回）
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), 6000);
  try {
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: ctrl.signal });
    if (!r.ok) return null;
    return await r.json();
  } catch (e) { return null; }
  finally { clearTimeout(to); }
}
// 進聊聊頁：她像朋友一樣「主動先開口」（帶記憶＋今日狀態）
async function enterChat() {
  if (chatOpened) return;
  chatOpened = true;
  setFaceState('idle');
  const cap = $('#chatCaption');
  if (cap) cap.textContent = '我在這裡，今天過得好嗎？';   // 先暖暖招呼、不留空白，等個人化開場回來再換
  const r = await brainPost('/open', { char: currentChar });
  if (r && r.reply) {
    if (cap) cap.textContent = r.reply;
    chatHistory.push({ role: 'model', text: r.reply });
    if (r.audio) playB64(r.audio); else say(r.reply);
    faceSpeak(r.reply);
  } else if (cap) {
    cap.textContent = '我在這裡，今天過得好嗎？想聊什麼都可以。';   // 沒真腦時的暖場
    faceSpeak(cap.textContent);
  }
}

function showView(id) {
  $$('.screen').forEach(s => s.classList.toggle('active', s.id === id));
  const overlay = OVERLAYS.includes(id);
  $('#tabBar').classList.toggle('hidden', overlay);
  $$('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.view === id));
  const el = $('#' + id); if (el) el.scrollTop = 0;
  if (id === 'chat') enterChat();
}

// [ENGINE] 原型用瀏覽器內建語音；正式版換中文（台灣）/英文語音接點
function say(text) {
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
function toggleTask(item) {
  const done = item.classList.toggle('done');
  if (done) say(CHEERS[item.dataset.task] || '做得很好。');
}

function init() {
  avatarRuntime.setCharacter(currentChar, currentAvatarId);
  avatarRuntime.setState('idle');
  $('#tabBar').addEventListener('click', e => { const b = e.target.closest('.tab-btn'); if (b) showView(b.dataset.view); });

  // 首頁「跟寧寧聊聊」＝ 進同一個全屏臉（不再有獨立視訊頁）
  if ($('#startCall')) $('#startCall').addEventListener('click', () => showView('chat'));
  // 用藥服務窗（獨立功能、保留）
  if ($('#medTaken')) $('#medTaken').addEventListener('click', () => { say('好，記下來了，連續六天，你真棒。'); showView('home'); });
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
  });

  // 全家健康圈：切換成員看健康
  function showFamPerson(p, rel, av) {
    $('#viewAll').classList.remove('active');
    $('#viewPerson').classList.add('active');
    if ($('#ptName')) $('#ptName').textContent = p;
    if ($('#ptRel')) $('#ptRel').textContent = rel || '';
    if ($('#ptAv') && av) $('#ptAv').src = av;
    $$('.fam-switch-item').forEach(b => b.classList.toggle('active', b.dataset.person === p));
    const v = $('#viewPerson'); if (v) v.scrollIntoView({ block: 'start' });
  }
  function showFamAll() {
    $('#viewPerson').classList.remove('active');
    $('#viewAll').classList.add('active');
    $$('.fam-switch-item').forEach(b => b.classList.toggle('active', b.dataset.person === 'all'));
  }
  const famSwitch = $('#famSwitch');
  if (famSwitch) famSwitch.addEventListener('click', e => {
    const b = e.target.closest('.fam-switch-item'); if (!b) return;
    const p = b.dataset.person;
    if (p === 'all') showFamAll();
    else if (p === 'invite') say('好，我幫你發邀請給家人，加進來就能互相關心健康。');
    else showFamPerson(p, b.dataset.rel, b.dataset.av);
  });
  const healthList = $('#healthList');
  if (healthList) healthList.addEventListener('click', e => {
    const r = e.target.closest('.health-row'); if (!r) return;
    showFamPerson(r.dataset.person, r.dataset.rel, r.dataset.av);
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
  if ($('#startChalBtn')) $('#startChalBtn').addEventListener('click', () => { closeChal(); say('好，邀請發出去了，等大家答應就開始。'); });
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
  $$('.chal-type').forEach(b => b.addEventListener('click', () => { $$('.chal-type').forEach(x => x.classList.remove('active')); b.classList.add('active'); }));
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
    const cap = $('#chatCaption');
    if (cap) cap.textContent = `你說：「${t}」`;
    chatHistory.push({ role: 'user', text: t });
    // [§6.2] 思考態：不空等轉圈，臉有「她在想」的活著感（< 1.5s 內回）
    setTimeout(() => { setFaceState('thinking'); if (cap && cap.textContent.startsWith('你說')) cap.textContent = '嗯…我想想'; }, 380);
    const r = await brainPost('/chat', { history: chatHistory, char: currentChar });
    if (r && r.reply) {                              // 真腦回話＋真聲音
      if (cap) cap.textContent = r.reply;
      chatHistory.push({ role: 'model', text: r.reply });
      if (r.audio) playB64(r.audio); else say(r.reply);
      faceSpeak(r.reply);
    } else {                                          // 沒真腦 → 退回規則版（純靜態 demo 也能動）
      const rr = chatReply(t);
      if (cap) cap.textContent = rr;
      chatHistory.push({ role: 'model', text: rr });
      say(rr);
      faceSpeak(rr);
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
    const cap = $('#chatCaption');
    if (!blob || !blob.size) {
      if (cap) cap.textContent = '沒有錄到聲音，我們再試一次。';
      setFaceState('idle');
      return;
    }
    if (cap) cap.textContent = '收到語音了，我先記下來。';
    const audio = await blobToDataUrl(blob);
    const r = await brainPost('/voice-note', { char: currentChar, audio, mime: blob.type || 'audio/webm', durationMs });
    if (r && r.ok) {
      if (cap) cap.textContent = r.reply || '語音已送出，下一步會接上即時理解。';
    } else {
      if (cap) cap.textContent = '這個裝置可以錄音，但目前先用打字繼續聊。';
      const s = prompt('我先用文字接住你，想跟寧寧說什麼？');
      if (s) chatHandle(s);
    }
    setFaceState('idle');
  }
  const chatMic = $('#chatMic');
  let mediaRec = null, mediaChunks = [], mediaStartedAt = 0;
  async function startVoiceCapture() {
    const cap = $('#chatCaption');
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
      const s = prompt('（這個裝置先用打字，正式版用即時語音）跟寧寧說什麼？');
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
      if (cap) cap.textContent = '我在錄音，說完再按一次。';
    } catch (e) {
      if (cap) cap.textContent = '目前拿不到麥克風權限，先用打字聊。';
      const s = prompt('想跟寧寧說什麼？');
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
    chatRec.onstart = () => { chatOn = true; chatMic.classList.add('recording'); setFaceState('listening'); if ($('#chatCaption')) $('#chatCaption').textContent = '嗯，我聽著呢…'; };
    chatRec.onresult = e => chatHandle(e.results[0][0].transcript);
    chatRec.onend = () => { chatOn = false; chatMic.classList.remove('recording'); if ($('#chat') && $('#chat').dataset.state === 'listening') setFaceState('idle'); };
    chatRec.onerror = chatRec.onend;
    chatRec.start();
  });
  if ($('#chatEnd')) $('#chatEnd').addEventListener('click', () => { chatOpened = false; showView('home'); });

  // 選角色 → 換那個角色的腦＋聲音＋名字，並重新認識（清對話）
  const avatarPick = $('#avatarPick');
  if (avatarPick) avatarPick.addEventListener('click', e => {
    const o = e.target.closest('.avo:not(.soon)'); if (!o) return;
    currentChar = AVA_TO_CHAR[o.dataset.ava] || '寧寧';
    chatHistory = []; chatOpened = false;
    avatarRuntime.setCharacter(currentChar, o.dataset.ava);
    if ($('#chatCaption')) $('#chatCaption').textContent = `${currentChar}在這裡，想聊什麼都可以。`;
  });

  if ('speechSynthesis' in window) speechSynthesis.onvoiceschanged = () => {};
}
document.addEventListener('DOMContentLoaded', init);
