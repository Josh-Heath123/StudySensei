# 0001: Rebuild StudySensei as a web app

- **Date:** 2026-11-12
- **Status:** Accepted

## Context

StudySensei was a PyQt5 desktop prototype: webcam focus and posture monitoring with MediaPipe, about 7,300 lines of Python
built in January 2026. An audit (PLAN.md §1) found that:

- it doesn't install from scratch, because MediaPipe is unpinned and 1.2.x dropped `mp.solutions`
- every session dies about 60 s after launch
- the posture score can't tell upright from slouched
- blink detection is wrong in both directions
- about 34 % of the code is unreachable

It has none of the academic features the product needs: modules, materials, planning, a tutor and practice.
A desktop UI toolkit is also slow to make polished, and other students would have to install it.

## Decision

Retire the PyQt code (archived at the git tag `v0-pyqt-prototype`) and rebuild as:

- **Web front end:** React + TypeScript + Vite, Tailwind + shadcn/ui, TanStack Query, Zustand.
  It is installable as a PWA, Chromium first.
- **API:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, managed with `uv`.
- **Database:** Postgres 16 + pgvector, run locally with docker-compose. It also holds full-text search and the job queue.
- **Camera and voice in the browser:** MediaPipe Tasks Vision in a Web Worker. Frames never leave the device.
- **Monorepo:** `apps/api`, `apps/web`, with a root `npm run dev` / `npm run check`.

Academic context (modules → materials → topic map → past papers → plan → sessions → practice → mastery) becomes the
centre of the product. The camera becomes an opt-in extra.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Fix the PyQt app | The measured parts don't work, the UI is hard to polish, and there's nothing worth keeping beyond the ideas |
| Python camera agent + web UI | Two runtimes to install; browser MediaPipe gives better blink and head-pose signals |
| Electron / Tauri desktop | Extra packaging for no benefit yet. Tauri stays the fallback if spike S1 shows background-tab throttling breaks the camera |
| Next.js | Server-side rendering isn't needed for an app behind a login |
| Node/TypeScript back end | Python has the best document-processing and ML libraries, and Pydantic doubles as AI-output validation |
| SQLite / a separate vector DB | Postgres covers relational data, vectors, keyword search and jobs in one service |

## Consequences

- The PyQt code is gone from the tree. `docs/legacy-notes.md` records the reusable ideas, and
  `git show v0-pyqt-prototype:<path>` recovers any file.
- Development needs Docker Desktop, uv and Node LTS.
- The browser camera has a known risk: browsers throttle tabs that aren't visible. Spike S1 tests this alongside Phase 2.
- Single local user until Phase 9. All tables still carry `user_id` from day one.
