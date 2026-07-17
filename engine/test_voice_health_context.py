# -*- coding: utf-8 -*-
"""聊聊也看得到你的身體 · 語音路防線（2026-07-17 · 接 health_context 到語音）

為什麼語音要繞一圈向 Brain 要，不自己撈：
  Voice 那台沒有雲端鑰匙、也認不出電話那頭是誰——所有來電者會落到同一個預設身分。
  健康資料最不能認錯人：**把 A 的血壓講給 B 聽，比不講嚴重得多**。
  所以一律 Brain 認人、Brain 撈，Voice 只拿結果（跟「上次聊天」「收線回寫」同一個模子）。

守的線：
  一、Brain 這個窗口只認得出人才給；認不出就回空。
  二、窗口有鎖：沒有內部密語進不來（跟另外兩個窗口同一道門）。
  三、Voice 拿不到（Brain 不通／認不出人／沒資料）→ **不塞任何東西** →
      她那段印成「你什麼都看不到、不准編」。失敗只能往「她不知道」倒。
  四、拿得到 → 事實真的進得了她的說明書，而且是**這位來電者自己的**數字。

跑法：python engine/test_voice_health_context.py（純本子模式、不需網路/鑰匙）
"""
import os
import sys
import tempfile

os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import server  # noqa: E402

FAILS = []

ME = "person-caller"
SOMEONE_ELSE = "person-other"
FAM = "fam-voice-test"


def check(name, cond):
    print(("  OK  " if cond else " FAIL ") + name)
    if not cond:
        FAILS.append(name)


def as_person(person_id, family_group_id=FAM):
    return server.REQUEST_DATA_IDENTITY.set({
        "accountId": "acct-test", "personId": person_id,
        "familyGroupId": family_group_id, "authUserId": "auth-test",
    })


def seed_two_people():
    """我跟另一個人都在同一家、都有健康帳本。"""
    store = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    store.close()
    server.FAMILY_STATE_STORE_PATH = store.name
    my_log = {f"2026-06-{d:02d}": {"bpSys": 118, "bpDia": 75} for d in range(1, 19)}
    my_log["2026-07-17"] = {"bpSys": 158, "bpDia": 92}
    token = as_person(ME)
    try:
        server.family_state_response({
            "action": "save", "familyGroupId": FAM, "key": "vitals", "personId": ME,
            "value": {ME: {"log": my_log}},
        })
        server.family_state_response({
            "action": "save", "familyGroupId": FAM, "key": "vitals", "personId": SOMEONE_ELSE,
            "value": {SOMEONE_ELSE: {"log": {"2026-07-17": {"bpSys": 999, "bpDia": 555}}}},
        })
    finally:
        server.REQUEST_DATA_IDENTITY.reset(token)
    return store.name


# ---- 一、Brain 的窗口 ----
def test_brain_window_blind_without_identity():
    """認不出人 → 回空。本子模式沒有帳號可解析，正是這個情境。"""
    resp = server.voice_health_context_response({"userId": "unknown-user"})
    check("窗口：認不出人 → ok 但沒資料", resp.get("ok") is True)
    check("窗口：認不出人 → 明說沒認出來", resp.get("identityResolved") is False)
    ctx = resp.get("healthContext") or {}
    check("窗口：認不出人 → 一個事實都不給", ctx.get("facts") == [] and ctx.get("hasData") is False)

    check("窗口：沒帶 userId → 一樣不給",
          (server.voice_health_context_response({}).get("healthContext") or {}).get("facts") == [])


def test_window_ignores_leaked_identity():
    """窗口認不出這通是誰時，**就算上一通的身分還黏在執行緒上，也絕不拿它的資料**。

    這條守的是「把 A 的血壓講給 B 聽」最可能真的發生的那條路：身分沒被清乾淨。
    每個窗口都有 finally 在清，但清漏一次的代價太大——所以窗口自己也要擋：
    認不出這通的人 → 根本不去撈，而不是「撈撈看撈到誰算誰」。
    """
    store = seed_two_people()
    token = as_person(ME)                 # 假裝上一通的身分殘留著沒清掉
    try:
        resp = server.voice_health_context_response({"userId": "unknown-user"})
        ctx = resp.get("healthContext") or {}
        check("窗口：認不出這通的人 → 不拿殘留身分的資料", ctx.get("facts") == [])
        check("窗口：認不出這通的人 → 不會誤報成有資料", ctx.get("hasData") is False)
        check("窗口：殘留身分的數字絕不外洩（158/92）", "158/92" not in str(ctx))
        check("窗口：誠實說沒認出人", resp.get("identityResolved") is False)
    finally:
        server.REQUEST_DATA_IDENTITY.reset(token)
    os.unlink(store)


