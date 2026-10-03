# mobile/: the phone app (Expo, Android)

A thin native shell around the web app in `../web`, so the phone shows exactly what the laptop does:
- Scan & Pay;
- the six agents' investigation;
- voice;
- the EN / हिं / मरा toggle.

The backend still runs on the laptop. The phone reaches it through an HTTPS tunnel, because Android's browser engine allows the microphone only over HTTPS.

| File | What |
|---|---|
| `App.js` | Server-address screen (remembered), then the web app full screen in a `WebView` |
| `app.json` | App name, Android package, microphone permission (`expo-audio` plugin) |
| `tunnel.ps1` | Opens a cloudflared HTTPS tunnel to `localhost:8000` and prints the address for the phone |

What the shell does natively:
- asks for the microphone once at launch;
- lets the page use it (`getUserMedia`);
- plays spoken replies without an extra tap;
- maps Android's back button to the app's back. At the app's home screen, back opens the server screen.

## Demo on your Android phone

You need Expo Go from the Play Store, and the phone and laptop on the same Wi-Fi.

1. **Backend** (terminal 1):
   ```powershell
   cd backend
   .venv\Scripts\python scripts\reset_db.py      # clean demo data
   .venv\Scripts\python -m uvicorn app.main:app --port 8000
   ```
2. **HTTPS tunnel** (terminal 2, from the repo root). Keep it open, and note the green `https://….trycloudflare.com` address:
   ```powershell
   powershell -ExecutionPolicy Bypass -File mobile\tunnel.ps1
   ```
3. **The app** (terminal 3):
   ```powershell
   cd mobile
   npm install        # first time only
   npx expo start
   ```
   Scan the QR code it shows with Expo Go. If the phone is on a different network, use `npx expo start --tunnel` instead.
4. **On the phone:**
   1. Allow the microphone.
   2. Type the tunnel address into the app and tap **Connect**.
   3. Tap **Scan & Pay** on Home.

The quick-tunnel address changes every time `tunnel.ps1` starts. When it changes, press back on the app's home screen and enter the new one.

## Notes

- **Security:** while the tunnel is open, anyone with its address can use the demo, and the demo login has no password. The LLM and voice calls run on your keys. Close the tunnel (Ctrl+C) after the demo.
- **Audio links** are relative (`PUBLIC_BASE_URL` empty in `backend/.env`), so they work through any tunnel without changing config.
- **Live preview:** Android's WebView has no browser speech recognizer, so the live words preview doesn't appear while you speak. The real transcript (Sarvam) does.
- **Installable APK (optional, no Expo Go):** `npx eas build -p android --profile preview` needs a free Expo account (`npx eas login`) and an `eas.json`. Ask for it if you want one.
- **Expo version:** SDK 57. Add packages with `npx expo install <pkg>`, and check `npx expo-doctor` (21/21 passing).
