# -*- coding: utf-8 -*-
"""AI 看得見誰的身體 · 接線與外洩防線（2026-07-17 · 配 health_context.py）

這支測的是「水管有沒有真的接到她面前」，還有更重要的：**有沒有接錯人**。

守的兩條線：

一、側寫只能給本人（隱私 · 這是真外洩、不是假想）
    `living_profile.json` 原本是一個檔、全站共用、每一輪都塞進她腦裡，
    而檔案裡躺的是示範假資料（一位 72 歲、有高血壓和膝蓋痛的奶奶）。
    等於誰來聊天，她都把那個人的病史當成對方的講回去；第二個用戶一進來就是真外洩。
    改成蓋章制：沒蓋「這是誰的」、或蓋的是別人 → 一律不給。

二、認不出是誰就什麼都看不到（防捏造）
    她的說明書原本每一輪都寫著「你看得到健康告警」，實際上一個數字都到不了她面前。
    一個以為自己看得到數據的模型，會很樂意生一句「你今天血壓有點高喔」出來。
    所以：撈不到 → 圍籬必須出現在說明書裡，明講「你什麼都看不到、不准編」。

跑法：python engine/test_health_visibility.py（純本子模式、不需網路/鑰匙）
"""
import os
import sys
import tempfile

os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"   # 走引擎本子、測接線本身

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import server  # noqa: E402

FAILS = []

ME = "person-me"
SOMEONE_ELSE = "person-other"
FAM = "fam-health-test"


def check(name, cond):
    print(("  OK  " if cond else " FAIL ") + name)
    if not cond:
        FAILS.append(name)


def as_person(person_id, family_group_id=FAM):
    """假裝是這個人在講話（綁已驗證身分，跟正式路徑同一個機制）。"""
    return server.REQUEST_DATA_IDENTITY.set({
        "accountId": "acct-test", "personId": person_id,
        "familyGroupId": family_group_id, "authUserId": "auth-test",
    })


def _tmp(suffix=".json"):
    f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    f.close()
    return f.name


# ---- 一、側寫只能給本人 ----
def test_living_profile_never_leaks():
    path = _tmp()
    server.LIVING_PROFILE_PATH = path

    # 現場重現：一份沒蓋章的示範側寫（就是今天 repo 裡那份陳秀英）
    server.save_living_profile({
        "who": "陳秀英奶奶，72歲，前年老伴過世後一個人生活，有高血壓和膝蓋疼痛的老毛病。",
        "caresAbout": ["孫子小寶的婚事"],
    })

    check("沒蓋章的側寫 → 認不出是誰時不給任何人",
          server.load_living_profile() == {})

    token = as_person(ME)
    try:
        check("沒蓋章的側寫 → 就算認得出是誰也不給（來歷不明＝不端出去）",
              server.load_living_profile() == {})
    finally:
        server.REQUEST_DATA_IDENTITY.reset(token)

    # 蓋章給「別人」→ 我不該看到別人的病史
    server.save_living_profile({"who": "別人的側寫，有糖尿病。", "personId": SOMEONE_ELSE})
    token = as_person(ME)
    try:
        check("側寫蓋的是別人 → 我看不到（這條就是外洩防線本身）",
              server.load_living_profile() == {})
    finally:
        server.REQUEST_DATA_IDENTITY.reset(token)

    # 蓋章給本人 → 才給（對照組：證明不是永遠回空的假通過）
    server.save_living_profile({"who": "我自己的側寫。", "personId": ME})
    token = as_person(ME)
    try:
        prof = server.load_living_profile()
        check("側寫蓋的是本人 → 給（對照組：證明不是永遠回空）",
              prof.get("who") == "我自己的側寫。")
    finally:
        server.REQUEST_DATA_IDENTITY.reset(token)

    os.unlink(path)


def test_living_profile_gets_stamped_on_refresh():
    """新做出來的側寫一定要蓋章，不然它自己就變成下一份陳秀英。"""
    path = _tmp()
    server.LIVING_PROFILE_PATH = path
    token = as_person(ME)
    try:
        server.save_living_profile({"who": "測試用", "personId": ME})
        prof = server.load_living_profile()
        check("側寫存得下、也讀得回（本人）", prof.get("personId") == ME)
    finally:
        server.REQUEST_DATA_IDENTITY.reset(token)
    os.unlink(path)


# ---- 二、認不出是誰 = 什麼都看不到 ----
def test_blind_when_no_identity():
    ctx = server.load_health_context()
    check("認不出是誰 → 健康脈絡回空（不亂撈別人的）", ctx.get("hasData") is False)
    check("認不出是誰 → 沒有任何事實", ctx.get("facts") == [])


