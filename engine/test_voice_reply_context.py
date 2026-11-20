# -*- coding: utf-8 -*-
"""聊聊記得你上週說的事 · 語音路防線（2026-11-18 · 補助案 A4「記憶接續與情境感知」）

以前：Voice 在自己容器的便條紙裡撈長期記憶——正式環境撈到的是空的，每通電話她只接得上
12 小時內「上一通」的一句重點。現在：開場前向 Brain 整份要（記憶＋活的側寫＋身體＋簡報）。

守的線（跟身體狀況那個窗口同一套）：
  一、Brain 這個窗口只認得出人才給；認不出就回空——就算上一通的身分還黏在執行緒上也不撈。
  二、窗口有鎖：跟其他語音內部窗口同一道內部密語門。
  三、Voice 要不到（沒設通道／認不出人／Brain 不通／開關關掉）→ 回空、退回原本的路（不會整段不見）。
  四、要得到 → Brain 給的段落真的進她的說明書，而且是在組本機那份「之前」先要。

跑法：python engine/test_voice_reply_context.py（純本子模式、不需網路/鑰匙）
"""
import json
import os
import sys
import tempfile

os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import server  # noqa: E402

FAILS = []


def check(name, cond):
    print(("  OK  " if cond else " FAIL ") + name)
    if not cond:
        FAILS.append(name)


def seed_memory(text):
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump([{"id": "m1", "type": "family_event", "content": text, "importance": 0.9,
                "createdAt": "2026-11-10T08:00:00Z"}], f, ensure_ascii=False)
    f.close()
    server.MEMORY_ITEMS_PATH = f.name
    return f.name


def test_window_blind_without_identity():
    resp = server.voice_reply_context_response({"userId": "unknown-user"})
    check("窗口：認不出人 → ok", resp.get("ok") is True)
    check("窗口：認不出人 → 明說沒認出來", resp.get("identityResolved") is False)
    check("窗口：認不出人 → 一個字都不給", resp.get("instruction") == "" and resp.get("memoryCount") == 0)
    check("窗口：沒帶 userId → 一樣不給", server.voice_reply_context_response({}).get("instruction") == "")


def test_window_ignores_leaked_identity():
    path = seed_memory("孫子下個月要娶某，婚宴在台中")
    token = server.REQUEST_DATA_IDENTITY.set({"accountId": "acct-x", "personId": "person-leaked",
                                              "familyGroupId": "fam-x", "authUserId": "auth-x"})
    try:
        resp = server.voice_reply_context_response({"userId": "unknown-user"})
        check("窗口：認不出這通的人 → 不拿殘留身分的記憶", "娶某" not in str(resp))
        check("窗口：認不出這通的人 → 誠實說沒認出人", resp.get("identityResolved") is False)
    finally:
        server.REQUEST_DATA_IDENTITY.reset(token)
    os.unlink(path)


def test_window_gives_the_callers_own_context():
    path = seed_memory("孫子下個月要娶某，婚宴在台中")
    real_scope = server._voice_identity_scope
    server._voice_identity_scope = lambda uid: (
        server.REQUEST_DATA_IDENTITY.set({"accountId": "acct-me", "personId": "person-me",
                                          "familyGroupId": "fam-me", "authUserId": uid}), "person-me")
    try:
        resp = server.voice_reply_context_response({"userId": "auth-me", "char": "寧寧", "displayName": "寧寧"})
        check("窗口：認得出人 → 有回段落", resp.get("identityResolved") is True and bool(resp.get("instruction")))
        check("窗口：他自己的記憶進得了段落", "娶某" in resp.get("instruction", ""))
        check("窗口：記憶條數有回報", resp.get("memoryCount", 0) >= 1)
        check("窗口：用完把身分清掉（不黏在執行緒上）", server.REQUEST_DATA_IDENTITY.get() in (None, {}))
    finally:
        server._voice_identity_scope = real_scope
    os.unlink(path)


def test_window_is_locked():
    import inspect
    src = inspect.getsource(server)
    check("窗口掛在內部密語那道門後面", '"/voice/health-context", "/voice/reply-context",' in src and "voice_internal_secret_required" in src)
    check("窗口有接到處理函式", '"/voice/reply-context": voice_reply_context_response' in src)


