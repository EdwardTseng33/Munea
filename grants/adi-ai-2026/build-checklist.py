# -*- coding: utf-8 -*-
"""待補資料清單 Excel 產線（放進 Google 雲端同步資料夾）
用法：python build-checklist.py
特性：重跑時會「保留 Edward 已打的勾與已回填的答案」，只更新項目內容。
2026-07-20 建：解決「原生 Google 試算表我只能建、不能改」的限制——改用 xlsx 放同步資料夾，我可反覆更新。
"""
import sys, os
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

DST = r"C:\Users\Administrator\我的雲端硬碟\Munea 沐寧｜數產署AI補助申請（正式版）\00-★待補資料清單.xlsx"

# (等級, 項目, 在哪處理, 連結／說明)
ROWS = [
    ("A 卡送件", "工商憑證 IC 卡可登入", "經濟部工商憑證管理中心 → 登入 DIGITAL+", "https://moeaca.nat.gov.tw｜沒辦過要跑幾個工作天；先確認卡在誰手上、有讀卡機"),
    ("A 卡送件", "近 3 年財報／營所稅 PDF 本體", "DIGITAL+ 自行上傳 PDF", "營業額數字已提供並納入計畫書；仍需財報或營所稅結算申報書『PDF 檔本身』供上傳（單檔 20MB 內）"),
    ("A 卡送件", "稅籍主行業代碼確認", "問記帳士（不用上傳）", "須為 J582／J62／J63；這是資格門檻、不是文件"),
    # ── ✅ 已納入計畫書（Edward 2026-07-21 補充資料）──
    ("✅已納入", "主要股東與持股比例", "已填入 壹一（二）", "來源：股東名冊；蔡盛全 46.59%、立健科技 20% 等 7 名股東"),
    ("✅已納入", "近 3 年營業額", "已填入 壹一（三）", "112:1,597萬→113:2,114萬→114:2,682萬（成長）"),
    ("✅已納入", "近 3 年研發費用", "已填入 壹一（三）", "0（前期自研以營運資金支應、未單列研發科目，已加註）"),
    ("✅已納入", "公司經營理念與沿革", "已填入 壹三（一）＋壹一", "AIoT→智慧醫療→AI 陪伴；ISO 27001(2022)"),
    ("✅已納入", "主要營業項目／SI 領域", "已填入 壹一＋摘要表", "AIoT/EMS/ESG碳盤查/智慧樓宇・工廠・醫療・園區"),
    ("✅已納入", "銷售模式與主要客戶", "已填入 壹一（四）", "專案型；智慧樓宇/工廠/醫療/園區業主"),
    ("✅已納入", "公司組織圖", "已填入 壹二（一）", "文字版部門架構（研發部為本計畫主體）"),
    ("✅已納入", "全公司人數與學歷分布", "已填入 壹二（二）", "12 人團隊配置；碩4／學士5／高職1／待確認2"),
    ("✅已納入", "友善職場措施", "已填入 壹三（二）", "性別友善廁所／中高齡身障／健檢津貼／彈性工時／托兒"),
    ("✅已納入", "資安現況 5 題", "已填入 資安章（一）", "ISO 27001(2022)＋防毒＋兩階段＋規章 已有；防火牆執行期建；窗口黃聖育"),
    ("✅已納入", "個人資料保護管理人員", "已填入 個資計畫", "黃聖育"),
    ("✅已納入", "增資規劃", "已填入 壹一", "無"),
    ("✅已納入", "公司獲獎／專利", "已填入 壹二（五）", "無（另列 ISO 27001 認證）"),
    ("✅已納入", "12 人前一份工作", "已填入團隊經歷", "來源：專任兼任人員學歷證照 docx"),
    # ── ✅ 團隊定案（2026-07-21 依薪資表重排職稱、已寫入計畫書）──
    ("✅已納入", "團隊 12 人職稱對頻＋學歷", "已寫入計畫書兩張團隊表", "依 2026/6 薪資表：薪資與人月不動、總預算 2,937,764 不變；管理職對頻研發、僅 1 個專案管理員額（曾宇晞）；蔡盛全＝業務負責→場域驗證／使用者研究；學歷已全部校正"),
    # ── B 還需你提供 ──
    ("B 跟公司要", "SI 代表性實績 2–3 項（具體案名）", "給蘇菲", "已寫領域級；若給 2–3 個具體案名＋客戶＋規模，執行力分數更高"),
    ("B 跟公司要", "12 人年資（年數）", "給蘇菲", "前職與學歷已補；只缺各人年資"),
    ("B 跟公司要", "12 人性別（算男女比）", "給蘇菲", "友善職場男女比欄待填"),
    ("B 跟公司要", "12 人薪轉／扣繳憑單（核銷用）", "給蘇菲", "皆為既有員工；人事費按實核銷需薪轉紀錄與扣繳憑單佐證"),
    ("B 跟公司要", "結案後增加就業人數", "給蘇菲", "效益欄『增加就業』——12 人皆既有人力，此欄填『結案後一年內預計新增 N 名』"),
    ("D 一句話拍板", "資安檢測機構名稱", "給蘇菲", "你有配合的資安公司→補名稱即可（計畫書已寫『既有配合機構』）"),
    ("D 一句話拍板", "退訂後資料保留天數", "給蘇菲", "建議 30 天"),
    ("D 一句話拍板", "曾宇晞到職 115/8 確認", "和蔡總確認", "已填 115 年 8 月；請與蔡總確認，並注意與前期 Munea 開發時序一致"),
    ("已完成", "計畫聯絡人資料", "已填入計畫書", "曾宇晞 0978-395-227"),
    ("已完成", "發明專利", "已決定不申請", "計畫書已改為「著作權＋營業秘密」，不再承諾專利"),
    ("已完成", "商標", "已決定不申請", "計畫書已移除商標申請規劃"),
    ("★送件動作", "計畫申請表暨企業聲明／同意書（附件3）", "DIGITAL+ 系統線上填", "https://digiplus.adi.gov.tw｜線上勾選簽署，我方自簽、12 條資格切結"),
    ("★送件動作", "建議迴避之人員清單（附件4）", "DIGITAL+ 系統線上填", "無則免填"),
    ("★送件動作", "企業申請計畫之個資同意書（附件5）", "DIGITAL+ 自行上傳", "官方範本填好轉 PDF 上傳"),
    ("★送件動作", "公職人員利益衝突揭露表（附件6）", "DIGITAL+ 自行上傳", "無則免附"),
    ("★送件動作", "計畫書（附件7）", "DIGITAL+ 部分線上填＋上傳 PDF", "蘇菲產出 Word→轉未加密 PDF；線上欄位我陪你逐格填"),
    ("★送件動作", "完成送出", "DIGITAL+", "建議 7/23 完成、不留到 7/24（截止 7/24 17:00）"),
    ("E 送件後補", "合作意向書 2–3 家", "審查階段補充佐證", "不在必交清單；審查前補上即可，仍是可行性加分"),
    ("E 送件後補", "場域合作機構全名", "給蘇菲", "隨意向書回收後填入"),
    ("E 送件後補", "Cares Expo 攤位費與報名截止", "主辦侒可傳媒（詢問信已擬）", "https://caresexpo.com｜只影響經費估算精度，總額不動"),
    ("★審查階段", "審查簡報電子檔", "DIGITAL+ 自行上傳", "進到審查才要；骨架已備（雲端 06 號檔）"),
    ("F 執行中補", "委外處理者清單與資料處理協議", "簽約前辦理", "雲端與 AI 服務供應商"),
    ("F 執行中補", "企業席次合約個資條款", "簽約前辦理", ""),
    ("F 執行中補", "資安規章與端點防護建置", "執行期辦理", "現在沒有就誠實寫「執行期建立」，本來就是計畫要做的事"),
]

