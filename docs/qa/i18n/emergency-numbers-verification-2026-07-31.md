# 各國急難號碼查證紀錄（2026-07-31）

> 為什麼要有這份：人設書分國之後，每一國的紅線裡都寫了當地的急難號碼。號碼寫錯不是文字問題，
> 是長輩在最需要幫忙的時候撥了一個沒人接的號碼。Edward 2026-07-31 拍板「沒有翻譯預算、
> 90 分信心就開」——查證號碼是免費的，所以這一項不接受「我覺得應該對」，只接受查過。

查證方式：對照各國官方或主管機關來源。查證人：蘇菲（Claude）。查證日：2026-07-31。

---

## 日本（safetyRegion = JP）

| 號碼 | 用途 | 查證結果 | 來源 |
|---|---|---|---|
| **119** | 消防・救急 | ✅ 正確 | 總務省消防廳 |
| **110** | 警察 | ✅ 正確 | 警察廳 |
| **#7119** | 「要不要叫救護車」諮詢（救急安心センター事業） | ✅ 正確，**但非全國涵蓋** | [消防廳 · 救急安心センター事業](https://www.fdma.go.jp/mission/enrichment/appropriate/appropriate003.html) |
| **0120-279-338** | よりそいホットライン（24 小時、免費、含自殺念頭／生活／家暴／外國人多語） | ✅ 正確 | [一般社團法人 社會的包摂サポートセンター](https://www.since2011.net/yorisoi/)、[厚生勞動省宣傳單](https://www.mhlw.go.jp/file/06-Seisakujouhou-12200000-Shakaiengokyokushougaihokenfukushibu/poster_2.pdf) |

⚠ **#7119 的重要限制**：由各都道府縣自行導入，**並非全國都有**（石川、靜岡、兵庫等縣已開通；靜岡自
令和 7 年 4 月起改為 24 小時）。人設書裡已寫明「地域により未対応」，這個註記**不可以拿掉**——
叫一位住在沒開通地區的長輩打 #7119，等於把他推到一通沒人接的電話。

## 美國（safetyRegion = US）

| 號碼 | 用途 | 查證結果 | 來源 |
|---|---|---|---|
| **911** | 醫療／消防／警察（共用） | ✅ 正確 | 全國通用 |
| **988** | Suicide & Crisis Lifeline，**可打電話也可傳簡訊**，24/7 | ✅ 正確 | [988lifeline.org](https://988lifeline.org/)、[SAMHSA](https://www.samhsa.gov/mental-health/988) |
| **1-800-677-1116** | Eldercare Locator（連到當地 Area Agency on Aging） | ✅ 正確，**但非 24 小時** | [Eldercare Locator](https://eldercare.acl.gov/) |

⚠ **Eldercare Locator 的重要限制**：**週一至週五 08:00–21:00（美東時間）**，不是 24 小時。
人設書裡已寫「weekdays」，這個註記**不可以拿掉**。緊急狀況一律走 911，不是這支。

## 西班牙（safetyRegion = ES）

| 號碼 | 用途 | 查證結果 | 來源 |
|---|---|---|---|
| **112** | 醫療／消防／警察（共用，全歐盟） | ✅ 正確 | 內政部 |
| **024** | 自殺行為關懷專線，24/7/365、免費、保密 | ✅ 正確 | [衛生部 · Línea 024](https://www.sanidad.gob.es/linea024/home.htm) |
| **016** | 性別暴力，24 小時、免費、**不留通聯紀錄**、53 種語言；另有 WhatsApp 600 000 016 | ✅ 正確 | [平等部 · Teléfono 016](https://violenciagenero.igualdad.gob.es/informacion-3/recursos/telefono016/) |

## 台灣（safetyRegion = TW · 原本就在用）

| 號碼 | 用途 |
|---|---|
| 119 | 消防／救護 |
| 1925 | 安心專線 |
| 1995 | 生命線 |
| 113 | 保護專線（受暴／受虐） |

---

## 守門

`scripts/test_persona_books.py::test_every_book_carries_its_local_emergency_numbers`
會逐本檢查各國紅線裡有沒有該國號碼，以及有沒有殘留別國號碼。號碼被刪或被改成別國的，主分支會紅。

## 什麼時候要重查

- 上架新國家時（新的 safetyRegion）。
- 每年一次例行複查（號碼會變：西班牙 024 是 2022 年才啟用的、美國 988 是 2022 年才取代舊的十位數專線）。
- 收到用戶回報「打過去沒人接」時，立刻重查並當事故處理。
