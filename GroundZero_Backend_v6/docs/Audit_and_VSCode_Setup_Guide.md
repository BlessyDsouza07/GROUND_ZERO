# Ground Zero — Plain-Language Audit & VS Code Setup Guide

This file has two parts:

1. **What was checked and fixed** — explained without jargon, so you can
   understand it without a coding background.
2. **Step-by-step instructions** to get the project running on your own
   computer in VS Code, written for someone doing this for the first
   time.

---

# PART 1 — The Audit, In Plain Words

## What Ground Zero's backend actually is, right now

Think of it as three connected machines:

- **Machine 1 (Layer 0)** — goes out and collects information about
  places in Mangaluru (restaurants, temples, beaches, museums, etc.) from
  real public sources like OpenStreetMap and Wikipedia, cleans that
  information up, removes duplicates, and stores it in a database.
- **Machine 2 (Layer 1)** — asks a tourist a short series of questions
  ("Soul Survey") to understand what kind of trip they want.
- **Machine 3 (Layer 2)** — takes what Machine 2 learned and picks the
  best matching places from Machine 1's database to build an itinerary.

All three machines exist as real, working code. None of them fake their
output — if a piece of information isn't genuinely available, the code is
built to say "unknown" rather than make something up. That "don't
fabricate" discipline shows up consistently throughout the codebase and
is one of its real strengths.

## What I actually verified, and how

I didn't just read the code and assume it works — I installed a real
database and a real cache system, and ran the project's full automated
test suite against them.

- **Result: 187 out of 187 tests passed.**
- These tests check things like: "does the system correctly recognize
  two listings as the same place with a slightly misspelled name?", "does
  a search request that's missing permission get correctly rejected?",
  "does the system correctly split a large map area into smaller chunks
  so a data-collection request doesn't time out?" — real behavior checks,
  not just "does the code run without crashing."

## What was broken, and what I fixed

**Problem found:** 6 of the automated tests were failing every time they
were run.

**In plain terms:** the project specifies it wants to reuse one
database connection across a batch of tests (for speed), but a mismatch
between two version numbers in the project's setup meant that
instruction was being silently ignored. Each test was instead getting
its own disposable connection, and when a later test tried to reuse a
connection that had already been thrown away, it crashed with an
"Event loop is closed" error.

**Fix:** updated one version number in the project's dependency list.
Nothing about the actual application logic changed. All 6 tests pass now.

**Problem found:** when the system saves a large batch of newly
collected places to the database, it was doing so as one single giant
save operation. If anything went wrong partway through — say, place
#8,000 out of 10,000 had a problem — the *entire* batch, including the
7,999 good places before it, would be thrown away and nothing would be
saved.

**Fix:** changed this to save in smaller, configurable chunks (500 places
at a time by default), each saved and confirmed independently. Now, if
something goes wrong on chunk 16, chunks 1 through 15 are already safely
stored — nothing already-good gets thrown away. This also makes each
individual save operation lighter, which matters as the database grows
into the thousands of places the project is meant to eventually hold.

**Added:** the system now reports exactly how many duplicate listings it
found and merged during each data-collection run, instead of leaving that
number to be worked out by hand.

**Added:** two documentation files —
- `docs/DataSources.md` explains, in detail, every outside source the
  system pulls data from (OpenStreetMap, Wikipedia, Wikidata, weather
  data, tide data), what each is used for, and what the legal rules
  ("licences") for using that data require — importantly, which sites are
  *not* allowed to be used as data sources (Google Maps, TripAdvisor,
  Booking.com), because their rules forbid this kind of automated
  collection.
- `docs/Attribution.md` gives the exact credit text that should appear
  somewhere in the finished app to satisfy those legal requirements — most
  open data sources require you to say where the data came from.

## What is genuinely still not done, and why

Be aware of this rather than assuming everything is finished:

- **The system has never actually gone out onto the internet and pulled
  in real data for Mangaluru.** Everything above was tested using a
  practice/test setup, not a live run against the real outside websites.
  The environment I was working in is deliberately locked down and
  cannot reach OpenStreetMap, Wikipedia, Wikidata, the weather service,
  or the tide service — so this step has to happen on your own computer,
  which does have normal internet access. Part 2 below tells you exactly
  how to do that.
