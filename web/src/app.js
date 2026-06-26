/* PAINING 陪寧 — 原型互動
 * 落實 Claude Design「陪寧 CAREON 配色」+ Elfie 融入（安心存摺 / 今天一起完成 / 媽媽這週）
 * 標 [ENGINE] 處正式版接 castle-voice-engine（台語語音 + 三顆腦 + 擬真 avatar）。 */

const $  = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

const OVERLAYS = ['call', 'med'];
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
    say(`好，寧寧會轉達給媽媽——美華${b.dataset.react}了。`);
  });

  // 一鍵回診摘要
  const rep = $('#reportBtn');
  if (rep) rep.addEventListener('click', () => say('好，我把這個月的用藥和血壓整理成一張，回診給醫生看就清楚了。'));

  // 找家人
  const ask = $('#askCall');
  if (ask) ask.addEventListener('click', () => say('好，我會提醒美華今晚打給你。'));

  if ('speechSynthesis' in window) speechSynthesis.onvoiceschanged = () => {};
}
document.addEventListener('DOMContentLoaded', init);
