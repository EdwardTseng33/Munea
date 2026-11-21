# -*- coding: utf-8 -*-
"""產生 web/src/zh-vowel-table.js：常用國字（Big5 常用字 5401 字）→ 這個字講出來的嘴型序列（1～3 個，ㄅㄆㄇ 前面多一個閉嘴）。

讀音來源：pypinyin（MIT 授權，https://github.com/mozillazg/python-pinyin，資料來自 pinyin-data，MIT）。
只在產表時用，App 不帶 pypinyin；產出的表只有「字 → 嘴型序列」，約 20KB，用到才載。

嘴型代號（照調研 docs/research/人物對嘴自然度-調研-2026-11-21.md 附錄 B2，Azure zh-CN 對照表的做法：ㄛ 多半是滑過去的）：
  M＝閉（ㄅㄆㄇ）  A＝張開（ㄚ）  H＝微張（ㄜ、舌尖音、收尾鼻音）  I＝ㄧ扁寬  U＝ㄨㄩ圓小  O＝ㄛ圓開
用法：python build_vowel_table.py <pypinyin 所在資料夾> <輸出 js>"""
import sys, json
sys.path.insert(0, sys.argv[1])
from pypinyin import pinyin, Style

OUT = sys.argv[2]


def big5_common():
    """Big5 常用字區 0xA440–0xC67E（5401 字）。"""
    out = []
    for hi in range(0xA4, 0xC7):
        for lo in list(range(0x40, 0x7F)) + list(range(0xA1, 0xFF)):
            if (hi, lo) > (0xC6, 0x7E):
                break
            try:
                ch = bytes([hi, lo]).decode('big5')
            except UnicodeDecodeError:
                continue
            if '一' <= ch <= '鿿':
                out.append(ch)
    return out


SIBILANT_INITIALS = {'zh', 'ch', 'sh', 'r', 'z', 'c', 's'}
LABIAL = {'b', 'p', 'm'}
FINAL_TO_SEQ = {
    'a': 'A', 'ia': 'IA', 'ua': 'UA',
    'o': 'O', 'uo': 'UO',
    'e': 'H', 'en': 'H', 'eng': 'H', 'er': 'H',
    'ai': 'AI', 'uai': 'UAI',
    'ei': 'HI', 'uei': 'UI',
    'ao': 'AO', 'iao': 'IAO',
    'ou': 'OU', 'iou': 'IOU',
    'an': 'AH', 'ang': 'AH', 'ian': 'IH', 'iang': 'IA', 'uan': 'UA', 'uang': 'UA',
    'van': 'UH', 'üan': 'UH',
    'ie': 'IH', 've': 'UH', 'üe': 'UH',
    'i': 'I', 'in': 'I', 'ing': 'I',
    'u': 'U', 'ong': 'U', 'iong': 'U', 'ueng': 'U', 'uen': 'UH',
    'v': 'U', 'ü': 'U', 'vn': 'U', 'ün': 'U',
}


def shape_of(ch):
    fin = pinyin(ch, style=Style.FINALS, strict=True)[0][0]
    ini = pinyin(ch, style=Style.INITIALS, strict=True)[0][0]
    if fin == 'i' and ini in SIBILANT_INITIALS:
        seq = 'H'                       # 知吃詩日資雌思：整個字微張
    else:
        seq = FINAL_TO_SEQ.get(fin)
    if not seq:
        return None
    if ini in LABIAL:
        seq = 'M' + seq                 # ㄅㄆㄇ：一定先閉一下
    return seq


chars = big5_common()
groups, missing = {}, []
for ch in chars:
    s = shape_of(ch)
    if not s:
        missing.append(ch)
        continue
    groups.setdefault(s, []).append(ch)
body = ',\n'.join(f'    {json.dumps(k)}: {json.dumps("".join(v), ensure_ascii=False)}' for k, v in sorted(groups.items()))
js = f"""/* 中文字 → 嘴型（2026-11-21 寧寧多嘴型草稿用，開關 munea.faceExpressive 開了才載）。
   由 tools/ningning-rig/build_vowel_table.py 產生，請不要手改。
   讀音來源：pypinyin（MIT 授權）／pinyin-data（MIT 授權）；收 Big5 常用字 {len(chars) - len(missing)} 字。
   代號（每字 1～3 個，照順序）：M＝閉（ㄅㄆㄇ）A＝張開 H＝微張 I＝ㄧ U＝ㄨㄩ O＝ㄛ。對照依據：docs/research/人物對嘴自然度-調研-2026-11-21.md 附錄 B2。 */
(function (g) {{
  'use strict';
  var GROUPS = {{
{body}
  }};
  var map = Object.create(null);
  Object.keys(GROUPS).forEach(function (k) {{ var s = GROUPS[k]; for (var i = 0; i < s.length; i++) map[s[i]] = k; }});
  g.MuneaZhVowels = map;
}})(typeof window !== 'undefined' ? window : globalThis);
"""
open(OUT, 'w', encoding='utf-8', newline='\n').write(js)
print('chars', len(chars), 'mapped', len(chars) - len(missing), 'missing', len(missing), ''.join(missing[:20]),
      'bytes', len(js.encode('utf-8')), {k: len(v) for k, v in groups.items()})
