#!/usr/bin/env python3
import os
import sys
import unittest

os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("MUNEA_DATABASE_PROVIDER", "json")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import chat_engine  # noqa: E402
import live_voice_server  # noqa: E402
import server  # noqa: E402


def context_with(state=None):
    return {
        "persona": {
            "templateId": "nening-real-female",
            "relationshipState": state or {},
        },
        "perception": {"domains": []},
        "guardian": {"risk": {"level": "none"}},
    }


class RelationshipDialogueTests(unittest.TestCase):
    def test_s2s_asr_uses_taiwan_mandarin_and_call_context_phrases(self):
        phrases = live_voice_server.asr_adaptation_phrases(
            "寧寧", "小月", "爸爸", ["園藝花草", "懷舊老歌"], "台北市",
        )
        self.assertIn("沐寧", phrases)
        self.assertIn("回診", phrases)
        self.assertIn("小月", phrases)
        self.assertIn("爸爸", phrases)
        self.assertIn("我叫爸爸", phrases)
        self.assertIn("我是爸爸", phrases)
        self.assertIn("園藝花草", phrases)
        self.assertIn("台北市", phrases)
        self.assertEqual(len(phrases), len(set(phrase.casefold() for phrase in phrases)))
        self.assertLessEqual(len(phrases), 28)

    def test_core_selects_one_dialogue_mode_and_avoids_ai_service_tone(self):
        self.assertIn("陪伴、探索、建議、行動或慶祝", chat_engine.CORE)
        self.assertIn("一次最多一個主要問題", chat_engine.CORE)
        self.assertIn("人格保持八成穩定、兩成隨使用者調整", chat_engine.CORE)
        self.assertIn("不能假裝自己是真人", chat_engine.CORE)

    def test_rapport_never_regresses_after_a_short_turn(self):
        previous = {
            "rapportLevel": "trusted",
            "userBoundaries": {"proactiveCareAllowed": False},
            "relationshipMemory": {
                "effectiveInteractionCount": 12,
                "meaningfulTurnCount": 40,
                "sharedDepthScore": 3,
                "storedMemoryCount": 10,
            },
        }
        result = server.relationship_state_from_turn(
            {"history": [{"role": "user", "text": "嗯"}]},
            context_with(previous),
            [],
        )
        self.assertEqual(result["rapportLevel"], "trusted")
        self.assertEqual(result["relationshipMemory"]["effectiveInteractionCount"], 12)
        self.assertFalse(result["userBoundaries"]["proactiveCareAllowed"])

    def test_rapport_uses_cumulative_effective_interactions(self):
        state = None
        for text in ("我今天去公園走了一圈", "女兒週末會回來吃飯", "最近晚上比較不好睡"):
            state = server.relationship_state_from_turn(
                {"history": [{"role": "user", "text": text}]},
                context_with(state),
                [],
            )
        self.assertEqual(state["rapportLevel"], "familiar")
        self.assertEqual(state["relationshipMemory"]["effectiveInteractionCount"], 3)
        self.assertEqual(state["relationshipMemory"]["meaningfulTurnCount"], 3)


if __name__ == "__main__":
    unittest.main()
