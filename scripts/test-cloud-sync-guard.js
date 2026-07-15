#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

const source = fs.readFileSync(path.join(__dirname, '..', 'web', 'src', 'app.js'), 'utf8');
const checks = [
  ['pull single-flight', 'if (_syncPullPromise) return _syncPullPromise'],
  ['pull cooldown', 'Date.now() - _syncPullCompletedAt < minIntervalMs'],
  ['background pull pause', "document.visibilityState === 'hidden'"],
  ['single family polling timer', 'if (_familySyncTimer) clearInterval(_familySyncTimer)'],
  ['single foreground listener', 'if (!_familyVisibilityBound)'],
  ['push coalescing', '_syncPushTimers.has(key)'],
  ['identical push suppression', 'Date.now() - previous.at < 30000'],
];

for (const [label, token] of checks) {
  if (!source.includes(token)) throw new Error(`${label}: missing ${token}`);
  console.log(`PASS ${label}`);
}

// 用藥照片只留本機、不上雲（隱私政策對外承諾 + App Privacy 問卷填答）。
// 2026-07-09 的修正只補了 /family/state，漏掉 /routine-reminders，照片持續上雲。
// 這裡逐一檢查「每一條會把用藥資料送出去的路徑」，而不是只比對某一句字串。
// 註解裡提到 photo 不算違規——只看真正會執行的程式碼。
function stripComments(code) {
  return code.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/[^\n]*/g, '$1');
}
function functionBody(name) {
  const start = source.indexOf(`function ${name}(`);
  if (start === -1) throw new Error(`photo privacy: function ${name}() not found in app.js`);
  let depth = 0;
  let i = source.indexOf('{', start);
  const open = i;
  for (; i < source.length; i++) {
    if (source[i] === '{') depth++;
    else if (source[i] === '}' && --depth === 0) return stripComments(source.slice(open, i + 1));
  }
  throw new Error(`photo privacy: could not parse ${name}()`);
}

// 1. 送往 /routine-reminders 的 payload 不得含照片
const syncMed = functionBody('syncMedicationReminder');
if (/\bphoto\b/.test(syncMed)) {
  throw new Error('photo privacy: syncMedicationReminder() still sends a photo to /routine-reminders');
}
console.log('PASS med photo not sent to /routine-reminders');

// 2. 送往 /family/state 的 meds 仍須剝除照片
if (!source.includes('delete rest.photo')) {
  throw new Error('photo privacy: family state sync no longer strips med photos');
}
console.log('PASS med photo stripped from family state sync');

// 3. 不得從雲端回讀照片
const toLocalMed = functionBody('reminderToLocalMed');
if (/schedule\.photo/.test(toLocalMed)) {
  throw new Error('photo privacy: reminderToLocalMed() reads photo back from the cloud');
}
console.log('PASS med photo not read back from cloud');

// 4. 雲端合併時必須把本機照片貼回——否則照片會在每次同步後從使用者手機上消失
const refresh = functionBody('refreshRoutineRemindersFromBackend');
if (!/localPhotoByKey/.test(refresh)) {
  throw new Error('photo privacy: cloud merge no longer preserves the local med photo (photos would vanish on sync)');
}
console.log('PASS local med photo preserved across cloud merge');

console.log('Cloud sync request guard PASS');