HEADERS = ["完成", "編號", "等級", "需要補的資料", "在哪處理", "連結／說明", "回填欄（答案打這格）"]
LEVEL_FILL = {
    "A 卡送件":   "FFD9D9",
    "⚠️團隊對頻": "FFC7CE",
    "B 跟公司要": "FFE9CC",
    "C 你自己答": "DDF3DD",
    "D 一句話拍板": "DDEBF7",
    "★送件動作":  "EADCF5",
    "★審查階段":  "EADCF5",
    "E 送件後補": "FFF7CC",
    "F 執行中補": "EFEFEF",
    "✅已納入":   "D6E4BC",
    "已完成":     "E2F0D9",
}

def main():
    # 讀舊檔，保留 Edward 已打的勾與回填答案（用「項目名稱」對應）
    keep = {}
    if os.path.exists(DST):
        try:
            old = load_workbook(DST)
            ws_old = old.active
            for r in ws_old.iter_rows(min_row=2, values_only=True):
                if r and len(r) >= 7 and r[3]:
                    keep[str(r[3])] = (r[0], r[6])   # 完成, 回填欄
        except Exception as e:
            print("（舊檔讀取略過）", e)

    wb = Workbook(); ws = wb.active; ws.title = "待補資料清單"
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws.append(HEADERS)
    for c in range(1, len(HEADERS) + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = Font(bold=True, color="FFFFFF", size=11)
        cell.fill = PatternFill("solid", fgColor="2E8A83")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border

    for i, (lvl, item, where, note) in enumerate(ROWS, start=1):
        done, answer = keep.get(item, (None, None))
        if done is None:
            done = True if lvl in ("已完成", "✅已納入") else False
        ws.append([done, i, lvl, item, where, note, answer if answer else ""])
        row = ws.max_row
        fill = PatternFill("solid", fgColor=LEVEL_FILL.get(lvl, "FFFFFF"))
        for c in range(1, len(HEADERS) + 1):
            cell = ws.cell(row=row, column=c)
            cell.border = border
            cell.alignment = Alignment(vertical="center", wrap_text=(c in (4, 5, 6, 7)))
            if c == 3:
                cell.fill = fill
            if c == 1:
                cell.alignment = Alignment(horizontal="center", vertical="center")

    widths = {"A": 7, "B": 6, "C": 14, "D": 34, "E": 26, "F": 46, "G": 30}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(HEADERS))}{ws.max_row}"

    os.makedirs(os.path.dirname(DST), exist_ok=True)
    wb.save(DST)
    print(f"✓ 已寫入：{DST}")
    print(f"  共 {len(ROWS)} 項；保留了 {len([k for k in keep if k])} 筆既有紀錄")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
