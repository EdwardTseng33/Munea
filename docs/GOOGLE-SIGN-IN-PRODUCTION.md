# Google Sign-In production setup

Munea uses two Google OAuth clients in Google Cloud project `gen-lang-client-0229303523` (project number `491603544409`):

- Web/server client: used as the ID-token audience accepted by Supabase.
- iOS client: used only by the native Google Sign-In SDK for bundle ID `net.munea.app`.

## Google Auth Platform

Branding:

- App name: `Munea App`
- User support email: the production Munea support address
- App logo: production Munea app icon
- Home page: `https://munea.net/`
- Privacy policy: `https://munea.net/privacy`
- Terms: `https://munea.net/terms`
- Authorized domain: `munea.net`
- Audience: External / In production

Clients:

1. Keep the current Web client used by Supabase.
2. The iOS OAuth client `Munea App iOS` is registered for bundle ID `net.munea.app`.
3. Debug and Release use client ID `491603544409-kutae0qdkjijqvguqtnh0ndf3ssn78ah.apps.googleusercontent.com`.
4. The callback scheme is `com.googleusercontent.apps.491603544409-kutae0qdkjijqvguqtnh0ndf3ssn78ah`.

The client ID and reversed client ID are public application identifiers, not client secrets. Never add the Web client secret to the App or repository.

## Verification

On a signed physical iPhone build:

1. Tap **使用 Google 登入**.
2. Confirm Google shows the native account chooser and `Munea App`, not the Supabase project hostname.
3. Select an existing Google account without typing its password again when Google already has a valid device/browser session.
4. Confirm Settings shows the Google account name, email, and profile photo.
5. Sign out, then confirm a new Google sign-in can select a different account.

The App Store export script blocks packaging when the iOS client ID, server client ID, or callback URL scheme is missing.