def test_brain_window_is_locked():
    """窗口跟另外兩個走同一道鎖（沒密語進不來）——鎖在 HTTP 那層，這裡驗它有被列進去。"""
    import inspect
    src = inspect.getsource(server)
    check("窗口有掛在內部密語那道門後面",
          '"/voice/health-context"' in src and "voice_internal_secret_required" in src)
    check("窗口有接到處理函式", "voice_health_context_response" in src)


# ---- 二、Voice 拿不到就走圍籬（失敗方向只能往「她不知道」倒）----
def test_voice_falls_back_to_fence():
    inst = server.reply_context_instruction(
        server.build_reply_context([], "寧寧", {"displayName": "寧寧"}))
    check("語音沒拿到健康資料 → 說明書印圍籬", "你現在什麼都看不到" in inst)
    check("語音沒拿到健康資料 → 明令不准編數字", "不要講任何他的健康數字" in inst)


def test_voice_brain_helper_fails_safe():
    """Brain 不通 / 沒設通道 / 認不出人 → 一律回 None（不塞東西）。"""
    import live_voice_server as lv
    for name, scope in [
        ("沒有 memory_scope（認不出這通是誰）", None),
        ("scope 格式不對", "person-me"),
        ("沒設 Brain 通道", "voice-abc"),
    ]:
        check(f"要不到就不塞：{name}", lv._brain_health_context(scope) is None)


# ---- 三、餵得進來 = 事實真的到得了她面前，而且是本人的 ----
def test_fed_context_reaches_her_instructions():
    store = seed_two_people()
    token = as_person(ME)
    try:
        fed = server.load_health_context()          # Brain 端撈好的（模擬窗口回來的東西）
    finally:
        server.REQUEST_DATA_IDENTITY.reset(token)

    # Voice 那台：沒有身分（撈不到自己的），只能靠餵
    inst = server.reply_context_instruction(
        server.build_reply_context([], "寧寧", {"displayName": "寧寧", "healthContext": fed}))
    check("餵進來的事實真的進得了說明書（158/92）", "158/92" in inst)
    check("餵進來後不再印圍籬", "你現在什麼都看不到" not in inst)
    check("同家庭別人的數字不會混進來（999/555）", "999" not in inst)
    check("檔位 2 規矩跟著進去（不主動報數字）", "不要一開口就報數字" in inst)
    os.unlink(store)


def test_fed_context_cannot_be_faked_empty():
    """餵一個空的進來（Brain 認不出人）→ 照樣走圍籬，不會被當成『有資料』。"""
    inst = server.reply_context_instruction(
        server.build_reply_context([], "寧寧", {
            "displayName": "寧寧",
            "healthContext": {"facts": [], "notable": [], "hasData": False},
        }))
    check("餵空的進來 → 還是印圍籬（不會假裝有資料）", "你現在什麼都看不到" in inst)


def test_voice_asks_before_building():
    """順序鐵律：一定要先向 Brain 要、再組說明書。
    反過來的話她那段會先印成『你什麼都看不到』，後面才拿到也來不及了。

    看的是程式碼真正的結構、不是找字串——找字串會被註解騙（第一版就被自己的註解騙過）。
    """
    import ast
    import inspect
    import textwrap
    import live_voice_server as lv

    tree = ast.parse(textwrap.dedent(inspect.getsource(lv.system_instruction)))
    first_line = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = getattr(fn, "id", None) or getattr(fn, "attr", None)
        if name in ("_brain_health_context", "build_reply_context"):
            first_line.setdefault(name, node.lineno)

    check("語音有去向大腦要健康資料", "_brain_health_context" in first_line)
    check("要健康資料排在組說明書之前",
          first_line.get("_brain_health_context", 10**9) < first_line.get("build_reply_context", -1))


def main():
    test_brain_window_blind_without_identity()
    test_window_ignores_leaked_identity()
    test_brain_window_is_locked()
    test_voice_falls_back_to_fence()
    test_voice_brain_helper_fails_safe()
    test_fed_context_reaches_her_instructions()
    test_fed_context_cannot_be_faked_empty()
    test_voice_asks_before_building()

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 項未過：" + "、".join(FAILS))
        sys.exit(1)
    print("✅ 語音路防線全過（Brain 認人才給、要不到就說看不到、餵進來是本人的數字）")


if __name__ == "__main__":
    main()
