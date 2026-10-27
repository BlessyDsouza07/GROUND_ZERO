# GroundZero — run guide (Windows)

## 1. Start the backend (this was why login said "Can't reach the server")
In the backend folder, double-click `START_BACKEND.bat` (or run `.\START_BACKEND.ps1` in PowerShell).
Needs Docker Desktop running. It starts Postgres+Redis, installs deps, creates `.env` with a secret,
runs migrations, loads Mangaluru places, and serves http://localhost:8000 (check /docs).

## 2. Start the frontend
```powershell
cd .\gz
flutter clean
flutter pub get
flutter run -d chrome --web-port=7357
```
The web app now calls the backend on the same host the page was opened from (port 8000),
so no `--dart-define` is needed locally. The login screen shows a "server online/offline" pill; tap it to re-check.

## What changed
- Backend: unhandled errors now return JSON with CORS headers (before, a 500 looked like "can't reach server");
  clear messages for DB down / missing tables / missing secret; AUTH_SECRET_KEY is read from `.env`
  (or auto-generated in development); one-click Windows starter.
- Frontend: Tiara-inspired redesign (coastal illustrated hero, capsule nav, framed cards, ticker, signal cards,
  golden-hour countdown, footer) in your light/dark palettes; login no longer logs you out when the server is just down;
  adds `google_fonts` (Unbounded, Space Grotesk, Space Mono).

## Update 2 — Guide, contributions, login, look
- **Login** now closes the sign-in page and lands on the signed-in home immediately (no reload).
- **Talk to Guide** is a real chat (`POST /guide/chat`). It answers from GroundZero's own place records and, with a Groq key, phrases replies in your selected language.
  Put `GROQ_API_KEY=your_key` in the backend `.env` (same folder as `main.py`) and **restart the backend**. A line under a reply tells you if it fell back to records-only (no key / key rejected / rate limit).
- **Contributions**: Suggest an update, Share a local tip, Report an issue and Add media now open real forms (search a place, fill, submit for review) and show under *Your impact*. The old "Explorer" text was your level label; it is now a progress card.
- **Look**: editorial serif headings (Fraunces) + DM Sans, soft shadows, thin borders, equal-height cards, same palettes.


## v3 changes
- Run `flutter pub get` (new packages: url_launcher, speech_to_text, flutter_tts).
- Add place: accepts `12.8834° N`, `74.8983° E`, "12.8834, 74.8983", DMS; tap-the-map and "Use my current location".
- "Take me there" opens Google Maps directions to the exact coordinates (explore, itinerary, live trip).
- Plan a trip: routing/weather lookups are time-capped on the backend; if the browser times out, the saved draft is opened automatically.
- Talk to Guide: type or tap the mic (Chrome/Edge); the guide speaks replies (speaker icon). Allow microphone access.
- Groq key: put `GROQ_API_KEY=gsk_...` in the backend `.env` (same folder as main.py), then **restart** uvicorn. Check `http://localhost:8000/guide/status` — it must say `"llm_configured": true`.


## v4 changes
- Explore uses your real location and the current Mangaluru time. Closed places are no longer recommended (typical hours are used where a place has none listed, and labelled "usually").
- "Where you are" card: at a bus stand late at night you see rooms that are open; if you are already at a stay it won't suggest a rest stop.
- Back and Home buttons on every inner screen.
- Guide: friendlier spoken voice (picks the most natural browser voice, speaks in short sentences), knows the time and what's open near you, much bigger Mangaluru knowledge.
- If the guide says the key was not found, tap **Connect AI guide** in the chat and paste your Groq key once. It is checked and saved to the backend `.env`.
- Allow location access in the browser when asked.


## v5 changes
Backend: run `pip install -r requirements.txt` again (adds pillow, imageio-ffmpeg, edge-tts), then restart.
Frontend: run `flutter pub get` (adds camera, audioplayers, share_plus).
- Guide: server-side Groq key (tourists never see it). It lists the models your key can use and picks one automatically. Check `http://localhost:8000/guide/status?probe=true`: it makes a real test call and shows the exact error if there is one.
- Guide works even without the AI (built-in Mangaluru knowledge, open-now places only).
- Natural voice: the backend uses Microsoft neural voices (edge-tts, needs internet on the backend machine). Falls back to the browser voice.
- Photos: Take a photo / choose from gallery, only on tap, with a confirm step. Used in Journal, Add a place and Add media.
- Journal: "Capture a moment", Timeline/Scrapbook, and "Play my story" which plays your photos as a story and can render a real shareable MP4 ("Make video").

## v6 – HIVE 2, privacy and safety

New screens: **Your Mangaluru, today** (home hub + sidebar "Your day"), **What HIVE remembers**, **Privacy & safety**, legal pages. Sign-up now needs the Terms/Privacy tick and the 18+ tick. A one-time "your choices" sheet appears after first sign-in; location, memory and camera stay off until switched on.
Run: `flutter pub get` then `flutter run -d chrome`. I could not compile Flutter in my sandbox; all new Dart passed a syntax check only, so expect to fix a small compile error or two on first run and send it to me.
