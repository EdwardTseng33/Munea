#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
從「進度表-正本.json」產生補助案驗收總進度表 .xlsx，並附帶 base64 以便上傳雲端硬碟。

用法：
    python build_progress_xlsx.py                 # 用今天（台灣時間）當版本日期
    python build_progress_xlsx.py --date 20260810 # 指定版本日期

產出：
    out/00-Munea補助案-驗收總進度表-<日期>.xlsx
    out/latest.b64      （上傳用的 base64，單行）
    out/latest.txt      （檔名、大小、統計，給人看的）
"""

import argparse
import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "進度表-正本.json"
OUT = ROOT / "out"

TAIPEI = timezone(timedelta(hours=8))

# 狀態 → (底色, 字色)。找不到就走「未開始」的灰。
STATUS_STYLE = {
    "完成": ("C6EFCE", "006100"),
    "等Edward": ("FFE0B2", "8A4B00"),
    "逾期": ("FFC7CE", "9C0006"),
    "里程碑": ("D9E7FD", "1F3864"),
    "進行中": ("FFF2CC", "7F6000"),
    "循環": ("E4DFEC", "4A3B6B"),
    "未開始": ("F2F2F2", "595959"),
}

HEAD_FILL = PatternFill("solid", fgColor="2F5597")
HEAD_FONT = Font(color="FFFFFF", bold=True, size=11)
TITLE_FONT = Font(bold=True, size=16, color="1F3864")
SUB_FONT = Font(size=10, color="595959")
THIN = Side(style="thin", color="D0D0D0")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")
WRAP_C = Alignment(wrap_text=True, vertical="center", horizontal="center")


def status_fill(status):
    bg, fg = STATUS_STYLE.get(str(status or "").strip(), STATUS_STYLE["未開始"])
    return PatternFill("solid", fgColor=bg), Font(color=fg, bold=True, size=10)


def write_table(ws, columns, rows, widths, start_row=1, status_col=None, pct_col=None):
    """寫一張標準表格：一列表頭 + N 列資料。status_col / pct_col 為 1-based 欄號。"""
    for idx, name in enumerate(columns, start=1):
        c = ws.cell(row=start_row, column=idx, value=name)
        c.fill, c.font, c.alignment, c.border = HEAD_FILL, HEAD_FONT, WRAP_C, BORDER
    ws.row_dimensions[start_row].height = 26

    for r, row in enumerate(rows, start=start_row + 1):
        for idx, val in enumerate(row, start=1):
            c = ws.cell(row=r, column=idx, value=val)
            c.alignment, c.border = WRAP, BORDER
            c.font = Font(size=10)
            if status_col and idx == status_col:
                fill, font = status_fill(val)
                c.fill, c.font, c.alignment = fill, font, WRAP_C
            if pct_col and idx == pct_col and isinstance(val, (int, float)):
                c.number_format = "0%"
                c.alignment = WRAP_C

    for idx, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = w
    ws.freeze_panes = ws.cell(row=start_row + 1, column=1)


def build(data, stamp):
    wb = Workbook()
    aug = data["august"]
    rows = aug["rows"]
    work = [r for r in rows if r[1] != "里程碑"]

    def count(*names):
        return sum(1 for r in work if str(r[7]).strip() in names)

    done, waiting, overdue, doing = count("完成"), count("等Edward"), count("逾期"), count("進行中")
    notyet = len(work) - done - waiting - overdue - doing

    # ---------- ① 怎麼看這份表 ----------
    ws = wb.active
    ws.title = "①怎麼看這份表"
    ws["A1"] = data["meta"]["title"]
    ws["A1"].font = TITLE_FONT
    ws["A2"] = data["meta"]["subtitle"]
    ws["A2"].font = SUB_FONT
    ws["A3"] = f"版本日期：{stamp}　｜　最後更新：{data['meta']['lastUpdated']}　｜　維護：{data['meta']['updatedBy']}"
    ws["A3"].font = SUB_FONT

    ws["A5"] = "八月進度一眼看"
    ws["A5"].font = Font(bold=True, size=13, color="1F3864")
    board = [
        ("已完成", done, "C6EFCE", "006100"),
        ("已逾期", overdue, "FFC7CE", "9C0006"),
        ("等你決定／你要做", waiting, "FFE0B2", "8A4B00"),
        ("還沒開始", notyet, "F2F2F2", "595959"),
        ("八月工作項合計", len(work), "D9E7FD", "1F3864"),
    ]
    for i, (label, num, bg, fg) in enumerate(board):
        col = 1 + i * 2
        a = ws.cell(row=6, column=col, value=label)
        a.font = Font(size=10, color=fg, bold=True)
        a.fill = PatternFill("solid", fgColor=bg)
        a.alignment = WRAP_C
        a.border = BORDER
        b = ws.cell(row=7, column=col, value=f"{num} 項")
        b.font = Font(size=18, bold=True, color=fg)
        b.fill = PatternFill("solid", fgColor=bg)
        b.alignment = WRAP_C
        b.border = BORDER
        ws.column_dimensions[get_column_letter(col)].width = 20
        ws.column_dimensions[get_column_letter(col + 1)].width = 2
    ws.row_dimensions[7].height = 32

    ws["A9"] = "本次更新"
    ws["A9"].font = Font(bold=True, size=11, color="1F3864")
    ws["A10"] = data["meta"].get("changeLog", "")
    ws["A10"].font = Font(size=10)
    ws.merge_cells(start_row=10, start_column=1, end_row=10, end_column=9)

    r = 12
    for k, v in data["howto"]:
        kc = ws.cell(row=r, column=1, value=k)
        kc.font = Font(bold=True, size=10, color="1F3864")
        kc.alignment = WRAP
        kc.border = BORDER
        vc = ws.cell(row=r, column=2, value=v)
        vc.alignment = WRAP
        vc.border = BORDER
        vc.font = Font(size=10)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=9)
        ws.row_dimensions[r].height = 34
        r += 1
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 30
    for i in range(3, 10):
        ws.column_dimensions[get_column_letter(i)].width = 14

    lk = ws.cell(row=r + 1, column=1, value="雲端資料夾（所有驗收文件都在裡面）")
    lk.font = Font(bold=True, size=10, color="1F3864")
    url = ws.cell(row=r + 1, column=2, value=data["meta"]["driveFolderUrl"])
    url.hyperlink = data["meta"]["driveFolderUrl"]
    url.font = Font(size=10, color="0563C1", underline="single")

    # ---------- ② 八月 ----------
    ws = wb.create_sheet("②8月-階段查核")
    write_table(ws, aug["columns"], rows, [9, 14, 22, 34, 15, 8, 8, 11, 8, 34],
                status_col=8, pct_col=9)

    # ---------- ③ 九月 ----------
    ws = wb.create_sheet("③9月-衝刺月")
    for i, line in enumerate(data["september"]["note"], start=1):
        c = ws.cell(row=i, column=1, value=line)
        c.font = Font(bold=(i == 1), size=11, color="1F3864" if i == 1 else "595959")
        ws.merge_cells(start_row=i, start_column=1, end_row=i, end_column=5)
    write_table(ws, data["september"]["columns"], data["september"]["rows"],
                [16, 26, 34, 18, 12], start_row=4, status_col=5)

    # ---------- ④ 十月 ----------
    ws = wb.create_sheet("④10月-查核與參展")
    write_table(ws, data["october"]["columns"], data["october"]["rows"],
                [8, 15, 26, 38, 18, 11, 11, 40], status_col=7)

    # ---------- ⑤ 十一月 ----------
    ws = wb.create_sheet("⑤11月-結案驗收")
    write_table(ws, data["november"]["columns"], data["november"]["rows"],
                [8, 24, 40, 18, 10, 11, 34], status_col=6)

    # ---------- ⑥ 交付文件連結 ----------
    ws = wb.create_sheet("⑥交付文件連結")
    lrows = [[a, b, ("開文件" if c else ""), d] for a, b, c, d in data["links"]["rows"]]
    write_table(ws, data["links"]["columns"], lrows, [10, 52, 14, 24])
    for i, (_, _, link, _) in enumerate(data["links"]["rows"], start=2):
        if link:
            c = ws.cell(row=i, column=3)
            c.hyperlink = link
            c.font = Font(size=10, color="0563C1", underline="single")
            c.alignment = WRAP_C

    # ---------- ⑦ 資料夾與檔名規則 ----------
    ws = wb.create_sheet("⑦資料夾與檔名規則")
    ws["A1"] = data["naming"]["intro"]
    ws["A1"].font = Font(size=10, color="595959")
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=3)
    write_table(ws, data["naming"]["columns"], data["naming"]["rows"],
                [30, 52, 34], start_row=3)

    return wb, dict(done=done, waiting=waiting, overdue=overdue, doing=doing,
                    notyet=notyet, total=len(work))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="版本日期 YYYYMMDD，省略則用今天（台灣時間）")
    args = ap.parse_args()

    stamp = args.date or datetime.now(TAIPEI).strftime("%Y%m%d")
    data = json.loads(SRC.read_text(encoding="utf-8"))
    wb, stats = build(data, stamp)

    OUT.mkdir(exist_ok=True)
    name = f"00-Munea補助案-驗收總進度表-{stamp}.xlsx"
    path = OUT / name
    wb.save(path)

    raw = path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    (OUT / "latest.b64").write_text(b64, encoding="ascii", newline="")

    # 純文字版八月表：給雲端試算表用（上傳成本低、Edward 可直接在雲端改）
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow([data["meta"]["title"] + "｜八月階段查核"])
    w.writerow([f"版本日期 {stamp}", f"最後更新 {data['meta']['lastUpdated']}", f"維護 {data['meta']['updatedBy']}"])
    w.writerow([f"完成 {stats['done']}", f"逾期 {stats['overdue']}", f"等Edward {stats['waiting']}",
                f"未開始 {stats['notyet']}", f"合計 {stats['total']} 項"])
    w.writerow([data["meta"].get("changeLog", "")])
    w.writerow([])
    w.writerow(data["august"]["columns"])
    for row in data["august"]["rows"]:
        w.writerow([
            f"{v:.0%}" if isinstance(v, float) else ("" if v is None else v)
            for v in row
        ])
    (OUT / "latest-八月.csv").write_text(buf.getvalue(), encoding="utf-8", newline="")

    summary = (
        f"檔名：{name}\n"
        f"大小：{len(raw):,} bytes　（base64 {len(b64):,} 字元）\n"
        f"八月：完成 {stats['done']}／逾期 {stats['overdue']}／等 Edward {stats['waiting']}／"
        f"進行中 {stats['doing']}／未開始 {stats['notyet']}　合計 {stats['total']} 項\n"
    )
    (OUT / "latest.txt").write_text(summary, encoding="utf-8", newline="\n")
    print(summary)


if __name__ == "__main__":
    main()