def test_fence_lands_in_her_instructions():
    """沒資料時，圍籬必須真的出現在她讀的說明書裡——不是只存在我腦裡。"""
    inst = server.reply_context_instruction(
        server.build_reply_context([{"role": "user", "text": "我睡不好"}]))
    check("說明書裡有健康那段", "他的身體狀況" in inst)
    check("沒資料 → 明講『你現在什麼都看不到』", "你現在什麼都看不到" in inst)
    check("沒資料 → 明令不准編數字", "不要講任何他的健康數字" in inst)


def test_fence_survives_broken_health_module():
    """健康那支壞掉時，也只能往『她不知道』倒——絕不能往『她以為自己看得到』倒。"""
    check("有寫死的備用圍籬", bool(server.HEALTH_FENCE_WHEN_BLIND))
    check("備用圍籬也明講看不到", "什麼都看不到" in server.HEALTH_FENCE_WHEN_BLIND)
    check("備用圍籬也禁止編數字", "不要講任何他的健康數字" in server.HEALTH_FENCE_WHEN_BLIND)


# ---- 三、有身分 + 有資料 = 事實真的到得了她面前 ----
def test_real_data_reaches_her():
    store = _tmp()
    server.FAMILY_STATE_STORE_PATH = store

    # 我的健康帳本（18 天平常 118/75，今天 158/92）
    log = {f"2026-06-{d:02d}": {"bpSys": 118, "bpDia": 75} for d in range(1, 19)}
    log["2026-07-17"] = {"bpSys": 158, "bpDia": 92}
    token = as_person(ME)
    try:
        server.family_state_response({
            "action": "save", "familyGroupId": FAM, "key": "vitals", "personId": ME,
            "value": {ME: {"name": "我", "day": "2026-07-17", "log": log}},
        })
        # 別人也在同一家推了資料——絕不能撈到他的
        server.family_state_response({
            "action": "save", "familyGroupId": FAM, "key": "vitals", "personId": SOMEONE_ELSE,
            "value": {SOMEONE_ELSE: {"name": "別人", "day": "2026-07-17",
                                     "log": {"2026-07-17": {"bpSys": 999, "bpDia": 555}}}},
        })

        ctx = server.load_health_context()
        facts = "\n".join(ctx.get("facts") or [])
        check("有身分＋有資料 → 她真的看得到（hasData）", ctx.get("hasData") is True)
        check("撈到的是我的數字（158/92）", "158/92" in facts)
        check("撈到我自己的平常（118/75）", "118/75" in facts)
        check("同一家的別人的數字絕不外洩（999/555 不得出現）", "999" not in facts)
        check("跟自己平常差很多 → 標起來", "bpSys" in (ctx.get("notable") or []))
    finally:
        server.REQUEST_DATA_IDENTITY.reset(token)
    os.unlink(store)


def test_other_person_sees_only_their_own():
    """換一個人來，只能看到自己的——這條跟上一條互為對照。"""
    store = _tmp()
    server.FAMILY_STATE_STORE_PATH = store
    token = as_person(ME)
    try:
        server.family_state_response({
            "action": "save", "familyGroupId": FAM, "key": "vitals", "personId": ME,
            "value": {ME: {"log": {"2026-07-17": {"bpSys": 158, "bpDia": 92}}}},
        })
        server.family_state_response({
            "action": "save", "familyGroupId": FAM, "key": "vitals", "personId": SOMEONE_ELSE,
            "value": {SOMEONE_ELSE: {"log": {"2026-07-17": {"bpSys": 121, "bpDia": 79}}}},
        })
    finally:
        server.REQUEST_DATA_IDENTITY.reset(token)

    token = as_person(SOMEONE_ELSE)
    try:
        facts = "\n".join(server.load_health_context().get("facts") or [])
        check("換人來：看得到自己的（121/79）", "121/79" in facts)
        check("換人來：看不到我的（158/92 不得出現）", "158/92" not in facts)
    finally:
        server.REQUEST_DATA_IDENTITY.reset(token)
    os.unlink(store)


def main():
    test_living_profile_never_leaks()
    test_living_profile_gets_stamped_on_refresh()
    test_blind_when_no_identity()
    test_fence_lands_in_her_instructions()
    test_fence_survives_broken_health_module()
    test_real_data_reaches_her()
    test_other_person_sees_only_their_own()

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 項未過：" + "、".join(FAILS))
        sys.exit(1)
    print("✅ 接線與外洩防線全過（只看得到自己的、認不出就什麼都看不到、圍籬進得了說明書）")


if __name__ == "__main__":
    main()
