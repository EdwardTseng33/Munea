# -*- coding: utf-8 -*-
"""更新 web/src/auth-config.js（真帳號登入的公開瀏覽器設定）。

從 engine/.env.local 讀 SUPABASE_URL + SUPABASE_PUBLISHABLE_KEY（公開鑰匙、可進瀏覽器），
寫成 web/src/auth-config.js。此檔只含設計上可公開的 publishable key，需進 Repo，
讓 Web、Mac 與 CI 的包版結果一致；service-role key 永遠不可寫入。

用法：python scripts/gen-auth-config.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = os.path.join(ROOT, "engine", ".env.local")
OUT = os.path.join(ROOT, "web", "src", "auth-config.js")

# 2026-07-18 全庫連結盤點收尾（卡西法）：正式資料只在東京 fespbkdwafueyonppzwq；
# 雪梨 uhmpmystjjdqqxlpsthc 是 2026-07-15 遷移後淘汰的舊庫。這支腳本輸出的
# auth-config.js 是「App／Web 包版都吃這份」的正式來源，若有人拿舊的
# engine/.env.local（指雪梨）重跑，會把正式設定檔整份覆蓋成雪梨——直接鎖死。
TOKYO_SUPABASE_PROJECT_REF = "fespbkdwafueyonppzwq"


def read_env(path):
    vals = {}
    try:
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        sys.exit(f"找不到 {path}（要有 SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY）")
    return vals


env = read_env(ENV)
url = env.get("SUPABASE_URL", "")
key = env.get("SUPABASE_PUBLISHABLE_KEY", "")
if not url or not key:
    sys.exit("engine/.env.local 缺 SUPABASE_URL 或 SUPABASE_PUBLISHABLE_KEY")
if "service_role" in key or env.get("SUPABASE_SERVICE_ROLE_KEY", "") == key:
    sys.exit("⛔ 拒絕：這把是後台萬能鑰匙、不可進瀏覽器")
if TOKYO_SUPABASE_PROJECT_REF not in url:
    sys.exit(
        "⛔ 拒絕：engine/.env.local 的 SUPABASE_URL 不是東京正式庫"
        f"（要含 {TOKYO_SUPABASE_PROJECT_REF}，目前讀到 {url!r}）。"
        "這支只能對東京生成 auth-config.js，避免拿舊／測試設定把正式包版來源覆蓋成雪梨或其他庫。"
        "請先把 engine/.env.local 的 SUPABASE_URL 改成東京再重跑。"
    )

content = (
    "// Public Supabase browser configuration. Never place a server-only key here.\n"
    "window.MUNEA_SUPABASE_CONFIG = {\n"
    f"  url: '{url}',\n"
    f"  publishableKey: '{key}',\n"
    "  sdkUrl: 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/+esm',\n"
    "  redirectTo: new URL('index.html', window.location.href).toString(),\n"
    "  nativeRedirectTo: 'munea://auth/callback',\n"
    "  environment: 'production-tokyo',\n"
    "};\n\n"
    "window.MUNEA_DEV_CONFIG = {\n"
    "  enabled: false,\n"
    "  autoSignIn: false,\n"
    "  skipOnboarding: false,\n"
    "  seedFixtures: false,\n"
    "  bypassCallControl: false,\n"
    "  analyticsExcluded: true,\n"
    "};\n"
)
with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write(content)
print(f"OK → {OUT}（url 網域：{url.split('//')[-1][:30]}…、公開鑰匙已注入、environment=production-tokyo）")
