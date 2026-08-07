/**
 * 本地對嘴 · 挑口型演算法守門（2026-08-08）
 *
 * 背景：正式線的聲音要先飛到台灣的顯示卡算嘴型再飛回來，來回 1~2 秒。
 * 那個延遲不只讓人等——業界文件明講「播放延遲超過 2 秒，回音消除品質受損」，
 * 於是她自己的聲音被當成使用者插話、把話掐掉＝Edward 8/8 報的斷字跳針。
 *
 * Google 官方確認 Gemini Live 只送聲音和文字、不給嘴型參數，所以不能等它支援。
 * 業界做法＝聲音一到就在本地當場算口型。這支測試釘住那個演算法：
 * 拿中文五個母音的標準共振峰合成頻譜，看它挑不挑得對。
 *
 * 跑法：node scripts/test-viseme-picker.js
 * 演算法正本在 tools/rive-lab/ning-lipsync.html 的 pickViseme()，兩邊要一致。
 */
// v2：改用語音學的標準做法——找出兩個最強的共振峰（F1／F2），看它們落在哪
// F1 高 = 嘴開得大；F2 高 = 舌頭前、嘴扁；F2 低 = 嘴圓
function pickViseme(freq, sampleRate){
  const nyq = sampleRate/2, n = freq.length;
  const hzOf = i => i/n*nyq;
  // 只看 200–3000Hz（人聲母音的共振峰都在這裡）
  const lo = Math.ceil(200/nyq*n), hi = Math.floor(3000/nyq*n);
  // 找 F1：200–1000Hz 裡最強的
  let f1=0, f1v=-1;
  for(let i=lo;i<=Math.floor(1000/nyq*n);i++){ if(freq[i]>f1v){ f1v=freq[i]; f1=hzOf(i); } }
  // 找 F2：1000–3000Hz 裡最強的
  let f2=0, f2v=-1;
  for(let i=Math.ceil(1000/nyq*n);i<=hi;i++){ if(freq[i]>f2v){ f2v=freq[i]; f2=hzOf(i); } }
  if(f1v<8 && f2v<8) return 'f-ahsmall';   // 幾乎沒能量

  // 標準母音四角：a(F1高) / i(F1低F2高) / u(F1低F2低) / e,o 在中間
  const open = f1 > 620;          // 嘴開得大
  const front = f2 > 1900;        // 舌前、嘴扁
  const round = f2 < 1100;        // 嘴圓

  if(open && !front) return 'f-a';
  if(!open && front) return 'f-i';
  if(!open && round) return f1 > 400 ? 'f-o' : 'f-u';   // 都是圓嘴，再用開口度分
  if(front) return 'f-e';         // F1 中等 + 前
  if(round) return 'f-o';         // F1 中等 + 圓
  return f1 > 450 ? 'f-e' : 'f-o';
}

const VOWELS = {
  'ㄚ (a)': { f1: 800,  f2: 1200, expect: 'f-a' },
  'ㄜ (e)': { f1: 500,  f2: 1500, expect: 'f-e' },
  'ㄧ (i)': { f1: 280,  f2: 2500, expect: 'f-i' },
  'ㄛ (o)': { f1: 450,  f2: 800,  expect: 'f-o' },
  'ㄨ (u)': { f1: 320,  f2: 700,  expect: 'f-u' },
};
const SR = 48000, BINS = 512;
function synth(f1, f2){
  const a = new Uint8Array(BINS), nyq = SR/2;
  for (let i=0;i<BINS;i++){
    const hz = i/BINS*nyq;
    a[i] = Math.min(255, Math.round(
      200*Math.exp(-Math.pow((hz-f1)/120,2)) +
      150*Math.exp(-Math.pow((hz-f2)/200,2)) +
      60*Math.exp(-hz/1500)));
  }
  return a;
}
console.log('=== v3：圓嘴再用開口度細分 ===\n');
let ok=0,total=0;
for (const [name, v] of Object.entries(VOWELS)){
  const got = pickViseme(synth(v.f1, v.f2), SR);
  const pass = got === v.expect; total++; if(pass) ok++;
  console.log(`  ${name.padEnd(9)} 期待 ${v.expect.replace('f-','').padEnd(3)} → 挑到 ${got.replace('f-','').padEnd(3)} ${pass?'✓':'✗'}`);
}
console.log(`\n  ${ok}/${total} 個母音挑對`);
if(ok !== total){ console.error('挑口型演算法退步了——五個母音沒有全對'); process.exit(1); }
