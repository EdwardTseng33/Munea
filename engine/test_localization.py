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

    def test_app_preferences_preserve_trusted_market_and_policy_fields(self):
        account = {
            "locale": "zh-TW",
            "preferred_languages": ["zh-TW"],
        }
        person = {
            "locale": "zh-TW",
            "timezone": "Asia/Taipei",
            "region_code": "JP",
            "attributes": {
                "localeContext": {
                    "units": "metric",
                    "currency": "JPY",
                    "safetyRegion": "JP",
                    "legalRegion": "JP",
                    "dataRegion": "jp-primary",
                },
            },
        }

        context = localization.locale_context_from_app_preferences(
            {
                "locale": "en-US",
                "conversationLocale": "es-MX",
                "preferredLanguages": ["en-US", "es-MX"],
                "timezone": "America/Los_Angeles",
            },
            account,
            person,
        )

        self.assertEqual(context["uiLocale"], "en")
        self.assertEqual(context["conversationLocale"], "es")
        self.assertEqual(context["preferredLanguages"], ["es", "en"])
        self.assertEqual(context["timeZone"], "America/Los_Angeles")
        self.assertEqual(context["countryCode"], "JP")
        self.assertEqual(context["currency"], "JPY")
        self.assertEqual(context["safetyRegion"], "JP")
        self.assertEqual(context["legalRegion"], "JP")
        self.assertEqual(context["dataRegion"], "jp-primary")

    def test_app_preferences_reject_policy_override_attempts(self):
        attempts = (
            {"countryCode": "US"},
            {"safety_region": "US"},
            {"localeContext": {"legalRegion": "US"}},
            {"locale_context": {"dataRegion": "us-primary"}},
            {"localeContext": {"currency": "USD"}},
            {"localeContext": {"units": "us"}},
        )
        for request in attempts:
            with self.subTest(request=request), self.assertRaisesRegex(
                ValueError,
                "cannot change server policy fields",
            ):
                localization.locale_context_from_app_preferences(request)

    def test_app_preferences_reject_unknown_nested_fields(self):
        with self.assertRaisesRegex(
            ValueError,
            "Unsupported App locale preference fields",
        ):
            localization.locale_context_from_app_preferences({
                "localeContext": {"version": 1, "uiLocale": "ja"},
            })

    def test_app_preferences_require_a_mapping_locale_context(self):
        with self.assertRaises(TypeError):
            localization.locale_context_from_app_preferences({
                "localeContext": ["en"],
            })

    def test_mixed_language_turn_does_not_mutate_saved_or_session_language(self):
        state = localization.new_conversation_locale_state({
            "uiLocale": "ja",
            "conversationLocale": "en",
            "countryCode": "US",
            "safetyRegion": "US",
        })

        decision = localization.resolve_conversation_turn_locale(
            state,
            detected_languages=["en-US", "zh-Hant-TW"],
        )

        self.assertEqual(decision["responseLocale"], "en")
        self.assertEqual(decision["detectedLocales"], ["en", "zh-TW"])
        self.assertTrue(decision["codeSwitchDetected"])
        self.assertFalse(decision["sessionChanged"])
        self.assertEqual(decision["state"]["baseLocale"], "en")
        self.assertEqual(decision["state"]["sessionLocale"], "en")
        self.assertNotIn("countryCode", decision["state"])
        self.assertNotIn("safetyRegion", decision["state"])

    def test_turn_can_reply_in_detected_language_without_saving_it(self):
        state = localization.new_conversation_locale_state({
            "conversationLocale": "en",
        })

        decision = localization.resolve_conversation_turn_locale(
            state,
            detected_languages=["ja-JP"],
        )

        self.assertEqual(decision["responseLocale"], "ja")
        self.assertEqual(decision["state"]["baseLocale"], "en")
        self.assertEqual(decision["state"]["sessionLocale"], "en")
        self.assertIsNone(decision["persistedLocale"])

    def test_explicit_temporary_voice_switch_changes_only_the_session(self):
        state = localization.new_conversation_locale_state({
            "conversationLocale": "zh-TW",
        })

        decision = localization.resolve_conversation_turn_locale(
            state,
            switch_locale="es-MX",
        )

        self.assertEqual(decision["responseLocale"], "es")
        self.assertEqual(decision["state"]["baseLocale"], "zh-TW")
        self.assertEqual(decision["state"]["sessionLocale"], "es")
        self.assertTrue(decision["sessionChanged"])
        self.assertFalse(decision["confirmationRequired"])

    def test_permanent_voice_switch_requires_then_records_confirmation(self):
        state = localization.new_conversation_locale_state({
            "conversationLocale": "en",
        })
        requested = localization.resolve_conversation_turn_locale(
            state,
            switch_locale="ja",
            permanent=True,
        )

        self.assertEqual(requested["responseLocale"], "ja")
        self.assertEqual(requested["state"]["baseLocale"], "en")
        self.assertEqual(requested["state"]["sessionLocale"], "ja")
        self.assertEqual(requested["state"]["pendingPermanentLocale"], "ja")
        self.assertTrue(requested["confirmationRequired"])
        self.assertIsNone(requested["persistedLocale"])

        confirmed = localization.resolve_conversation_turn_locale(
            requested["state"],
            confirmation=True,
        )
        self.assertEqual(confirmed["state"]["baseLocale"], "ja")
        self.assertEqual(confirmed["state"]["sessionLocale"], "ja")
        self.assertIsNone(confirmed["state"]["pendingPermanentLocale"])
        self.assertEqual(confirmed["persistedLocale"], "ja")

    def test_voice_switch_rejects_unsupported_or_unexpected_confirmation(self):
        state = localization.new_conversation_locale_state({
            "conversationLocale": "en",
        })
        with self.assertRaisesRegex(ValueError, "Unsupported conversation locale"):
            localization.resolve_conversation_turn_locale(
                state,
                switch_locale="fr-FR",
            )
        with self.assertRaisesRegex(ValueError, "No permanent"):
            localization.resolve_conversation_turn_locale(
                state,
                confirmation=True,
            )
        with self.assertRaisesRegex(ValueError, "requires switchLocale"):
            localization.resolve_conversation_turn_locale(
                state,
                permanent=True,
            )

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

    def test_voice_session_profile_keeps_ui_conversation_and_region_independent(self):
        profile = localization.voice_session_locale_profile({
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

        self.assertEqual(profile["localeContext"]["uiLocale"], "ja")
        self.assertEqual(profile["sessionLocale"], "en")
        self.assertEqual(profile["responseLocale"], "en")
        self.assertEqual(profile["captionLocale"], "en")
        self.assertEqual(profile["speechLanguageCode"], "en-US")
        self.assertTrue(profile["openingMessage"].startswith("Hi,"))
        self.assertNotIn("119", profile["regionalSafetyInstruction"])
        self.assertNotIn("1925", profile["regionalSafetyInstruction"])
        self.assertEqual(profile["localeContext"]["countryCode"], "JP")
        self.assertEqual(profile["localeContext"]["safetyRegion"], "JP")

    def test_voice_session_profile_covers_all_four_speech_locales(self):
        expected = {
            "zh-TW": "cmn-TW",
            "en": "en-US",
            "ja": "ja-JP",
            "es": "es-ES",
        }
        for locale, speech_code in expected.items():
            with self.subTest(locale=locale):
                profile = localization.voice_session_locale_profile({
                    "conversationLocale": locale,
                })
                self.assertEqual(profile["speechLanguageCode"], speech_code)
                self.assertTrue(profile["openingMessage"])
                self.assertTrue(profile["retryMessage"])
                self.assertTrue(profile["replyLanguageInstruction"])
                self.assertTrue(profile["regionalSafetyInstruction"])

    def test_voice_turn_profile_can_code_switch_without_mutating_policy(self):
        context = localization.build_locale_context({
            "uiLocale": "en",
            "conversationLocale": "en",
            "countryCode": "US",
            "timeZone": "America/Los_Angeles",
            "currency": "USD",
            "safetyRegion": "US",
            "legalRegion": "US",
            "dataRegion": "us-central",
        })
        state = localization.new_conversation_locale_state(context)

        turn = localization.voice_turn_locale_profile(
            context,
            state,
            detected_languages=["ja-JP", "en-US"],
        )

        self.assertTrue(turn["decision"]["codeSwitchDetected"])
        self.assertEqual(turn["decision"]["state"]["baseLocale"], "en")
        self.assertEqual(turn["decision"]["state"]["sessionLocale"], "en")
        self.assertEqual(turn["profile"]["responseLocale"], "ja")
        self.assertEqual(turn["profile"]["sessionLocale"], "en")
        self.assertEqual(turn["profile"]["speechLanguageCode"], "ja-JP")
        self.assertEqual(turn["profile"]["localeContext"]["countryCode"], "US")
        self.assertEqual(turn["profile"]["localeContext"]["safetyRegion"], "US")
        self.assertNotIn("119", turn["profile"]["regionalSafetyInstruction"])

    def test_explicit_voice_switch_updates_session_profile_but_not_account_policy(self):
        context = localization.build_locale_context({
            "uiLocale": "zh-TW",
            "conversationLocale": "zh-TW",
            "countryCode": "TW",
            "safetyRegion": "TW",
        })
        state = localization.new_conversation_locale_state(context)

        turn = localization.voice_turn_locale_profile(
            context,
            state,
            switch_locale="es-MX",
        )

        self.assertEqual(turn["profile"]["sessionLocale"], "es")
        self.assertEqual(turn["profile"]["responseLocale"], "es")
        self.assertEqual(turn["profile"]["speechLanguageCode"], "es-ES")
        self.assertIsNone(turn["decision"]["persistedLocale"])
        self.assertEqual(turn["profile"]["localeContext"]["conversationLocale"], "zh-TW")
        self.assertEqual(turn["profile"]["localeContext"]["countryCode"], "TW")
        self.assertIn("119", turn["profile"]["regionalSafetyInstruction"])
        self.assertIn("1925", turn["profile"]["regionalSafetyInstruction"])

    def test_regional_safety_numbers_follow_safety_region_not_language(self):
        english_in_taiwan = localization.regional_safety_instruction("en", "TW")
        chinese_in_mexico = localization.regional_safety_instruction("zh-TW", "MX")

        self.assertIn("119", english_in_taiwan)
        self.assertIn("1925", english_in_taiwan)
        self.assertIn("911", chinese_in_mexico)
        self.assertIn("墨西哥", chinese_in_mexico)
        self.assertNotIn("119", chinese_in_mexico)
        self.assertNotIn("1925", chinese_in_mexico)

    def test_spain_and_mexico_safety_policies_do_not_follow_spanish_language(self):
        spanish_in_spain = localization.regional_safety_instruction("es", "ES")
        spanish_in_mexico = localization.regional_safety_instruction("es", "MX")
        chinese_in_spain = localization.regional_safety_instruction("zh-TW", "ES")
        spanish_in_unknown_region = localization.regional_safety_instruction("es", "AR")

        self.assertIn("112", spanish_in_spain)
        self.assertNotIn("911", spanish_in_spain)
        self.assertIn("España", spanish_in_spain)
        self.assertIn("911", spanish_in_mexico)
        self.assertNotIn("112", spanish_in_mexico)
        self.assertIn("México", spanish_in_mexico)
        self.assertIn("112", chinese_in_spain)
        self.assertIn("西班牙", chinese_in_spain)
        self.assertNotRegex(spanish_in_unknown_region, r"\b(?:112|911|119|1925)\b")
        self.assertIn("servicio local de emergencias", spanish_in_unknown_region)

    def test_regional_safety_policy_sources_are_explicit_and_official(self):
        self.assertEqual(
            set(localization.REGIONAL_SAFETY_POLICY_SOURCES),
            {"ES", "MX"},
        )
        self.assertIn(
            "interior.gob.es",
            localization.REGIONAL_SAFETY_POLICY_SOURCES["ES"],
        )
        self.assertIn(
            "gob.mx",
            localization.REGIONAL_SAFETY_POLICY_SOURCES["MX"],
        )

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
        self.assertIn("不要說「濃醇」，改說「厚實」", instruction)
        # 2026-07-28：「興趣→喜好」這條拿掉了——Edward 真機聽到換上去的「喜好」也走音
        # （聽成「信號」），等於拿一個唸錯換另一個唸錯。兩個詞都改成句型層級的避用指示。
        self.assertNotIn("改說「喜好」", instruction)
        self.assertIn("「興趣」「喜好」這類書面詞一律不要說出口", instruction)
        self.assertIn("你平常喜歡做什麼", instruction)
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
        # 2026-07-28 新增的那半邊防線：「喜好」以前是替換表「換上去」的詞，從來不被攔——
        # Edward 真機聽到它走音成「信號」兩個禮拜都沒被抓到。現在講出口一樣攔下重講。
        self.assertTrue(localization.contains_unstable_mandarin_speech("你的喜好是什麼"))
        self.assertFalse(localization.contains_unstable_mandarin_speech("你平常喜歡做什麼"))
        self.assertEqual(
            localization.speech_text("這杯咖啡很濃醇", "zh-TW"),
            "這杯咖啡很厚實",
        )

    def test_replacement_targets_are_not_themselves_broken(self):
        """換上去的詞本身不可以是已知會唸歪的詞。

        這是 7/28 那個坑的回歸護欄：當時為了修「興趣」走音，把它換成「喜好」，
        結果「喜好」也走音（Edward 真機聽成「信號」）＝拿一個唸錯換另一個唸錯，
        而且沒有任何一支測試會叫。以後誰再加這種替換，這條就會擋下來。
        """
        for target in localization.unstable_replacement_targets():
            self.assertFalse(
                localization.contains_unstable_mandarin_speech(target),
                f"替換後的「{target}」本身就是已知會唸歪的詞，等於拿一個唸錯換另一個唸錯",
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

    def test_live_asr_hints_follow_conversation_locale(self):
        self.assertEqual(localization.asr_language_hints("zh-TW"), ["cmn-Hant-TW"])
        self.assertEqual(localization.asr_language_hints("en-US"), ["en-US"])
        self.assertEqual(localization.asr_language_hints("ja"), ["ja-JP"])
        self.assertEqual(localization.asr_language_hints("es-MX"), ["es-ES"])

    def test_code_switch_detection_is_language_only_not_region_policy(self):
        self.assertEqual(
            localization.detect_supported_languages("今天還不錯, and I want to tell you why"),
            ["en", "zh-TW"],
        )
        self.assertEqual(
            localization.detect_supported_languages("Hola, quiero hablar contigo"),
            ["es"],
        )
        self.assertEqual(
            localization.detect_supported_languages("今日はいい天気ですね"),
            ["ja"],
        )
        instruction = localization.live_voice_code_switch_instruction("en")
        self.assertIn("saved conversation language", instruction)
        self.assertIn("never changes country", instruction)


if __name__ == "__main__":
    unittest.main()