def test_voice_helper_fails_safe():
    import live_voice_server as lv
    for name, scope in [("沒有 memory_scope", None), ("scope 格式不對", "person-me"), ("沒設 Brain 通道", "voice-abc")]:
        check("要不到就回空：" + name, lv._brain_reply_context(scope, "寧寧", {}) == "")
    os.environ["MUNEA_BRAIN_INTERNAL_URL"] = "http://brain.invalid"
    os.environ["MUNEA_VOICE_BRAIN_SECRET"] = "s"
    real_post = lv.post_internal
    try:
        lv.post_internal = lambda *a, **k: {"ok": True, "instruction": "（記憶：孫子要娶某）", "identityResolved": False}
        check("Brain 說認不出人 → 回空", lv._brain_reply_context("voice-abc", "寧寧", {}) == "")

        def boom(*a, **k):
            raise RuntimeError("down")
        lv.post_internal = boom
        check("Brain 不通 → 回空", lv._brain_reply_context("voice-abc", "寧寧", {}) == "")
        sent = {}

        def ok(url, secret, path, payload, **k):
            sent.update(path=path, payload=payload)
            return {"ok": True, "instruction": "（記憶：孫子要娶某）", "identityResolved": True}
        lv.post_internal = ok
        got = lv._brain_reply_context("voice-abc", "寧寧", {"displayName": "阿寧", "interests": ["園藝"]})
        check("認得出人 → 拿到 Brain 的段落", got == "（記憶：孫子要娶某）")
        check("只送已驗證的 user_id（去掉 voice- 前綴）", sent.get("payload", {}).get("userId") == "abc")
        check("走 /voice/reply-context", sent.get("path") == "/voice/reply-context")
        check("把稱呼與興趣一起帶過去", sent["payload"].get("displayName") == "阿寧" and sent["payload"].get("interests") == ["園藝"])
        os.environ["MUNEA_VOICE_BRAIN_REPLY_CONTEXT"] = "0"
        check("開關關掉 → 不去要", lv._brain_reply_context("voice-abc", "寧寧", {}) == "")
    finally:
        lv.post_internal = real_post
        for k in ("MUNEA_BRAIN_INTERNAL_URL", "MUNEA_VOICE_BRAIN_SECRET", "MUNEA_VOICE_BRAIN_REPLY_CONTEXT"):
            os.environ.pop(k, None)


def test_voice_asks_brain_before_building_locally():
    """結構檢查（看程式碼結構，不找字串）：先向 Brain 要整份，要不到才在本機組。"""
    import ast
    import inspect
    import textwrap
    import live_voice_server as lv
    tree = ast.parse(textwrap.dedent(inspect.getsource(lv.system_instruction)))
    first = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name in ("_brain_reply_context", "_brain_health_context", "build_reply_context"):
                first.setdefault(name, node.lineno)
    check("語音有向大腦要整份開場素材", "_brain_reply_context" in first)
    check("先要整份、再退回本機組", first.get("_brain_reply_context", 10**9) < first.get("build_reply_context", -1))
    check("退回的路仍先要身體狀況", first.get("_brain_health_context", 10**9) < first.get("build_reply_context", -1))


def test_voice_uses_brain_context_in_instructions():
    import live_voice_server as lv
    real = lv._brain_reply_context
    try:
        lv._brain_reply_context = lambda scope, char, data: "（【記憶標記】孫子下個月要娶某）"
        inst = lv.system_instruction(char="寧寧", name="寧寧", memory_scope="voice-abc")
        check("Brain 給的段落真的進她的說明書", "【記憶標記】" in inst)
        lv._brain_reply_context = lambda scope, char, data: ""
        inst2 = lv.system_instruction(char="寧寧", name="寧寧", memory_scope="voice-abc")
        check("要不到 → 退回本機那份（健康圍籬還在）", "【記憶標記】" not in inst2 and "你現在什麼都看不到" in inst2)
    finally:
        lv._brain_reply_context = real


def main():
    test_window_blind_without_identity()
    test_window_ignores_leaked_identity()
    test_window_gives_the_callers_own_context()
    test_window_is_locked()
    test_voice_helper_fails_safe()
    test_voice_asks_brain_before_building_locally()
    test_voice_uses_brain_context_in_instructions()
    print()
    if FAILS:
        print("❌ %d 項未過：%s" % (len(FAILS), "、".join(FAILS)))
        sys.exit(1)
    print("✅ 記憶接續語音路防線全過（Brain 認人才給、要不到就退回、給的段落真的進說明書）")


if __name__ == "__main__":
    main()
