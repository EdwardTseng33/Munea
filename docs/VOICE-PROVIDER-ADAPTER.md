# Munea Voice Provider Adapter

> Updated: 2026-06-29
> Status: baseline contract in place; real-time provider not connected yet.

## Why This Exists

Munea should not hard-code one model name or one vendor API into the app shell.

The first product experience is still `聊聊`: Taiwan Mandarin voice, subtitles, a living face, family context, and health-care boundaries. The voice layer must be replaceable because Gemini Live / Interactions, fallback STT -> chat -> TTS, and future providers have different transport, auth, interruption, and timing behavior.

## Current Frontend Contract

`window.MuneaVoiceProvider` is now exposed from `web/src/app.js`.

Current methods:

- `connect(context)`
- `open(char)`
- `sendText({ history, char })`
- `sendVoiceNote({ audio, mime, durationMs, char })`
- `close()`

Current modes:

- `static-fallback`
- `stt-chat-tts`
- `gemini-live`
- `interactions`

Today, the provider routes through the existing local demo endpoints:

- `/voice-session`
- `/open`
- `/chat`
- `/voice-note`

## Current Backend Contract

`POST /voice-session` returns capability metadata:

```json
{
  "ok": true,
  "provider": "stt-chat-tts",
  "fallback": "typed-chat",
  "locale": "zh-TW",
  "capabilities": {
    "textChat": true,
    "recordedVoiceNote": true,
    "serverTts": true,
    "realtimeAudio": false,
    "interrupt": false,
    "visemeTiming": false
  }
}
```

This endpoint is the future place to mint a short-lived real-time voice session or token. Standard API keys must not be exposed to the frontend.

## Product Rules

- Taiwan Mandarin first.
- English second.
- Taiwanese Hokkien remains research only for now.
- If real-time voice fails, keep the conversation alive through typed chat or recorded-note fallback.
- Avatar must degrade independently from voice: voice continuity matters more than face fidelity.
- Do not expose diagnosis, treatment, prescription, or therapy claims through voice copy.

## Next Implementation Step

1. Confirm real iPhone microphone and playback behavior inside Capacitor.
2. Add a `gemini-live` or `interactions` provider behind this same contract.
3. Return ephemeral session details from `/voice-session`.
4. Add transcript and audio-state events for Avatar Runtime.
5. Add interruption and viseme timing only after the basic voice loop is stable.

