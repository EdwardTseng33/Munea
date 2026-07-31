#!/usr/bin/env python3
"""一鍵開／關語系——把散在四個地方的開關同時翻，避免現場漏改。

為什麼要這支：「開語系」不是改一個開關，而是四個地方要同時對上，
少改一個，主分支就會紅在一個沒人預期的地方（8/2 現場最不需要的事）：

  ① web/src/i18n/catalog-manifest.json  runtimeEnabled / binaryLocalizationEnabled
  ② ios/App/App/Info.plist              CFBundleLocalizations（決定 iPhone 設定裡
                                        有沒有「語言」那一列——沒有這個，
                                        四語實機走查根本做不了）
  ③ ios/App/App.xcodeproj/project.pbxproj  knownRegions + InfoPlist.strings 的成員
                                        （字檔存在不等於被打包進去）
  ④ scripts/test-i18n-catalogs.js       「非預設語系必須維持關閉」那兩條刻意的
                                        絆線——開語系時必須一起鬆開，
                                        否則 test:launch 會擋住自己

用法：
    python scripts/toggle-locale-release.py --status          看現在誰開誰關
    python scripts/toggle-locale-release.py --enable en ja es --dry-run
    python scripts/toggle-locale-release.py --enable en ja es
    python scripts/toggle-locale-release.py --disable en ja es   （退版用）

⚠ 這支只翻開關，不代表可以上架。上架仍要 scripts/i18n-release-readiness.js
  的所有關卡通過（母語審查、實機走查、商店對帳那些是人做的、翻不了）。
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "web", "src", "i18n", "catalog-manifest.json")
INFO_PLIST = os.path.join(ROOT, "ios", "App", "App", "Info.plist")
PBXPROJ = os.path.join(ROOT, "ios", "App", "App.xcodeproj", "project.pbxproj")
CATALOG_TEST = os.path.join(ROOT, "scripts", "test-i18n-catalogs.js")

# 這幾個代號是 App 包裡的寫法（跟語系代號不同）：繁中在 iOS 是 zh-Hant
NATIVE = {"zh-TW": "zh-Hant", "en": "en", "ja": "ja", "es": "es"}
# project.pbxproj 裡每個語言檔的識別碼（已存在、只是沒被收進群組）
FILE_REFS = {
    "zh-Hant": "A1AA0001B2BB0001C3CC0042",
    "en": "A1AA0001B2BB0001C3CC0043",
    "ja": "A1AA0001B2BB0001C3CC0044",
    "es": "A1AA0001B2BB0001C3CC0046",
}


def read(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def current_status():
    manifest = json.loads(read(MANIFEST))
    rows = []
    for entry in manifest["locales"]:
        rows.append((entry["locale"], entry.get("runtimeEnabled"),
                     entry.get("binaryLocalizationEnabled"), entry.get("status")))
    return manifest, rows


def binary_locales(manifest):
    out = []
    for entry in manifest["locales"]:
        if entry.get("binaryLocalizationEnabled"):
            out.append(entry.get("nativeLocale") or NATIVE[entry["locale"]])
    return sorted(set(out))


def apply_manifest(manifest, locales, enable):
    changed = []
    for entry in manifest["locales"]:
        if entry["locale"] in locales:
            if entry.get("runtimeEnabled") != enable:
                entry["runtimeEnabled"] = enable
                changed.append(f"{entry['locale']}.runtimeEnabled={enable}")
            if entry.get("binaryLocalizationEnabled") != enable:
                entry["binaryLocalizationEnabled"] = enable
                changed.append(f"{entry['locale']}.binaryLocalizationEnabled={enable}")
            # 開了就不再是「開發中」，但也還不是「可對外」——
            # 這支工具只負責把語系放進 App 包裡（讓人打包、實機測），
            # 那是 release-candidate。要升成 production 得等八道關卡全綠，
            # 那是人看過證據後手動改 catalog-manifest.json 的事，不該由一支指令代勞。
            # （2026-08-01：原本這裡直接寫 production，等於一個指令就把「還沒驗」
            #  講成「可對外」，守門那關才會卡成死循環。）
            want_status = "release-candidate" if enable else "development"
            if entry.get("status") != want_status and entry["locale"] != "zh-TW":
                entry["status"] = want_status
                changed.append(f"{entry['locale']}.status={want_status}")
    return changed


def apply_plist(natives):
    text = read(INFO_PLIST)
    block = "\n".join(f"\t\t<string>{code}</string>" for code in natives)
    new_text, count = re.subn(
        r"(<key>CFBundleLocalizations</key>\s*<array>)([\s\S]*?)(</array>)",
        lambda m: f"{m.group(1)}\n{block}\n\t{m.group(3)}",
        text,
        count=1,
    )
    if not count:
        raise SystemExit("Info.plist: 找不到 CFBundleLocalizations")
    return new_text, text != new_text


def apply_pbxproj(natives):
    text = read(PBXPROJ)
    original = text

    # knownRegions：Base 一定要留（storyboard 靠它）
    regions = "\n".join(f'\t\t\t\t"{code}",' for code in natives) + "\n\t\t\t\tBase,"
    text, count = re.subn(
        r"(knownRegions = \()([\s\S]*?)(\n\t\t\t\);)",
        lambda m: f"{m.group(1)}\n{regions}{m.group(3)}",
        text,
        count=1,
    )
    if not count:
        raise SystemExit("project.pbxproj: 找不到 knownRegions")

    # InfoPlist.strings 的成員名單——字檔存在不等於被打包進去，這裡才是決定性的
    children = "\n".join(
        f"\t\t\t\t{FILE_REFS[code]} /* {code} */," for code in natives if code in FILE_REFS
    )
    text, count = re.subn(
        r"(A1AA0001B2BB0001C3CC0040 /\* InfoPlist\.strings \*/ = \{\s*isa = PBXVariantGroup;\s*children = \()([\s\S]*?)(\n\t\t\t\);)",
        lambda m: f"{m.group(1)}\n{children}{m.group(3)}",
        text,
        count=1,
    )
    if not count:
        raise SystemExit("project.pbxproj: 找不到 InfoPlist.strings 群組")
    return text, text != original


def apply_catalog_test(enable):
    """鬆開／收回「非預設語系必須維持關閉」那三條刻意的絆線。

    這三條是防呆用的：沒過上架關卡前有人手滑把語系打開，這裡會擋住。
    真的要開的時候，它們必須一起鬆開，否則 test:launch 會擋住自己
    ——這正是 2026-07-31 巡檢抓到的「開關與它自己的守門互相矛盾」。
    """
    text = read(CATALOG_TEST)
    original = text

    guard_on = """for (const entry of developmentLocales) {
  assert.equal(entry.status, 'development', `${entry.locale} must stay development-only`);
  assert.equal(entry.runtimeEnabled, false, `${entry.locale} runtime was enabled before release gates`);
  assert.equal(
    entry.binaryLocalizationEnabled,
    false,
    `${entry.locale} binary localization was enabled before release gates`,
  );
}"""

    guard_off = """// 2026-08 語系開放後由 scripts/toggle-locale-release.py 鬆開這三條。
