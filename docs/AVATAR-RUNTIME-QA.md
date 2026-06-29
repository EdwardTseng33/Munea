# Munea Avatar Runtime QA

> Updated: 2026-06-29
> Scope: visual and interaction QA for the Avatar Runtime path.

## What To Test

Avatar Runtime currently has four modes:

- `static-css`
- `2d-viseme`
- `ditto`
- `liveavatar`

Only `static-css` and the first mock `2d-viseme` layer are implemented in the app today. `ditto` and `liveavatar` are reserved integration targets.

## Local Browser Check

1. Start Munea locally.
2. Open `http://localhost:8200`.
3. Enter `聊聊`.
4. Confirm the fullscreen face appears.
5. Confirm idle state has no cue overlay except the breathing face.
6. Trigger speech.
7. Confirm speaking state shows the wave cue.
8. Choose a 2D avatar in Settings.
9. Return to `聊聊`.
10. Confirm `2d-viseme` mode is active while speaking.

Development console checks:

```js
window.MuneaAvatarRuntime.mode
window.MuneaAvatarRuntime.state
window.MuneaAvatarRuntime.viseme
```

## Forced 2D Mode Check

For development only:

```text
http://localhost:8200/?avatar=2d
```

This forces `2d-viseme` so the mouth-state layer can be inspected without changing avatar selection.

## iPhone / WKWebView Check

Run this after the Capacitor iOS shell exists.

1. Open the app on a real iPhone.
2. Enter `聊聊`.
3. Watch idle breathing for at least 10 seconds.
4. Tap microphone.
5. Confirm listening cue appears immediately.
6. Speak or use fallback recording.
7. Confirm thinking cue appears after input.
8. Confirm speaking cue appears during response.
9. Choose a 2D avatar.
10. Confirm mouth-state motion is visible while speaking.
11. Confirm caption remains readable and does not overlap controls.
12. Confirm the mic and end buttons remain tappable.
13. Confirm no obvious heat, stutter, or battery spike after 3 minutes.

## Go / No-Go

Go:

- State transitions are visible and smooth.
- 2D mouth-state motion is stable on iPhone.
- Captions remain readable.
- Voice and face continue gracefully when network or engine calls fail.

No-go:

- Mouth layer visually lands in a strange place on the selected avatar.
- Speaking animation stutters or blocks button taps.
- The face depends on GPU or network availability for basic presence.
- The user waits on a blank or loading face.

## Next Improvement

Replace mock mouth-state cycling with audio-driven motion:

1. Estimate amplitude from playback or generated TTS timing.
2. Map amplitude to `rest`, `open`, `wide`, `round`, and `smile`.
3. Later replace with phoneme/viseme timing when the voice loop provides better metadata.
