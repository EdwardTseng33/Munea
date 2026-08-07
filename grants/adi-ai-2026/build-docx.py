# -*- coding: utf-8 -*-
"""正式版 Word 產線：md → docx（含圖）→ 字體正規化＋表格框線 → 鏡像資料夾
用法：python build-docx.py [--no-sync]
2026-07-17 建：取代散裝流程；正式對外質感（微軟正黑體、主文加目錄、表格框線）。"""
import sys, shutil
from pathlib import Path
import pypandoc
from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Pt

BASE  = Path(r"E:\Claude\Munea\grants\adi-ai-2026")
SRC   = BASE / "draft"
BUILD = BASE / "build"
DST   = Path(r"C:\Users\Administrator\我的雲端硬碟\Munea 沐寧｜數產署AI補助申請（正式版）")

FILE_MAP = {  # 來源 md → 雲端 docx（主文帶 --toc）· 2026-07-18 改指 500 萬案現行版（舊 2000 萬對照表勿還原）
    "13-補件需求總清單.md":         ("00-📋補件需求總清單（先看這份）.docx", False),
    "30-500萬-計畫書完整版.md":     ("01-計畫書第一部分（含圖）.docx", True),
    "500萬案-工作計畫與甘特圖.md": ("02-時程人力經費表-工作計畫.docx", False),
    "22-500萬-經費表.md":           ("03-經費表（官方格式）.docx", False),
    "40-500萬-摘要表續.md":         ("04-計畫書摘要表續.docx", False),
    "06-企業導入意向書模板.md":     ("05-意向書模板（可轉發）.docx", False),
    "12-審查簡報骨架.md":           ("06-審查簡報骨架（500萬版）.docx", False),
}

def normalize_fonts(doc):
    """全文件字體統一：中文微軟正黑體、英數 Calibri→同系；標題黑色加粗。"""
    for style_name in ("Normal",):
        try:
            st = doc.styles[style_name]
            st.font.name = "Microsoft JhengHei"
            st.font.size = Pt(11)
            rpr = st.element.get_or_add_rPr()
            rfonts = rpr.find(qn("w:rFonts"))
            if rfonts is None:
                rfonts = OxmlElement("w:rFonts"); rpr.append(rfonts)
            rfonts.set(qn("w:eastAsia"), "Microsoft JhengHei")
            rfonts.set(qn("w:ascii"), "Microsoft JhengHei")
            rfonts.set(qn("w:hAnsi"), "Microsoft JhengHei")
        except KeyError:
            pass
    for st in doc.styles:
        if st.type is not None and st.name and st.name.startswith("Heading"):
            try:
                st.font.name = "Microsoft JhengHei"
                rpr = st.element.get_or_add_rPr()
                rfonts = rpr.find(qn("w:rFonts"))
                if rfonts is None:
                    rfonts = OxmlElement("w:rFonts"); rpr.append(rfonts)
                rfonts.set(qn("w:eastAsia"), "Microsoft JhengHei")
                color = rpr.find(qn("w:color"))
                if color is None:
                    color = OxmlElement("w:color"); rpr.append(color)
                color.set(qn("w:val"), "1A1A1A")
            except Exception:
                pass

def add_table_borders(doc):
    def borders(tbl):
        tblPr = tbl._tbl.tblPr
        for old in tblPr.findall(qn("w:tblBorders")):
            tblPr.remove(old)
        bs = OxmlElement("w:tblBorders")
        for edge in ("top","left","bottom","right","insideH","insideV"):
            el = OxmlElement(f"w:{edge}")
            el.set(qn("w:val"), "single"); el.set(qn("w:sz"), "4")
            el.set(qn("w:space"), "0"); el.set(qn("w:color"), "444444")
            bs.append(el)
        tblPr.append(bs)
    n = 0
    for t in doc.tables:
        borders(t); n += 1
        for row in t.rows:
            for cell in row.cells:
                for nt in cell.tables:
                    borders(nt); n += 1
    return n

def main(sync=True):
    sys.stdout.reconfigure(encoding="utf-8")
    BUILD.mkdir(exist_ok=True)
    for src_name, (dst_name, toc) in FILE_MAP.items():
        s = SRC / src_name
        if not s.exists():
            print(f"⚠ 缺來源：{src_name}"); continue
        out = BUILD / dst_name
        args = [f"--resource-path={SRC};{BASE}", "--standalone"]
        if toc:
            args += ["--toc", "--toc-depth=2", "-M", "toc-title=目錄"]
        pypandoc.convert_file(str(s), "docx", outputfile=str(out), extra_args=args)
        doc = Document(str(out))
        normalize_fonts(doc)
        nt = add_table_borders(doc)
        doc.save(str(out))
        note = f"表格框線×{nt}" + ("＋目錄" if toc else "")
        if sync and DST.is_dir():
            shutil.copy2(out, DST / dst_name)
            note += "＋已同步雲端"
        print(f"✓ {dst_name}  {out.stat().st_size//1024}KB  {note}")
    # 收掉雲端舊檔名版本（v2/v4 命名）
    if sync and DST.is_dir():
        stale = ["01-計畫書第一部分-v2定稿（含圖）.docx", "02-時程人力經費表-v4.docx",
                 "03-計畫書摘要表續-v4.docx", "04-審查簡報骨架17頁-v4.docx",
                 # 2000 萬案舊檔名（已入封存夾、根目錄不留）
                 "02-時程人力經費表.docx", "03-計畫書摘要表續.docx", "04-審查簡報骨架17頁.docx"]
        removed = []
        for name in stale:
            p = DST / name
            if p.exists():
                p.unlink(); removed.append(name)
        if removed:
            print("🗑️ 收掉舊版檔名（雲端垃圾桶可復原）:", "、".join(removed))

if __name__ == "__main__":
    main(sync="--no-sync" not in sys.argv)
