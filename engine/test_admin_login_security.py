# -*- coding: utf-8 -*-
"""後台登入加固（2026-11-08 沙利曼盤點後修）

守的線：
  1. 防猜計數（登入 + 邀請碼）取 X-Forwarded-For 的『最後一個』值（Google
     Front End 親自蓋的真實來源），不能再用攻擊者自己塞得動的『第一個』值——
     舊寫法等於沒鎖，攻擊者每次換一個假第一棒就重新歸零計數。
  2. /admin/login 成功後發的是 8 小時就過期的短期憑證，不是跟 6 個 Cloud
     Scheduler 定時任務共用、永不過期的萬能通行碼；萬能通行碼仍要能通過
     admin_authorized（定時任務不能壞）。
  3. 短期憑證過期、被竄改都要被拒絕。

跑法：python engine/test_admin_login_security.py
"""
import os
import sys
import time

os.environ.setdefault("GEMINI_API_KEY", "admin-login-security-test-key")
sys.path.insert(0, os.path.dirname(__file__))

import server

FAILS = []


def check(name, cond):
    print(("  OK  " if cond else " FAIL ") + name)
    if not cond:
        FAILS.append(name)


# ────────────────────────────────────────────────────────────────
# 1. client_ip_from_headers：取最後一個值，不是第一個
# ────────────────────────────────────────────────────────────────

ip_a = server.client_ip_from_headers({"X-Forwarded-For": "1.2.3.4, 9.9.9.9"})
check("多段 XFF 取最後一個值（GFE 蓋的章）", ip_a == "9.9.9.9")

ip_b = server.client_ip_from_headers({"X-Forwarded-For": "9.9.9.9"})
check("單段 XFF 原樣取用", ip_b == "9.9.9.9")

ip_c = server.client_ip_from_headers({}, fallback_addr="127.0.0.1")
check("沒有 XFF 時退回連線位址", ip_c == "127.0.0.1")

ip_d = server.client_ip_from_headers({"X-Forwarded-For": ""}, fallback_addr="127.0.0.1")
check("XFF 是空字串時也退回連線位址", ip_d == "127.0.0.1")

# 攻擊者能左右『第一段』、但左右不了 GFE 蓋在最後一段的真實來源——
# 同一個真實來源、不同的偽造第一段，必須被算成同一個人。
spoofed_1 = server.client_ip_from_headers({"X-Forwarded-For": "6.6.6.1, 203.0.113.9"})
spoofed_2 = server.client_ip_from_headers({"X-Forwarded-For": "6.6.6.2, 203.0.113.9"})
check("偽造第一段無法讓同一來源算成不同人（最後一段才算數）", spoofed_1 == spoofed_2 == "203.0.113.9")


# ────────────────────────────────────────────────────────────────
# 2. 防猜計數用上面那支函式算出的值，真的鎖得住（不會被偽造第一段繞過）
# ────────────────────────────────────────────────────────────────

real_attacker_ip = "203.0.113.50"
for i in range(server.LOGIN_MAX_FAILS):
    # 每次都用不同的偽造第一段，模擬攻擊者想繞過計數
    headers = {"X-Forwarded-For": f"10.0.0.{i}, {real_attacker_ip}"}
    cip = server.client_ip_from_headers(headers, fallback_addr="")
    server.record_login_failure(cip)

blocked = server.login_rate_limited(server.client_ip_from_headers(
    {"X-Forwarded-For": f"10.0.0.99, {real_attacker_ip}"}, fallback_addr=""
))
check(f"登入錯 {server.LOGIN_MAX_FAILS} 次後（偽造第一段也擋得住）", blocked is True)

# 邀請碼防猜同一套邏輯
real_invite_attacker = "203.0.113.60"
for i in range(server.INVITE_MAX_FAILS):
    headers = {"X-Forwarded-For": f"10.1.1.{i}, {real_invite_attacker}"}
    cip = server.client_ip_from_headers(headers, fallback_addr="")
    server.record_invite_failure(cip)
invite_blocked = server.invite_rate_limited(server.client_ip_from_headers(
    {"X-Forwarded-For": f"10.1.1.200, {real_invite_attacker}"}, fallback_addr=""
))
check(f"邀請碼錯 {server.INVITE_MAX_FAILS} 次後（偽造第一段也擋得住）", invite_blocked is True)


