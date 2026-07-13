#!/usr/bin/env python3
"""Protect the launch personality contract for Ningning and Ahong."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHARACTERS_PATH = ROOT / "engine" / "characters.json"

SHARED_PERSONA_TERMS = (
    "磁性",
    "溫柔",
    "沉著",
    "可靠",
    "語速比一般聊天稍慢",
    "節奏穩",
    "句尾完整",
    "不搶話",
    "不急著填滿沉默",
)

SHARED_STYLE_TERMS = (
    "低暖",
    "磁性",
    "溫柔穩重",
    "語速比一般聊天稍慢",
    "節奏穩定",
    "咬字清楚",
    "句尾完整",
)


def main():
    characters = json.loads(CHARACTERS_PATH.read_text(encoding="utf-8"))
    launch_roles = {name: characters[name] for name in ("寧寧", "阿宏")}

    for name, role in launch_roles.items():
        assert role["type"] == "human", f"{name}: launch companion must be human"
        assert role.get("voice"), f"{name}: missing Gemini voice"
        for term in SHARED_PERSONA_TERMS:
            assert term in role["persona"], f"{name}: persona missing {term}"
        for term in SHARED_STYLE_TERMS:
            assert term in role["style"], f"{name}: TTS style missing {term}"

    assert launch_roles["寧寧"]["voice"] != launch_roles["阿宏"]["voice"], (
        "Launch companions must retain distinct female and male voice casts"
    )
    assert "細心" in launch_roles["寧寧"]["persona"]
    assert "不冷淡" in launch_roles["阿宏"]["persona"]

    chat_engine = (ROOT / "engine" / "chat_engine.py").read_text(encoding="utf-8")
    live_voice = (ROOT / "engine" / "live_voice_server.py").read_text(encoding="utf-8")
    assert 'c["persona"]' in chat_engine, "Text brain no longer loads character persona"
    assert '(c["style"] or "") + text' in chat_engine, "TTS no longer loads character style"
    assert 'c.get("persona", "")' in live_voice, "Realtime Voice no longer loads persona"

    print("PASS: 寧寧與阿宏共用磁性、溫柔、穩重人格契約，並保留角色差異。")


if __name__ == "__main__":
    main()