- Two areas of the project — the admin monitoring screens, and the
  "why was this place recommended to you" explanation feature — have not
  been reviewed in this pass. They may be complete or may need work; I
  simply haven't checked them yet.
- An older audit document already exists in the project
  (`audit/AUDIT_REPORT.md`) from an earlier point in development. Some of
  the gaps it lists (like opening hours never being read, or every
  collected place getting an identical "trust score") have since been
  fixed by later work — that file is now partly out of date. Treat this
  document as the current, accurate one.

---

# PART 2 — Step-by-Step: Running Ground Zero in VS Code

Written assuming you're starting from a completely fresh computer with
nothing installed yet. Follow these in order. Every step tells you
exactly what to type and where.

## Step 0 — What you'll install (one-time setup)

1. **VS Code** — you likely already have this.
2. **Python 3.11 or newer**
3. **Docker Desktop** — this is the easiest way to get a real database
   and cache running without installing them by hand.
4. **Git** (only needed if you're pulling the code from GitHub rather
   than using the zip file directly).

### Installing Python

- Go to https://www.python.org/downloads/ and download the latest
  Python 3.x installer for your operating system.
- **Windows:** during installation, tick the box that says **"Add
  python.exe to PATH"** before clicking Install — this step is easy to
  miss and causes most setup problems if skipped.
- **Mac:** the installer from python.org is fine; alternatively `brew
  install python` if you use Homebrew.
- To check it worked, open a terminal and type:
  ```
  python --version
  ```
  You should see something like `Python 3.12.x`. (On Mac/Linux you may
  need to type `python3 --version` instead.)

### Installing Docker Desktop

- Go to https://www.docker.com/products/docker-desktop/ and download
  Docker Desktop for your operating system.
- Install it, then open it once so it fully starts up (you'll see a
  whale icon in your system tray/menu bar when it's ready).
- This gives you Postgres (the database) and Redis (the cache) without
  installing either one manually — the project already has a
  ready-to-use `docker-compose.yml` file for exactly this.

## Step 1 — Open the project in VS Code

1. Unzip the project folder somewhere you'll remember, e.g. your
   Desktop or Documents folder.
2. Open VS Code.
3. Go to **File → Open Folder…** and select the `groundzero` folder
   (the one containing `main.py`, `requirements.txt`, etc.).
4. If VS Code asks to install the recommended Python extension, say yes.

## Step 2 — Open a terminal inside VS Code

- Go to **Terminal → New Terminal** in the top menu. A command-line
  panel opens at the bottom of the window. Every command below is typed
  into this panel, one at a time, pressing Enter after each.

## Step 3 — Create a clean Python environment

This keeps this project's installed packages separate from anything else
on your computer.

```
python -m venv .venv
```

Then activate it:

- **Windows (PowerShell):**
  ```
  .venv\Scripts\Activate.ps1
  ```
- **Mac/Linux:**
  ```
  source .venv/bin/activate
  ```

You'll know it worked because your terminal line now starts with
`(.venv)`. **Every command from here on should be run with this active**
— if you close and reopen the terminal, just run the activate command
again.

## Step 4 — Install the project's dependencies

```
pip install -r requirements.txt
```

This downloads and installs everything the project needs (the web
framework, database driver, etc.). It can take a minute or two.

## Step 5 — Start the database and cache

With Docker Desktop open and running, type:

```
docker compose up -d
```

This reads the project's `docker-compose.yml` file and starts a real
Postgres database and a real Redis cache in the background, with no
manual database installation needed. To check they started correctly:

```
docker compose ps
```

You should see both `postgres` and `redis` listed as running/healthy.

## Step 6 — Create your settings file

The project needs a small settings file telling it how to connect to the
database and which API keys to use for outside data sources.

1. In VS Code's file explorer (left sidebar), find the file named
   `.env.example`.
2. Right-click it → **Copy**, then right-click the `groundzero` folder →
   **Paste**, and rename the copy to exactly `.env` (no `.example`).
3. Open the new `.env` file and fill in:
   - `OPENWEATHERMAP_API_KEY=` — get a free key at
     https://openweathermap.org/api (sign up, then find your API key
     under your account).
   - `TIDE_API_KEY=` — get a key at https://www.worldtides.info/
   - `ADMIN_API_KEY=` — type any random password-like string here
     yourself, e.g. `my-secret-admin-key-12345`. You'll need to remember
     this exact value for Step 9.
   - Leave everything else as it already is — the database and Redis
     addresses already match what Step 5 started for you.