# ────────────────────────────────────────────────────────────────
# 3. 短期後台憑證：簽發／驗證／過期／竄改
# ────────────────────────────────────────────────────────────────

os.environ["MUNEA_ADMIN_API_TOKEN"] = "scheduler-standing-token-xyz"
os.environ["MUNEA_ADMIN_EMAIL"] = "boss@example.com"
os.environ["MUNEA_ADMIN_PASSWORD"] = "correct-horse-battery-staple"
os.environ.pop("MUNEA_ADMIN_SESSION_SECRET", None)  # 用衍生密語那條路

now = time.time()
token = server.issue_admin_session_token(now=now)
check("簽得出短期憑證（萬能通行碼已設定）", bool(token) and token.count(".") == 2)

check("剛簽發的短期憑證立刻驗得過", server.verify_admin_session_token(token, now=now + 1))
check("短期憑證在效期內（7 小時 59 分）驗得過",
      server.verify_admin_session_token(token, now=now + server.ADMIN_SESSION_TOKEN_TTL_SECONDS - 60))
check("短期憑證過期（8 小時整之後）被拒絕",
      not server.verify_admin_session_token(token, now=now + server.ADMIN_SESSION_TOKEN_TTL_SECONDS + 1))

tampered_sig = token.rsplit(".", 1)[0] + "." + ("0" * 64)
check("竄改簽章的短期憑證被拒絕", not server.verify_admin_session_token(tampered_sig, now=now))

parts = token.split(".")
tampered_exp = f"{parts[0]}.{int(parts[1]) + 999999}.{parts[2]}"
check("竄改到期時間但簽章對不上的憑證被拒絕", not server.verify_admin_session_token(tampered_exp, now=now))

check("空字串憑證被拒絕", not server.verify_admin_session_token(""))
check("None 憑證被拒絕", not server.verify_admin_session_token(None))
check("格式不對（缺一段）的憑證被拒絕", not server.verify_admin_session_token("v1.123456"))


# ────────────────────────────────────────────────────────────────
# 4. admin_authorized：萬能通行碼（定時任務）與短期憑證（後台登入）兩條路並存
# ────────────────────────────────────────────────────────────────

standing_token = os.environ["MUNEA_ADMIN_API_TOKEN"]
ok, code = server.admin_authorized({"X-Munea-Admin-Token": standing_token})
check("定時任務的萬能通行碼仍然有效（不能因為加固壞掉）", ok is True and code is None)

session_token = server.issue_admin_session_token(now=now)
ok, code = server.admin_authorized({"X-Munea-Admin-Token": session_token})
check("後台登入發的短期憑證可以通過 admin_authorized", ok is True and code is None)

ok, code = server.admin_authorized({"X-Munea-Admin-Token": "totally-made-up"})
check("亂打的通行碼被拒絕", ok is False and code == "invalid_admin_token")

ok, code = server.admin_authorized({})
check("沒帶通行碼被拒絕", ok is False and code == "invalid_admin_token")


# ────────────────────────────────────────────────────────────────
# 5. admin_login_response：帳密核對通過後發的是短期憑證，不是萬能通行碼本身
# ────────────────────────────────────────────────────────────────

fresh_ip = "203.0.113.80"  # 專用來源，不被上面的防猜測試誤擋
resp = server.admin_login_response(
    {"email": "boss@example.com", "password": "correct-horse-battery-staple"},
    client_ip=fresh_ip,
)
check("帳密對了登入成功", resp.get("ok") is True)
issued_token = resp.get("token") or ""
check("發出去的不是萬能通行碼本身（短期憑證跟它長得不一樣）", issued_token != standing_token)
check("發出去的憑證格式正確（三段式）", issued_token.count(".") == 2)
check("回傳有效期秒數", resp.get("expiresIn") == server.ADMIN_SESSION_TOKEN_TTL_SECONDS)
ok, _ = server.admin_authorized({"X-Munea-Admin-Token": issued_token})
check("登入發出去的憑證可以直接拿去打後台 API", ok is True)

wrong_resp = server.admin_login_response(
    {"email": "boss@example.com", "password": "wrong-password"},
    client_ip="203.0.113.81",
)
check("密碼錯登入失敗", wrong_resp.get("ok") is False and wrong_resp.get("error") == "invalid_credentials")


print()
if FAILS:
    print(f"❌ {len(FAILS)} 項未過：" + "、".join(FAILS))
    sys.exit(1)
print("✅ 後台登入加固護欄全過")
