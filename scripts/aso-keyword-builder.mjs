#!/usr/bin/env node
/* 沐寧 · App Store 關鍵字欄產生器
 *
 * 為什麼要這支：蘋果分開索引「名稱／副標／關鍵字」三欄，但同一個詞寫兩次不會加分。
 * 所以關鍵字欄的 100 字元，只能放名稱與副標「沒用過」的詞——每次改標題副標都要重算一次，
 * 手算很容易漏。這支把它變成一行指令。
 *
 * 用法：
 *   node scripts/aso-keyword-builder.mjs "<App 名稱>" "<副標>"
 *
 * 例：
 *   node scripts/aso-keyword-builder.mjs "沐寧 Munea－全家人的 AI 照護管家" "陪爸媽聊天・提醒吃藥回診"
 *
 * 策略依據：docs/ASO與上線衝刺-施工包-2026-07-29.md
 */

const LIMIT = 100;   // 蘋果關鍵字欄上限（中文一字算一個字元，分隔逗號也算）

/* 候選詞庫。排序＝搜尋意圖強度，前面的優先塞。
 * 核心洞察：搜尋的人是 40-60 歲擔心爸媽的子女，不是長輩本人。
 * 所以這裡放的是「子女焦慮時會打的字」，不是「銀髮」「孝親」這種簡報用詞。 */
const CANDIDATES = [
  // 第一梯：子女焦慮的直接投射（最該搶的位置）
  '獨居', '長照', '長輩', '老人', '照顧', '聊天', '遠距',
  // 第二梯：長輩健康的高頻搜尋詞
  '血壓', '回診', '關心', '看護', '居家', '安養', '子女', '失能', '日照',
  // 第三梯：功能與情境補位
  '心情', '睡眠', '心率', '孤單', '對話', '通話', '視訊', '家庭', '親情',
  '問候', '溝通', '安全', '復健', '量測', '步數', '關懷'
];

/* Edward 2026-07-29 指定必放的詞。不參與去重、不參與排序，永遠排最前面塞滿。
 * 註記：「健康管家」「AI照護」的字名稱裡都有了，理論上蘋果能自己組合。
 * 但中文斷詞蘋果沒有公開文件，放完整詞組是保守安全的選擇；且算過空間夠，
 * 不必為了省字元冒這個不確定性。 */
const MUST_HAVE = ['健康管家', '高齡照護', '心靈陪聊', '家人圈', 'AI照護', '用藥看診提醒'];

/* 需要 Edward 拍板才放的詞。2026-07-29 Edward 拍板：不放失智。
 * 保留機制與詞本身，之後想加就跑 --with-judgment，不必改程式。 */
const NEEDS_JUDGMENT = ['失智'];

/* 剔除規則：候選詞若整個出現在名稱或副標裡，就是重複、必須拿掉。
 * 注意是「整詞比對」不是「單字比對」——蘋果中文索引是詞彙層級的。
 * 例：名稱有「照護管家」→「照護」重複要剔除；但「看護」沒出現過，那個「護」字不算重複。 */
function isDuplicate(word, taken) {
  return taken.includes(word);
}

function build(name, subtitle, withJudgment) {
  const taken = `${name}${subtitle}`;
  const kept = [];
  const dropped = [];
  const pool = withJudgment ? [...CANDIDATES, ...NEEDS_JUDGMENT] : CANDIDATES;

  for (const word of pool) {
    // 指定必放的詞不重複佔位（例：MUST_HAVE 已有「健康管家」，候選就不必再放「管家」）
    if (MUST_HAVE.some(m => m.includes(word))) dropped.push(word);
    else if (isDuplicate(word, taken)) dropped.push(word);
    else kept.push(word);
  }

  // 指定必放的詞永遠先塞、不參與去重
  const picked = [...MUST_HAVE];
  let used = MUST_HAVE.join(',').length;

  // 其餘照優先序貪心填滿（不跳過後面較短的詞，免得破壞意圖排序）
  for (const word of kept) {
    const cost = picked.length === 0 ? word.length : word.length + 1;   // +1 = 分隔逗號
    if (used + cost > LIMIT) continue;
    picked.push(word);
    used += cost;
  }

  return { result: picked.join(','), used, picked, dropped, unused: kept.filter(w => !picked.includes(w)) };
}

const argv = process.argv.slice(2);
const withJudgment = argv.includes('--with-judgment');
const [name, subtitle] = argv.filter(a => !a.startsWith('--'));

if (!name || !subtitle) {
  console.log(`
沐寧 · App Store 關鍵字欄產生器

用法：
  node scripts/aso-keyword-builder.mjs "<App 名稱>" "<副標>"

例：
  node scripts/aso-keyword-builder.mjs "沐寧 Munea－全家人的 AI 照護管家" "陪爸媽聊天・提醒吃藥回診"

它會自動剔除跟名稱／副標重複的詞（重複的字蘋果不加分，純浪費格子），
然後照搜尋意圖強度把 100 個字元填滿。
`);
  process.exit(1);
}

const { result, used, picked, dropped, unused } = build(name, subtitle, withJudgment);

console.log('');
console.log('  名稱：', name, `（${name.length} 字元）`);
console.log('  副標：', subtitle, `（${subtitle.length} 字元）`);
console.log('');
console.log('  ── 關鍵字欄（複製這行貼進蘋果後台）──');
console.log('');
console.log('  ' + result);
console.log('');
console.log(`  用了 ${used}/${LIMIT} 字元、共 ${picked.length} 個詞`);
if (dropped.length) console.log(`  已剔除（名稱或副標裡已經有了）：${dropped.join('、')}`);
if (unused.length) console.log(`  沒塞下（格子滿了）：${unused.join('、')}`);
console.log('');
console.log('  提醒：這是用搜尋意圖推理的起手式，不是真實搜尋量。');
console.log('  上線 2-3 週後看蘋果後台「App 分析 → 搜尋詞」的真數據再校準一次。');
console.log('');