## Step 7 — Set up the database's tables

The database Step 5 started is empty — it has no tables yet. This step
creates them:

```
python -m alembic upgrade head
```

If this finishes with no red error text, your database now has the
correct structure.

## Step 8 — Run the automated tests (recommended, confirms everything works)

```
pytest -q
```

You should see something like `187 passed`. This confirms your setup is
correct before you try to run the real thing. If any tests fail, it
almost always means Step 5 or Step 7 didn't complete successfully —
re-check `docker compose ps` and re-run Step 7.

## Step 9 — Start the actual application

```
uvicorn main:app --reload
```

Leave this running — it's now your live backend server. You'll see log
output in the terminal. Open a web browser and go to:

```
http://127.0.0.1:8000/health
```

You should see `{"status":"ok","layers":["layer0","layer1","layer2"]}` —
this confirms the server is alive.

You can also open `http://127.0.0.1:8000/docs` in your browser for an
interactive page listing every available API endpoint.

## Step 10 — Run the real data-collection pipeline

This is the step that actually goes out onto the internet and pulls in
real information about places in Mangaluru — the step that could not be
done from within this conversation.

With the server from Step 9 still running, open a **second** terminal in
VS Code (**Terminal → New Terminal** again — this leaves Step 9's server
running in the first one), activate the environment again
(`source .venv/bin/activate` or the Windows equivalent from Step 3), and
run:

- **Mac/Linux:**
  ```
  curl -X POST http://127.0.0.1:8000/admin/pipeline/run \
    -H "X-Admin-Api-Key: my-secret-admin-key-12345"
  ```
- **Windows (PowerShell):**
  ```
  curl.exe -X POST http://127.0.0.1:8000/admin/pipeline/run -H "X-Admin-Api-Key: my-secret-admin-key-12345"
  ```

(Replace `my-secret-admin-key-12345` with whatever you actually typed
into `ADMIN_API_KEY` in Step 6.)

This can take anywhere from under a minute to several minutes, depending
on how much data OpenStreetMap returns for the Mangaluru area. When it
finishes, it prints back a report: how many places were collected, how
many were enriched with Wikipedia/Wikidata information, how many
duplicates were merged, and how many were actually saved.

**This is the real, honest production report** the earlier phases of
this project called for — it will only exist once you've run this step
yourself, since it needs your computer's normal internet access.

## Step 11 — Check the results

```
curl http://127.0.0.1:8000/admin/stats -H "X-Admin-Api-Key: my-secret-admin-key-12345"
```

This shows you current totals — how many places are in the database
right now.

You can also open the admin dashboard directly: find
`admin-dashboard/index.html` in the project folder in VS Code, right
click it, and choose **"Open with Live Server"** (if you have that
extension) or simply double-click it in your file explorer to open it
in a browser.

## Troubleshooting

- **"docker compose: command not found"** — Docker Desktop isn't running,
  or wasn't installed correctly. Reopen Docker Desktop and wait for the
  whale icon to show it's ready, then retry.
- **Tests fail with a connection error mentioning port 5432** — Postgres
  isn't running. Run `docker compose ps`; if it's not listed as
  running, run `docker compose up -d` again.
- **"ModuleNotFoundError" for any package name** — Step 4 wasn't
  completed, or your `.venv` isn't activated (you won't see `(.venv)` at
  the start of your terminal line). Re-run Step 3's activate command,
  then Step 4.
- **The pipeline run in Step 10 reports sources as "skipped"** — this is
  the system correctly telling you it couldn't reach that particular
  outside data source, rather than pretending it succeeded. Check your
  own internet connection, and double-check any API keys in `.env` for
  typos.
