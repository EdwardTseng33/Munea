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

content = (
    "// Public Supabase browser configuration. Never place a server-only key here.\n"
    "window.MUNEA_SUPABASE_CONFIG = {\n"
    f"  url: '{url}',\n"
    f"  publishableKey: '{key}',\n"
    "  sdkUrl: 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/+esm',\n"
    "  redirectTo: new URL('index.html', window.location.href).toString(),\n"
    "  nativeRedirectTo: 'munea://auth/callback',\n"
    "};\n\n"
    "window.MUNEA_DEV_CONFIG = {\n"
    "  enabled: false,\n"
    "  autoSignIn: false,\n"
    "  skipOnboarding: false,\n"
    "  analyticsExcluded: true,\n"
    "};\n"
)
with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write(content)
print(f"OK → {OUT}（url 網域：{url.split('//')[-1][:30]}…、公開鑰匙已注入）")
