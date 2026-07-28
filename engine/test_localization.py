import unittest

import localization


class LocalizationTests(unittest.TestCase):
    def test_locale_context_defaults_preserve_current_taiwan_production_behavior(self):
        context = localization.build_locale_context()

        self.assertEqual(context, localization.DEFAULT_LOCALE_CONTEXT)
        self.assertIsNot(context["preferredLanguages"], localization.DEFAULT_LOCALE_CONTEXT["preferredLanguages"])

    def test_locale_context_keeps_language_and_region_policy_independent(self):
        context = localization.build_locale_context({
            "uiLocale": "ja-JP",
            "preferredLanguages": ["ja-JP", "en-US", "ja"],
        })

        self.assertEqual(context["uiLocale"], "ja")
        self.assertEqual(context["conversationLocale"], "ja")
        self.assertEqual(context["preferredLanguages"], ["ja", "en"])
        self.assertEqual(context["countryCode"], "TW")
        self.assertEqual(context["safetyRegion"], "TW")
        self.assertEqual(context["legalRegion"], "TW")
        self.assertEqual(context["dataRegion"], "tw-primary")

    def test_locale_context_accepts_explicit_market_and_data_policy(self):
        context = localization.build_locale_context({
            "uiLocale": "es-MX",
            "conversationLocale": "en-US",
            "preferredLanguages": ["es-MX", "en-US"],
            "countryCode": "mx",
            "timeZone": "America/Mexico_City",
            "units": "metric",
            "currency": "mxn",
            "safetyRegion": "mx",
            "legalRegion": "mx",
            "dataRegion": "us-central",
        })

        self.assertEqual(context, {
            "version": 1,
            "uiLocale": "es",
            "conversationLocale": "en",
            "preferredLanguages": ["en", "es"],
            "countryCode": "MX",
            "timeZone": "America/Mexico_City",
            "units": "metric",
            "currency": "MXN",
            "safetyRegion": "MX",
            "legalRegion": "MX",
            "dataRegion": "us-central",
        })

    def test_locale_context_falls_back_only_for_unsupported_app_languages(self):
        context = localization.build_locale_context({
            "uiLocale": "de-DE",
            "preferredLanguages": ["de-DE"],
        })

        self.assertEqual(context, localization.DEFAULT_LOCALE_CONTEXT)

    def test_locale_context_rejects_invalid_policy_values(self):
        invalid_values = (
            {"countryCode": "Taiwan"},
            {"timeZone": "../Taipei"},
            {"units": "imperial"},
            {"currency": "$"},
            {"safetyRegion": "global"},
            {"legalRegion": ""},
            {"dataRegion": "../../prod"},
        )
        for values in invalid_values:
            with self.subTest(values=values), self.assertRaises(ValueError):
                localization.build_locale_context(values)

    def test_locale_context_rejects_unknown_contract_versions(self):
        for version in (0, 2, "future", True):
            with self.subTest(version=version), self.assertRaises(ValueError):
                localization.build_locale_context({"version": version})

    def test_locale_context_rejects_non_mapping_input(self):
        with self.assertRaises(TypeError):
            localization.build_locale_context(["ja"])

    def test_locale_context_maps_existing_account_and_person_storage(self):
        context = localization.locale_context_from_account(
            {
                "locale": "en-US",
                "preferred_languages": ["en-US", "es-MX"],
            },
            {
                "locale": "es-MX",
                "timezone": "America/Mexico_City",
                "region_code": "MX",
                "attributes": {
                    "localeContext": {
                        "units": "metric",
                        "currency": "MXN",
                        "safetyRegion": "MX",
                        "legalRegion": "MX",
                        "dataRegion": "us-central",
                    },
                },
            },
        )

        self.assertEqual(context["uiLocale"], "en")
        self.assertEqual(context["conversationLocale"], "es")
        self.assertEqual(context["preferredLanguages"], ["es", "en"])
        self.assertEqual(context["countryCode"], "MX")
        self.assertEqual(context["safetyRegion"], "MX")
        self.assertEqual(context["legalRegion"], "MX")
        self.assertEqual(context["dataRegion"], "us-central")

    def test_locale_context_request_keeps_ui_and_conversation_language_separate(self):
        context = localization.locale_context_from_request({
            "locale": "ja-JP",
            "conversationLocale": "en-US",
            "preferredLanguages": ["ja-JP", "en-US"],
            "countryCode": "JP",
            "timeZone": "Asia/Tokyo",
            "currency": "JPY",
            "safetyRegion": "JP",
            "legalRegion": "JP",
            "dataRegion": "jp-primary",
        })

        self.assertEqual(context["uiLocale"], "ja")
        self.assertEqual(context["conversationLocale"], "en")
        self.assertEqual(context["preferredLanguages"], ["en", "ja"])
        self.assertEqual(context["countryCode"], "JP")
        self.assertEqual(context["timeZone"], "Asia/Tokyo")

    def test_locale_context_storage_reuses_columns_and_preserves_attributes(self):
        context = localization.build_locale_context({
            "uiLocale": "es",
            "conversationLocale": "en",
            "preferredLanguages": ["es", "en"],
            "countryCode": "MX",
            "timeZone": "America/Mexico_City",
            "currency": "MXN",
            "safetyRegion": "MX",
            "legalRegion": "MX",
            "dataRegion": "us-central",
        })
        fields = localization.locale_context_storage_fields(
            context,
            {"birthday": "1950-01-01"},
        )

        self.assertEqual(fields["account"], {
            "locale": "es",
            "preferred_languages": ["en", "es"],
        })
        self.assertEqual(fields["person"]["locale"], "en")
        self.assertEqual(fields["person"]["timezone"], "America/Mexico_City")
        self.assertEqual(fields["person"]["region_code"], "MX")
        self.assertEqual(fields["person"]["attributes"]["birthday"], "1950-01-01")
        self.assertEqual(
            fields["person"]["attributes"]["localeContext"]["safetyRegion"],
            "MX",
        )

    def test_call_claims_keep_every_locale_dimension_in_one_signed_object(self):
        claims = localization.locale_context_call_claims({
            "uiLocale": "ja",
            "conversationLocale": "en",
            "preferredLanguages": ["ja", "en"],
            "countryCode": "JP",
            "timeZone": "Asia/Tokyo",
            "currency": "JPY",
            "safetyRegion": "JP",
            "legalRegion": "JP",
            "dataRegion": "jp-primary",
        })

        self.assertEqual(list(claims), ["locale_context"])
        self.assertEqual(claims["locale_context"]["uiLocale"], "ja")
        self.assertEqual(claims["locale_context"]["conversationLocale"], "en")
        self.assertEqual(claims["locale_context"]["safetyRegion"], "JP")
        self.assertEqual(claims["locale_context"]["dataRegion"], "jp-primary")

    def test_verified_call_payload_ignores_untrusted_top_level_locale_aliases(self):
        context = localization.locale_context_from_verified_call_payload({
            "locale": "ja",
            "countryCode": "JP",
            "safetyRegion": "JP",
        })

        self.assertEqual(context, localization.DEFAULT_LOCALE_CONTEXT)

    def test_verified_call_payload_accepts_only_nested_locale_context(self):
        context = localization.locale_context_from_verified_call_payload({
            "call_id": "call-1",
            "locale_context": {
                "version": 1,
                "uiLocale": "es-MX",
                "conversationLocale": "en-US",
                "preferredLanguages": ["es-MX", "en-US"],
                "countryCode": "MX",
                "timeZone": "America/Mexico_City",
                "currency": "MXN",
                "safetyRegion": "MX",
                "legalRegion": "MX",
                "dataRegion": "us-central",
            },
        })

        self.assertEqual(context["uiLocale"], "es")
        self.assertEqual(context["conversationLocale"], "en")
        self.assertEqual(context["safetyRegion"], "MX")
        self.assertEqual(context["dataRegion"], "us-central")

    def test_verified_call_payload_can_fail_closed_after_rollout(self):
        with self.assertRaises(ValueError):
            localization.locale_context_from_verified_call_payload(
                {"call_id": "call-1"},
                allow_legacy=False,
            )
        with self.assertRaises(TypeError):
            localization.locale_context_from_verified_call_payload(
                {"locale_context": "ja"},
            )

    def test_normalizes_supported_and_browser_locales(self):
        self.assertEqual(localization.normalize_locale("zh-Hant"), "zh-TW")
        self.assertEqual(localization.normalize_locale("en-GB"), "en")
        self.assertEqual(localization.normalize_locale("ja-JP"), "ja")
        self.assertEqual(localization.normalize_locale("es-MX"), "es")
        self.assertEqual(localization.normalize_locale("de-DE"), "zh-TW")

    def test_speech_codes_are_provider_ready(self):
        self.assertEqual(localization.speech_language_code("zh-TW"), "cmn-TW")
        self.assertEqual(localization.speech_language_code("en"), "en-US")
        self.assertEqual(localization.speech_language_code("ja"), "ja-JP")
        self.assertEqual(localization.speech_language_code("es"), "es-ES")

    def test_asr_transcription_uses_taiwan_traditional_copy(self):
        self.assertEqual(
            localization.canonicalize_transcription("我 想 了 园 艺 。 明 天 下 午 要 回 诊 。"),
            "我想了園藝。明天下午要回診。",
        )
        self.assertEqual(localization.canonicalize_transcription("hello world", "en"), "hello world")

    def test_asr_name_aliases_require_active_call_context(self):
        self.assertEqual(
            localization.reconcile_context_transcription("我叫阿紅", ["阿宏"]),
            "我叫阿宏",
        )
        self.assertEqual(
            localization.reconcile_context_transcription("我叫阿紅", ["爸爸"]),
            "我叫阿紅",
        )

    def test_non_taiwanese_prompt_never_assumes_taiwan_hotlines(self):
        self.assertIn("Do not use Taiwan-specific hotline numbers", localization.reply_language_instruction("es"))
        self.assertNotIn("Do not use Taiwan-specific hotline numbers", localization.reply_language_instruction("zh-TW"))

    def test_opening_and_retry_messages_follow_locale(self):
        self.assertEqual(localization.opening_message("en").split()[0], "Hi,")
        self.assertIn("conexión", localization.retry_message("es"))
        self.assertNotIn("今天過得怎麼樣", localization.opening_message("zh-TW"))

    def test_disabled_hokkien_is_rewritten_to_mandarin_for_speech_and_display(self):
        self.assertEqual(localization.speech_text("你卡早捆喔", "zh-TW"), "你早點睡喔")
        self.assertEqual(localization.display_text("你咖紮綑喔", "zh-TW"), "你早點睡喔")
        self.assertEqual(localization.display_text("食飽未？拍謝喔", "zh-TW"), "吃飽了嗎？不好意思喔")

    def test_taiwanese_pronunciation_is_not_applied_to_other_locales(self):
        self.assertEqual(localization.speech_text("卡早捆", "en"), "卡早捆")
        self.assertEqual(localization.display_text("咖紮綑", "ja"), "咖紮綑")

    def test_live_pronunciation_instruction_is_explicit_and_conservative(self):
        instruction = localization.taiwanese_pronunciation_instruction("zh-TW")
        self.assertIn("卡早捆", instruction)
        self.assertIn("咖紮綑", instruction)
        self.assertIn("不要自行猜音", instruction)
        self.assertEqual(localization.taiwanese_pronunciation_instruction("en"), "")

    def test_taiwanese_hokkien_is_disabled_below_release_threshold(self):
        self.assertFalse(localization.taiwanese_hokkien_release_enabled())
        self.assertLess(
            localization.TAIWANESE_HOKKIEN_VALIDATED_SCORE,
            localization.TAIWANESE_HOKKIEN_MIN_RELEASE_SCORE,
        )

    def test_taiwan_mandarin_launch_instruction_fails_safe(self):
        instruction = localization.taiwan_mandarin_launch_instruction("zh-TW")
        self.assertIn("只能使用自然、清楚的台灣華語", instruction)
        self.assertIn("不要主動講台語", instruction)
        self.assertIn("人設、記憶、喜好、舊對話或範例", instruction)
        self.assertIn("可以用國語再說一次嗎", instruction)
        self.assertIn("絕對不要猜意思", instruction)
        self.assertIn("不要說「興趣」，改說「喜好」", instruction)
        self.assertIn("不要說「濃醇」，改說「厚實」", instruction)
        self.assertEqual(localization.taiwan_mandarin_launch_instruction("en"), "")

    def test_reply_instruction_includes_launch_language_gate(self):
        instruction = localization.reply_language_instruction("zh-TW")
        self.assertIn("繁體台灣中文", instruction)
        self.assertIn("首發語言限制", instruction)

    def test_explicit_hokkien_speaking_request_is_blocked(self):
        self.assertTrue(localization.requests_taiwanese_hokkien("請用完整台語自我介紹，並講三句台語"))
        self.assertTrue(localization.requests_taiwanese_hokkien("改用 Hokkien 回答"))
        self.assertFalse(localization.requests_taiwanese_hokkien("這句台語我沒有聽清楚"))

    def test_hokkien_utterance_heuristic_is_conservative(self):
        self.assertTrue(localization.looks_like_taiwanese_hokkien("拍謝，我閣咧學"))
        self.assertTrue(localization.looks_like_taiwanese_hokkien("阮欲甲你講話"))
        self.assertTrue(localization.looks_like_taiwanese_hokkien("我咧等你"))
        self.assertTrue(localization.looks_like_taiwanese_hokkien("呷飽未"))
        self.assertTrue(localization.looks_like_taiwanese_hokkien("伊欲去食飯"))
        self.assertFalse(localization.looks_like_taiwanese_hokkien("今天要記得早點休息"))
        self.assertFalse(localization.looks_like_taiwanese_hokkien("這本書很著名，值得和大家共同分享"))
        self.assertFalse(localization.looks_like_taiwanese_hokkien("這個安排真的令人滿足"))
        self.assertFalse(localization.looks_like_taiwanese_hokkien("勇敢說出自己的想法嘛"))
        self.assertFalse(localization.looks_like_taiwanese_hokkien(localization.TAIWANESE_HOKKIEN_FALLBACK))

    def test_assistant_output_gate_maps_known_terms_and_blocks_residual_hokkien(self):
        self.assertEqual(
            localization.assistant_output_text("食飽未？拍謝喔", "zh-TW"),
            "吃飽了嗎？不好意思喔",
        )
        blocked = localization.assistant_output_text("阮今仔日真歡喜", "zh-TW")
        self.assertEqual(blocked, localization.TAIWANESE_HOKKIEN_OUTPUT_FALLBACK)
        self.assertNotIn("阮", blocked)

    def test_unstable_mandarin_terms_use_speech_safe_paraphrases(self):
        self.assertTrue(localization.contains_unstable_mandarin_speech("聊聊你的興趣"))
        self.assertTrue(localization.contains_unstable_mandarin_speech("味道很濃醇"))
        self.assertEqual(
            localization.speech_text("聊聊你的興趣，這杯咖啡很濃醇", "zh-TW"),
            "聊聊你的喜好，這杯咖啡很厚實",
        )

    def test_opening_policy_rotates_and_bans_generic_mood_questions(self):
        openings = [
            localization.voice_opening_instruction(i, ["懷舊老歌", "園藝花草"], "台北市")
            for i in range(4)
        ]
        self.assertEqual(len(set(openings)), 4)
        for opening in openings:
            self.assertIn("禁止使用", opening)
            self.assertIn("有開心嗎", opening)
            self.assertIn("只能一句", opening)
        self.assertNotEqual(
            localization.voice_opening_instruction(8, ["懷舊老歌"], "台北市", 0),
            localization.voice_opening_instruction(8, ["懷舊老歌"], "台北市", 1),
        )


if __name__ == "__main__":
    unittest.main()
