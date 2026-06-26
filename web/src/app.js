/* PeiNing 陪寧 — 原型互動
 * 落實 Claude Design「陪寧 CAREON 配色」+ Elfie 融入（安心存摺 / 今天一起完成 / 媽媽這週）
 * 標 [ENGINE] 處正式版接 castle-voice-engine（台語語音 + 三顆腦 + 擬真 avatar）。 */

const $  = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

const OVERLAYS = ['call', 'med', 'chat'];
let callTimer = null;

function showView(id) {
  $$('.screen').forEach(s => s.classList.toggle('active', s.id === id));
  const overlay = OVERLAYS.includes(id);
  $('#tabBar').classList.toggle('hidden', overlay);
  $$('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.view === id));
  const el = $('#' + id); if (el) el.scrollTop = 0;
  if (id === 'call') startCallTimer(); else stopCallTimer();
}

function startCallTimer() {
  let s = 0; if ($('#callTimer')) $('#callTimer').textContent = '00:00';
  clearInterval(callTimer);
  callTimer = setInterval(() => {
    s++; const m = String(Math.floor(s/60)).padStart(2,'0'); const ss = String(s%60).padStart(2,'0');
    if ($('#callTimer')) $('#callTimer').textContent = `${m}:${ss}`;
  }, 1000);
}
function stopCallTimer() { clearInterval(callTimer); }

// [ENGINE] 原型用瀏覽器內建語音；正式版換台語 TTS
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
  $('#tabBar').addEventListener('click', e => { const b = e.target.closest('.tab-btn'); if (b) showView(b.dataset.view); });

  $('#startCall').addEventListener('click', () => { showView('call'); say('陳奶奶，我在，看得到我嗎？'); });
  $('#toMed').addEventListener('click', () => { showView('med'); say('陳奶奶，吃藥時間到囉。'); });
  $('#endCall').addEventListener('click', () => showView('home'));
  $('#medTaken').addEventListener('click', () => { say('好，記下來了，連續六天，你真棒。'); showView('home'); });
  $('#medSnooze').addEventListener('click', () => showView('home'));

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

  // 找家人
  const ask = $('#askCall');
  if (ask) ask.addEventListener('click', () => say('好，我會提醒美華今晚打給你。'));

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

  // 聊聊：日常語音陪聊 · [ENGINE] 正式版換台語 STT/TTS + 反射腦
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
  function chatHandle(t) {
    if ($('#chatCaption')) $('#chatCaption').textContent = `你說：「${t}」`;
    setTimeout(() => { const r = chatReply(t); if ($('#chatCaption')) $('#chatCaption').textContent = r; say(r); }, 600);
  }
  const chatMic = $('#chatMic');
  if (chatMic) chatMic.addEventListener('click', () => {
    if (!SR2) { const s = prompt('（這個瀏覽器先用打字，正式版用台語語音）跟寧寧說什麼？'); if (s) chatHandle(s); return; }
    if (chatOn) { chatRec && chatRec.stop(); return; }
    chatRec = new SR2(); chatRec.lang = 'zh-TW'; chatRec.interimResults = false;
    chatRec.onstart = () => { chatOn = true; chatMic.classList.add('recording'); if ($('#chatCaption')) $('#chatCaption').textContent = '嗯，我聽著呢…'; if ($('#chatHint')) $('#chatHint').textContent = '再點一下結束'; };
    chatRec.onresult = e => chatHandle(e.results[0][0].transcript);
    chatRec.onend = () => { chatOn = false; chatMic.classList.remove('recording'); if ($('#chatHint')) $('#chatHint').textContent = '點麥克風，跟我說說話'; };
    chatRec.onerror = chatRec.onend;
    chatRec.start();
  });
  if ($('#chatEnd')) $('#chatEnd').addEventListener('click', () => showView('home'));

  if ('speechSynthesis' in window) speechSynthesis.onvoiceschanged = () => {};
}
document.addEventListener('DOMContentLoaded', init);
