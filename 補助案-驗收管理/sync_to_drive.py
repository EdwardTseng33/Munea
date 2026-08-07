#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把最新的進度表寫回雲端硬碟上「同一份」檔案，不另外開新的。

Edward 2026-08-10 拍板：統一用 Munea補助案-查核與核銷 資料夾裡那份
「00-Munea補助案-驗收總進度表.xlsx」，不要每次多生一份。

用法：
    python build_progress_xlsx.py     # 先重生表
    python sync_to_drive.py           # 再寫回雲端同一份

鑰匙：專用服務帳號，鑰匙存在雲端保險箱（Secret Manager）的 munea-drive-sync-key，
不落地成檔案——每次執行時從保險箱拉進記憶體用完就丟。

這把鑰匙預設什麼都看不到；Edward 在雲端硬碟把資料夾分享給服務帳號的信箱，
它才碰得到那個資料夾。權限因此天然只限那一個資料夾，不是整個硬碟。

檢查狀態：
    python sync_to_drive.py --check
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"

# Edward 指定的那一份，連結永遠是這個，不要改。
FILE_ID = "10kTFpiDiDjelAwlvg9_P5gx5J6pA8aAi"
FOLDER_ID = "19LtbvxZevGZMAn2tfsitYrSUTNeaWZbs"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

GCP_PROJECT = "gen-lang-client-0229303523"
SECRET_NAME = "munea-drive-sync-key"
SERVICE_ACCOUNT = "munea-drive-sync@gen-lang-client-0229303523.iam.gserviceaccount.com"

SHARE_HINT = (
    f"這把鑰匙還碰不到那個資料夾。請在雲端硬碟把資料夾分享給它：\n\n"
    f"  1. 開 https://drive.google.com/drive/folders/{FOLDER_ID}\n"
    f"  2. 右鍵資料夾 →「共用」\n"
    f"  3. 貼上這個信箱，權限給「編輯者」：\n"
    f"     {SERVICE_ACCOUNT}\n"
    f"  4. 取消勾選「通知使用者」（它是程式、不會收信），按分享\n"
)


def latest_xlsx():
    if not OUT.exists():
        return None
    files = sorted(OUT.glob("00-Munea補助案-驗收總進度表-*.xlsx"))
    return files[-1] if files else None


def load_key():
    """從雲端保險箱把鑰匙拉進記憶體。刻意不寫成檔案——鑰匙不落地。"""
    cmd = [
        "gcloud", "secrets", "versions", "access", "latest",
        "--secret", SECRET_NAME, "--project", GCP_PROJECT,
    ]
    try:
        raw = subprocess.run(
            cmd, capture_output=True, check=True,
            shell=(os.name == "nt"),
        ).stdout
    except FileNotFoundError:
        raise SystemExit("找不到 gcloud，無法從雲端保險箱拿鑰匙。")
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        raise SystemExit(
            "拿不到鑰匙（保險箱 " + SECRET_NAME + "）：" + (detail[-1] if detail else "未知原因")
        )
    return json.loads(raw.decode("utf-8"))


def build_service():
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        raise SystemExit(
            "缺套件。先跑：pip install google-api-python-client google-auth-oauthlib"
        )

    creds = service_account.Credentials.from_service_account_info(
        load_key(), scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def check():
    service = build_service()
    try:
        meta = service.files().get(
            fileId=FILE_ID, fields="id,name,mimeType,modifiedTime,parents"
        ).execute()
    except Exception as exc:
        if "404" in str(exc) or "403" in str(exc):
            raise SystemExit(SHARE_HINT)
        raise
    print("授權正常，看得到目標檔案：")
    print("  檔名：", meta.get("name"))
    print("  類型：", meta.get("mimeType"))
    print("  上次修改：", meta.get("modifiedTime"))
    in_folder = FOLDER_ID in (meta.get("parents") or [])
    print("  在指定資料夾裡：", "是" if in_folder else "否（請確認 FILE_ID 對不對）")
    return 0


def push(path=None):
    from googleapiclient.http import MediaFileUpload

    src = Path(path) if path else latest_xlsx()
    if not src or not src.exists():
        raise SystemExit(
            "找不到要上傳的表。先跑：python build_progress_xlsx.py"
        )

    service = build_service()
    before = service.files().get(fileId=FILE_ID, fields="name,modifiedTime").execute()

    media = MediaFileUpload(str(src), mimetype=XLSX_MIME, resumable=False)
    # 只換內容、不換檔名也不換位置——連結因此保持不變，資料夾不會多出東西。
    after = service.files().update(
        fileId=FILE_ID, media_body=media, fields="id,name,modifiedTime,webViewLink"
    ).execute()

    print("已寫回同一份檔案：")
    print("  來源：", src.name, f"（{src.stat().st_size:,} bytes）")
    print("  檔名：", after.get("name"), "（沒有改名，連結不變）")
    print("  更新前：", before.get("modifiedTime"))
    print("  更新後：", after.get("modifiedTime"))
    print("  連結：", after.get("webViewLink"))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只檢查授權與目標檔案，不上傳")
    ap.add_argument("--file", help="指定要上傳的 .xlsx，省略則用 out/ 裡最新那份")
    args = ap.parse_args()
    return check() if args.check else push(args.file)


if __name__ == "__main__":
    sys.exit(main())