// 原意是防「沒過上架關卡就有人手滑打開語系」；語系正式開放之後，
// 把關的責任交給 scripts/i18n-release-readiness.js（那支是真的在看證據）。
// 要退版關回去：python scripts/toggle-locale-release.py --disable en ja es
// for (const entry of developmentLocales) {
//   assert.equal(entry.status, 'development', `${entry.locale} must stay development-only`);
//   assert.equal(entry.runtimeEnabled, false, `${entry.locale} runtime was enabled before release gates`);
//   assert.equal(
//     entry.binaryLocalizationEnabled,
//     false,
//     `${entry.locale} binary localization was enabled before release gates`,
//   );
// }"""

    if enable and guard_on in text:
        text = text.replace(guard_on, guard_off)
    elif not enable and guard_off in text:
        text = text.replace(guard_off, guard_on)
    return text, text != original


def main():
    parser = argparse.ArgumentParser(description="一鍵開／關語系（四個地方同時翻）")
    parser.add_argument("--status", action="store_true", help="只看現況")
    parser.add_argument("--enable", nargs="+", metavar="LOCALE")
    parser.add_argument("--disable", nargs="+", metavar="LOCALE")
    parser.add_argument("--dry-run", action="store_true", help="只印會改什麼、不寫檔")
    args = parser.parse_args()

    manifest, rows = current_status()
    if args.status or not (args.enable or args.disable):
        print("語系開關現況：")
        for locale, runtime, binary, status in rows:
            mark = "✅ 開" if runtime else "⛔ 關"
            print(f"  {locale:6} {mark}  App 包內建：{'有' if binary else '沒有'}  ({status})")
        print(f"\nApp 包目前收了：{', '.join(binary_locales(manifest)) or '（無）'}")
        print("\n開語系：python scripts/toggle-locale-release.py --enable en ja es")
        return 0

    enable = bool(args.enable)
    locales = args.enable or args.disable
    unknown = [x for x in locales if x not in NATIVE]
    if unknown:
        raise SystemExit(f"不認得的語系：{unknown}；可用：{sorted(NATIVE)}")

    changed = apply_manifest(manifest, set(locales), enable)
    natives = binary_locales(manifest)
    if not natives:
        raise SystemExit("至少要留一個語系在 App 包裡")

    plist_text, plist_changed = apply_plist(natives)
    pbx_text, pbx_changed = apply_pbxproj(natives)
    test_text, test_changed = apply_catalog_test(enable)

    print(("【試跑】" if args.dry_run else "【已改】") + ("開啟" if enable else "關閉") + f"：{', '.join(locales)}")
    for item in changed:
        print(f"  開關表：{item}")
    print(f"  App 包語系：{', '.join(natives)}" + ("（有改）" if plist_changed else "（沒變）"))
    print("  Xcode 專案：" + ("已同步" if pbx_changed else "沒變"))
    print("  防呆絆線：" + ("已" + ("鬆開" if enable else "收回") if test_changed else "沒變"))

    if args.dry_run:
        print("\n（試跑，什麼都沒寫）")
        return 0

    write(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    write(INFO_PLIST, plist_text)
    write(PBXPROJ, pbx_text)
    write(CATALOG_TEST, test_text)
    print("\n接著跑：npm run test:ui-contracts && node scripts/i18n-release-readiness.js")
    return 0


if __name__ == "__main__":
    sys.exit(main())
