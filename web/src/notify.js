/* 沐寧 · 本機提醒通知橋接（原生程式：ios/App/App/NotifyPlugin.swift）
   App 關著也會到點響：吃藥（每日重複、跟作息時間走）＋回診（提前 1 小時、單次）。
   - 只在 App 裡才會動；網頁預覽空轉。
   - 資料來源直接讀 localStorage（munea.meds / munea.routine / munea.visits），
     app.js 在用藥/看診/作息變動後呼叫 MuneaNotify.sync() 整批重排。 */
window.MuneaNotify = (function () {
  var _t = null, _asked = false;
  function plugin() {
    return (window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.Notify) || null;
  }
  function routineTimes() {
    var rt = { b: '07:30', l: '12:00', d: '18:00', s: '22:00' };
    try { rt = Object.assign(rt, JSON.parse(localStorage.getItem('munea.routine') || '{}')); } catch (e) {}
    return rt;
  }
  // 時段 → 實際提醒時間（餐後 = 該餐 +30 分、睡前 = 就寢 −30 分，跟 App 內用藥時間一致）
  function slotTime(slot) {
    var map = { '早餐後': ['b', 30], '午餐後': ['l', 30], '晚餐後': ['d', 30], '睡前': ['s', -30] };
    var m = map[slot];
    if (!m) return null;
    var p = String(routineTimes()[m[0]] || '08:00').split(':');
    var mins = ((+p[0] || 8) * 60 + (+p[1] || 0) + m[1] + 1440) % 1440;
    return { hour: Math.floor(mins / 60), minute: mins % 60 };
  }
  function buildItems() {
    var items = [];
    // 吃藥：同時段的藥併成一則、每天重複
    var meds = [];
    try { meds = JSON.parse(localStorage.getItem('munea.meds')) || []; } catch (e) {}
    var slots = {};
    meds.forEach(function (md) {
      String(md.time || '').split('、').forEach(function (raw) {
        var s = raw.trim();
        if (s) (slots[s] = slots[s] || []).push(String(md.name || '藥').split(/\s+/)[0]);
      });
    });
    Object.keys(slots).forEach(function (s) {
      var t = slotTime(s);
      if (!t) return;
      items.push({ id: 'med-' + s, title: '該吃藥了', body: s + '的藥：' + slots[s].join('、') + '。吃完回沐寧打個勾，家人就放心了。', hour: t.hour, minute: t.minute, repeats: true });
    });
    // 家庭活動（揪一攤）：活動前 30 分鐘提醒（Edward 7/9）
    var acts = [];
    try { acts = JSON.parse(localStorage.getItem('munea.activities')) || []; } catch (e) {}
    if (Array.isArray(acts)) acts.forEach(function (a) {
      if (!a || a.kind !== 'event' || !a.dateISO) return;
      var d = new Date(a.dateISO + 'T' + (a.time || '18:00'));
      if (isNaN(d)) return;
      var r = new Date(d.getTime() - 30 * 60 * 1000);
      if (r <= new Date()) return;
      items.push({ id: 'act-' + a.id, title: (a.title || '家庭聚會') + ' 快到了', body: '再 30 分鐘：' + (a.title || '聚會') + (a.place ? ' 在 ' + a.place : '') + '，別忘了喔。', year: r.getFullYear(), month: r.getMonth() + 1, day: r.getDate(), hour: r.getHours(), minute: r.getMinutes() });
    });
    // 回診：提前 1 小時、單次
    var visits = [];
    try { visits = JSON.parse(localStorage.getItem('munea.visits')) || []; } catch (e) {}
    if (Array.isArray(visits)) visits.forEach(function (v) {
      if (!v || !v.dateISO) return;
      var d = new Date(v.dateISO + 'T' + (v.time || '09:00'));
      if (isNaN(d)) return;
      var r = new Date(d.getTime() - 60 * 60 * 1000);
      if (r <= new Date()) return;
      items.push({ id: 'visit-' + v.id, title: (v.title || '回診') + '提醒', body: '等等 ' + (v.time || '') + (v.label ? ' 在' + v.label : '') + '，記得帶健保卡，想問醫生的沐寧都幫你記著。', year: r.getFullYear(), month: r.getMonth() + 1, day: r.getDate(), hour: r.getHours(), minute: r.getMinutes() });
    });
    return items;
  }
  // 整批重排（有小緩衝：連續變動只排一次）
  function sync() {
    var p = plugin();
    if (!p) return;
    clearTimeout(_t);
    _t = setTimeout(async function () {
      var items = buildItems();
      if (items.length && !_asked) {
        _asked = true;
        try { var r = await p.requestPermission(); if (!r || !r.granted) return; } catch (e) { return; }
      }
      try { await p.sync({ items: items }); } catch (e) {}
    }, 800);
  }
  return { available: function () { return !!plugin(); }, sync: sync, boot: sync };
})();
