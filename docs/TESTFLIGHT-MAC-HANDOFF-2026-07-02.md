# Munea TestFlight Mac Handoff - 2026-07-02

Purpose: give Edward a clean Mac-side checklist now that Xcode is installed and the Apple Developer Program is active.

This handoff is intentionally kept outside the memory / perception / interaction code lanes so it does not overlap Claude / 城堡's current memory-layer work.

## Current Status

| Area | Status | Note |
|---|---|---|
| Apple Developer Program | Ready from owner | Team signing can now be configured on Mac. |
| Xcode | Ready from owner | Use the Mac with Xcode installed for all iOS steps. |
| Capacitor config | Ready | `capacitor.config.json` already uses `appId = net.munea.app`. |
| iOS native project | Not generated in repo yet | Run `npm run cap:add:ios` on Mac. |
| iPhone microphone QA | Not verified yet | Must be tested on real iPhone, not only browser. |
| TestFlight upload | Not ready yet | Needs signing, privacy purpose strings, backend reachability, and archive validation. |

## Mac Setup Steps

Run these on the Mac from a fresh clone or synced repo:

```bash
cd /path/to/Munea
git pull --rebase
npm install
npm run mac:doctor
npm run smoke:no-api
npm run cap:doctor
npm run cap:add:ios
npm run cap:sync
npm run cap:open:ios
```

`npm run mac:doctor` checks the Mac prerequisites before the first iOS build: Git, Node/npm, PowerShell for repo smoke scripts, Xcode, xcrun, repo status, and Capacitor config.

If PowerShell is missing on Mac, install it before running `npm run smoke:no-api`:

```bash
brew install --cask powershell
```

If `npm run cap:add:ios` says the iOS project already exists, skip it and run:

```bash
npm run cap:sync
npm run cap:open:ios
```

## Xcode Signing Checklist

In Xcode:

1. Open the `App` project generated under `ios/App`.
2. Select the `App` target.
3. Set the signing team to the active Apple Developer Program team.
4. Confirm the bundle identifier is `net.munea.app`.
5. Let Xcode manage signing for the first internal TestFlight build.
6. Select a real iPhone as the run target.
7. Build and run once before trying Archive.

## Required iOS Purpose Strings

Add these to `ios/App/App/Info.plist` before real-device QA:

```xml
<key>NSMicrophoneUsageDescription</key>
<string>Munea needs microphone access so you can talk with your AI health companion.</string>
<key>NSSpeechRecognitionUsageDescription</key>
<string>Munea may use speech recognition to help turn your voice into companion responses.</string>
<key>NSUserNotificationsUsageDescription</key>
<string>Munea uses notifications for reminders, family care updates, and gentle check-ins.</string>
```

HealthKit is not required for the first shell test. If HealthKit is enabled later, add a separate HealthKit purpose string and verify the entitlement in Xcode.

## Real iPhone Smoke QA

Pass these before calling the iOS shell usable:

1. App installs and opens on iPhone.
2. Landing / onboarding loads from bundled `web/` assets.
3. Onboarding AI / voice provider consent appears before entering the app.
4. Home, Settings, Family, and `聊聊` screens can be opened.
5. `聊聊` fullscreen avatar is visible and does not overlap core buttons.
6. Tapping microphone triggers the iOS permission prompt.
7. After permission, tap once to record and tap again to stop.
8. The app shows that the voice note was received or falls back gracefully.
9. Audio playback works after a user gesture.
10. Settings privacy policy link opens the in-app privacy page.
11. Account sign-in UI appears, but production auth can remain disabled for the first shell test.
12. No placeholder medical, subscription, or privacy copy is visible.

## App Store Connect Prep

Create the app record when the bundle id is available:

1. App name: `Munea` / `沐寧` depending on App Store locale strategy.
2. Bundle ID: `net.munea.app`.
3. SKU: `munea-ios`.
4. Primary category: Health & Fitness or Lifestyle, pending final positioning.
5. Support URL: must be live before App Review.
6. Privacy Policy URL: must be live before App Review.
7. Age rating: avoid medical-treatment claims; keep companion / reminder positioning.

## TestFlight Build Gate

Do not upload as a serious reviewer-facing build until these are true:

1. `npm run smoke:no-api` passes before `cap sync`.
2. iPhone shell opens without blank screen.
3. Microphone prompt and fallback behavior are verified.
4. Privacy link is reachable inside the app.
5. Backend URL strategy is decided for TestFlight:
   - bundled static shell only, for UI shell QA; or
   - reachable staging backend for voice / profile / entitlement contracts.
6. App Store Connect has a privacy policy URL and support URL ready or clearly scheduled.

## App Review Notes Draft

Use this as the first draft later:

```text
Munea is an AI health-care companion and family care app. It provides companionship, daily check-ins, routine reminders, family interaction, and safety referral prompts. It is not medical software and does not diagnose, treat, prescribe, provide dosage advice, replace emergency services, or provide psychotherapy.

The voice and AI features may process audio/text through third-party AI providers such as Google Gemini and OpenAI, with user consent shown during onboarding and in Settings.

Subscriptions, if enabled in this build, unlock premium companion capacity and avatar-related features. Safety, privacy controls, account deletion, and basic companion access are not gated by consumable credits.
```

## Mac Result To Report Back

After running the Mac test, report these back into the repo:

1. Xcode version.
2. iOS device model and iOS version.
3. Whether `npm run cap:add:ios` was newly run or iOS already existed.
4. Whether microphone prompt appeared.
5. Whether recording start / stop worked.
6. Whether playback worked.
7. Any Xcode signing or provisioning error text.
8. Screenshots if layout breaks on the iPhone.
