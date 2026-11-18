# StudySensei — Assessment, Product Direction & Roadmap

> Archived. Personal identifiers redacted on 18 Nov 2026.

> **Frozen source document (12 Nov 2026).** The working docs split from it are
> [PRODUCT.md](../PRODUCT.md), [ARCHITECTURE.md](../ARCHITECTURE.md), [ROADMAP.md](../ROADMAP.md) and [decisions/](../decisions/).
> Edit those, not this file.

Nov 12, 2026 · @Joshua Heath

> **Decisions confirmed by Joshua on 12 Nov 2026**
> - The web rebuild is approved. Archive the PyQt code under the tag `v0-pyqt-prototype`.
> - Docker Desktop is installed, so use local Postgres via `docker-compose.yml`.
> - AI must cost nothing. Use the Gemini API free tier as primary (Flash for the tutor, topic maps and scanned papers; Flash-Lite for bulk classification) and the Groq free tier as fallback. Local Ollama is optional. All go through one OpenAI-compatible adapter; drop the Anthropic adapter for now. Free-tier prompts may be used by the provider, so never send personal data. Record this as `docs/decisions/0002-free-ai-providers.md`.
> - Test module: COS330 (exclude Joshua's own submissions from AI processing), at a local folder (its path is in `CLAUDE.local.md`, which isn't committed). This is read-only course material. Never copy it into the repo or commit it.
> - Diagrams from the online version of this plan appear below as "embedded content" placeholders; the surrounding text describes them.

## Summary

Today StudySensei is a webcam focus-and-posture monitor: a PyQt5 desktop app with MediaPipe and about 7,300 lines of Python, built over 7 commits between 19 and 26 January 2026. It has none of the academic, planning or AI features in your vision. Its main measurements also don't work yet. I ran and tested it, and confirmed these problems:

- **It doesn't start from a clean install.** `requirements.txt` doesn't pin MediaPipe. The current release (1.2.3) no longer includes the `mp.solutions` API that the code depends on.
- **Every session stops on its own about 60 seconds after launch.** The "memory manager" releases the camera and stops the processing timer, but the UI keeps showing the session as running.
- **The posture score can't tell upright from slouched.** Both score 38.8/100, because of two angle bugs. Calibration is saved but never used.
- **Blink detection is wrong both ways.** It misses almost every normal blink and counts a single 3-second eye closure as 29 blinks. Blink data makes up 30% of the focus score.
- **About 34% of the code (around 2,500 lines) is never reached from `main.py`.** That includes all of the analytics, SQLite storage, break logic and the ML predictor. Nothing is saved between sessions.
- **The UI was left mid-debug.** Every widget has a cyan border, the video box is red and yellow, and 222 `print` calls write about 105 lines a second to the console while it runs.

**What I recommend**

- **Keep the repository and its history, but not the PyQt code.** Tag the prototype, then carry forward its ideas rather than its code: the landmark sets, the session and time-series schema, the break heuristics and the focus-circle visual. This isn't rebuilding something that works, because the measured parts don't.
- **Rebuild it as a web app.** That means a React and TypeScript front end, a Python FastAPI back end, and Postgres with pgvector for search. Camera processing runs in the browser, so video never leaves the student's laptop.
- **Put academic context at the centre.** The flow is: modules, then materials, then a topic map, then evidence from past papers, then a plan, then sessions, then practice, then mastery, and then a new plan. The camera becomes an opt-in extra rather than the main feature.
- **Split the work clearly between AI and ordinary code.** AI reads, explains and suggests. Ordinary code owns timers, schedules, progress and every number labelled "measured".
- **Build it in ten phases, numbered 0 to 9, plus a list for later (section 4).** Phase 1 gives a usable core: modules, assessments and reliable study sessions. Phase 3 adds an AI tutor grounded in your own course material.

**What I need from you before Phase 0 ends**

1. Approve the move to a web app and retiring the PyQt code. It stays available under a git tag.
2. Choose which AI provider to start with, and supply an API key. Section 3 explains my default and the alternatives.
3. Pick one real module to use as a test case: its slides, notes, two or three past papers and the exam date. Confirm you're happy for that material to be sent to the AI provider.
4. Tell me whether Docker Desktop is installed on your PC. If it isn't, we'll use a free hosted Postgres database instead.

## 1. Current project assessment

StudySensei today is a single-window desktop prototype. It reads the webcam, runs face and body landmark models, and shows a "focus" circle, a posture percentage, a timer and two charts. It has no database in use, no user accounts, no AI or LLM, no microphone, no document handling, no modules or subjects, and no scheduling.

### How it is built

| Layer | Files | What it does |
| --- | --- | --- |
| Entry point | `main.py` | Starts Qt, loads the dark stylesheet and starts the memory manager |
| Window | `ui/main_window.py` (906 lines) | Builds the layout and Start/Stop/Toggle Mesh buttons, and connects engine signals to widgets |
| Engine | `services/studysensei_engine.py` | A `QTimer` every 33 ms on the UI thread reads the camera and processes every 3rd frame |
| Vision | `vision/gaze.py`, `posture.py`, `frame_processor.py`, `mediapipe_setup.py`, `emotion.py` | Uses MediaPipe FaceMesh (with iris) and Pose to work out gaze confidence, eye-aspect-ratio blinks and posture angles |
| Focus window | `core/focus_history.py` | Percentage of "focused" frames over the last 60 s |
| Widgets | `ui/focus_circle_widget.py`, `metrics_panel.py`, `video_widget.py`, `analytics_widget.py`, `sidebar_*.py` | Display |
| Not connected | `analytics/*`, `services/video_processor.py`, `services/state_manager.py`, `utils/memory_manager.py`, `utils/image_utils.py` | Left over from the Streamlit version; nothing imports them |

It runs on Python 3.10 with PyQt5, PyQtChart, OpenCV, MediaPipe's legacy Solutions API, numpy and psutil. Streamlit, fer, pandas, scikit-learn and joblib are still in `requirements.txt` but the live app doesn't use them.

### Feature inventory

| Feature | Status | Evidence |
| --- | --- | --- |
| Webcam capture and preview | Works, with flaws | Preview switches between annotated and raw frames (2 of every 3 frames skip processing); the debug drawing code repaints synchronously on every frame |
| Session timer | Works until the session dies | Counts correctly, but the session stops about 60 s after launch (see defects) |
| Focus circle | Works | Animated ring, but the number behind it isn't meaningful (next two rows) |
| Gaze-based focus score | Partial | Measures whether the iris is centred in the eye. That isn't focus: a student reading notes on the desk scores as "distracted". The right-eye width ignores vertical distance (`gaze.py` line 62) |
| Blink rate / fatigue | Broken | In my replay test it detected 3 of 15 real blinks per minute, and counted one 3-second eye closure as 29 blinks |
| Posture score | Broken | Synthetic test: upright 38.8, slouched 38.8, leaning sideways 29.1. Neck and shoulder angles read about 90° when ideal because `abs(90 - angle)` is wrong |
| Posture calibration | Present but not working | Saves a JSON file, but `compute_posture_score` ignores it, and the PyQt UI has no calibrate button |
| Slouch alert | Present but not working | The alert text is generated but never displayed |
| Emotion detection | Present but not working | `toggle_emotion` in the engine never calls `enable()`, so it can't run, and there's no UI control for it |
| Analytics charts | Partial | X-axis uses `timestamp % 60`, so lines zig-zag back after a minute. "Every 2 s" sampling actually adds about 10 points a second, and with a 100-point cap only about 20 s is shown |
| CSV export | Works | Exports only the in-memory chart points |
| Saving sessions | Missing | `closeEvent` has `# TODO: Save session data`; the SQLite store is never called |
| Breaks, session phases, patterns, ML predictor | Present but not working | About 1,500 lines in `analytics/` that nothing reaches |
| Sidebar navigation | Works | Switches between the Main and Analytics views |

### Defects I confirmed by running it

1. **The app doesn't start from a fresh install.** `mediapipe>=0.10.0` resolves to 1.2.3, which has no `mp.solutions`. The code's fallback import also fails, and the app raises `ImportError` on startup.
2. **Sessions stop after 60 s.** `PyQtMemoryManager.periodic_cleanup()` runs every 60 s, measured from app launch. It calls `release()` on the registered camera and `stop()` on the processing timer. In my headless run with a simulated camera, the last frame was processed at 59.9 s. After that, `engine.running` stayed `True` with the camera closed. The code implies that if you press Start more than 60 s after launch, the session dies on its first frame.
3. **Posture metrics are inverted.** In `vision/posture.py`, `compute_neck_angle` and `compute_shoulder_roll` return about 90° for perfect alignment. That zeroes 45% of the posture weighting for everyone. `compute_forward_head_ratio` measures sideways head offset, not forward head posture, which a front-facing camera can't see that way.
4. **Blink logic.** It takes a median over 10 frames, which filters real blinks out. It also has no edge detection, so it counts every closed-eye frame as a blink.
5. **Computer vision runs on the UI thread.** MediaPipe Pose plus FaceMesh run inside the Qt timer, so slow frames freeze the interface.

### Technical debt

- **`.venv/` is committed:** 1,476 files from an MSYS2 Python that contains only pip and setuptools. Your real environment can't be reproduced from the repo.
- **Line endings:** 42 files show as modified, but nothing changes apart from CRLF line endings, so there is no unsaved work.
- **Outdated docs:** the README says to run `streamlit run app.py`, but `app.py` was deleted in the latest commit. `PYQT_SETUP.md` lists features as to-dos that partly exist.
- **No tests, CI, licence or pinned versions.**
- **Two duplicate engines:** a threaded `VideoProcessor` and the `QTimer` engine. Module-level global state, Streamlit shims inside PyQt code, an import of a `posture_simple` module that doesn't exist, and broad `except: pass` blocks that hide errors.

### Retain, refactor, replace or remove

| Component | Decision | Reason |
| --- | --- | --- |
| Repository and git history | Retain | Tag the prototype `v0-pyqt-prototype` so it can always be restored |
| `vision/gaze.py`, `frame_processor.py`, `mediapipe_setup.py` | Replace | Move to the browser. MediaPipe's FaceLandmarker gives blink scores and head angles directly |
| `vision/posture.py` | Replace, keep the ideas | Redesign around deviation from the student's own baseline. Keep the visibility checks and the choice of signals (shoulder tilt, head drop) |
| `vision/emotion.py` | Remove | Inaccurate in normal lighting, sensitive, and doesn't help anyone study |
| `services/studysensei_engine.py` | Replace | Keep the design idea (engine produces signals, UI subscribes); rebuild it in TypeScript |
| `analytics/session_store.py` | Reuse the schema ideas | Sessions, time series and behaviour patterns carry over into the new Postgres model |
| `analytics/break_logic.py` | Port the rules | Throttling plus a reasons list is a sound basis for the interventions engine |
| `analytics/time_series.py`, `behavior_model.py` | Revisit in Phase 8 | Phase and pattern heuristics are only worth tuning against real data |
| `analytics/ml_predictor.py` | Shelve | A random forest needs far more labelled sessions than one student produces |
| `ui/*`, `styles/*.qss` | Replace | Keep the focus-ring visual and the colour palette as design-system input |
| `utils/*memory_manager.py`, `image_utils.py`, `services/state_manager.py`, `services/video_processor.py` | Remove | Unused, or actively harmful |
| `.venv/` | Remove from git | Recreate it locally with `uv` |

## 2. Recommended product direction

StudySensei should be a study planner and tutor that knows your modules and your habits. It is built around one loop: know what's coming, decide what to study, study with support, check understanding, then adjust. Camera and voice support the study session. They aren't the product.

**Product statement:** *StudySensei tells you what to study next and why, helps you while you study it, and gets more accurate about you every week, using your own course material and your own study record.*

&#91;embedded content: The core loop and its shared context\]

New materials and assessments can arrive at any time. Each one updates the shared context, and the next plan reflects it.

### The student's journey

1. **Onboarding, about 10 minutes.** Create an account and add your modules. Upload a course outline or study guide, and StudySensei proposes assessments, dates and topics for you to confirm. Set your weekly available hours, and get a first plan.
2. **Building module knowledge.** Upload slides, notes, tutorials and past papers, and watch their processing status. Review the proposed topic map: confirm, rename, merge or delete topics. Once past papers are processed, the module shows its assessment profile.
3. **Today.** The Today screen shows the next study block and why it was chosen. For example: "Thermodynamics: entropy. Exam in 12 days. Seen in 4 of 5 past papers. Last practice score 62%." It also shows reviews that are due and upcoming deadlines.
4. **Study session.** Start a block and choose whether to turn on the camera and microphone. You get a timer with planned breaks, plus a side panel with the topic's materials, a tutor that cites its sources, and "quiz me". Nudges are rare and only appear when there's evidence for them. The session ends with a 20-second reflection: focus from 1 to 5, what you covered, and your confidence per topic.
5. **Practice and review.** Spaced-repetition reviews, past-paper questions by topic, and timed past-paper mode in the final week before an exam.
6. **Weekly review.** Hours planned against hours studied, mastery trends, and what changes next week. Each insight is labelled "measured" or "estimated", with how much evidence it's based on.

### How the features share context

| Shared data | Produced by | Used by |
| --- | --- | --- |
| Topic map (per module) | Document processing plus your edits | Tutor search scope, question generation, plan units, mastery tracking |
| Past-paper profile | Past-paper analysis | Plan priority, choice of study method, practice question style, tutor emphasis ("usually examined as a calculation") |
| Topic mastery | Practice results, reviews, self-ratings | How the plan allocates time, review scheduling, spotting when you're struggling in a session |
| Session log and reflections | Study sessions | Student profile (session length, best times), realistic plan capacity |
| Camera signals (opt-in, per-minute summaries only) | In-browser vision | Break timing, posture nudges, "estimated" profile items |
| Assessments and availability | You | Hard limits on the plan |

This is how an uploaded exam paper reaches the session. Questions are mapped to topics, which raises those topics' priority in the plan. The tutor then pulls those questions into "quiz me" while you study the topic.

### The student profile: measured versus estimated

| Profile item | How it's derived | Label | Shown after |
| --- | --- | --- | --- |
| Usual session length before a break | Median active minutes before the first unplanned pause, absence or early end | Measured | 5 sessions |
| Consistency | Days studied per week, and planned blocks completed versus skipped | Measured | 1 week |
| Break habits | Break count and length against the plan | Measured | 5 sessions |
| Most productive times | Completion rate, self-rated focus and practice accuracy, grouped by time of day | Estimated (from measured inputs) | 10 sessions across 3 or more time bands |
| Topic mastery | Spaced-repetition memory model plus practice accuracy and self-confidence | Estimated | 3 practice attempts per topic |
| Which methods work for you | Mastery gained per minute, by study method and topic type | Estimated | About 5 sessions per method |
| Time away from desk | Face present or absent (camera) | Measured, if the camera is on | 3 camera sessions |
| Posture drift | Minutes spent noticeably lower, closer or more tilted than your calibrated baseline | Estimated | 3 camera sessions |

Rule: nothing is shown before its minimum evidence, and every insight states what it's based on. Until then, StudySensei uses general evidence-based defaults (for example, 25 to 50 minute blocks) and says that's what they are.

### Academic context for each module

- **Topics:** a tree of topics and subtopics with learning objectives, linked to the pages and slides where they're taught. Your edits always win over the AI's suggestions.
- **Assessments:** date, weight, the topics they cover and their status. Assignments are tracked as tasks with deadlines.
- **Past-paper evidence:** each question has its source paper, number, marks, topics, type (recall, explain, apply, calculate, essay) and an estimated difficulty.
- **Assessment profile:** for example, "Entropy: in 4 of 5 papers, 17% of marks on average, mostly application questions." Click through to the actual questions. Forward-looking statements are labelled *Likely emphasis (estimate, based on 5 papers)*. They're never presented as "will be in the exam", and they're hidden when there are fewer than 3 papers.

### What AI does and what ordinary code does

| Responsibility | Done by | Why |
| --- | --- | --- |
| Extracting text, chunking, search | Ordinary code (plus local embeddings) | Fast, free, repeatable |
| Proposing topic maps; segmenting and classifying past-paper questions | AI, then you review | Needs reading comprehension; output is checked against a fixed structure before it's saved |
| Explaining concepts, answering questions, generating practice | AI | This is where it adds the most |
| Marking short written answers | AI, with the reference answer and source shown | Self-marking stays available |
| Assessment-profile statistics | Ordinary code | Counts and percentages must be exact |
| Scheduling, re-planning, feasibility | Ordinary code (a tested planner) | Must be predictable and explainable |
| Choosing the study method for a block | Ordinary code (a rules table); AI writes the explanation | Consistent decisions, friendly wording |
| Timers, breaks, reminders, progress | Ordinary code | Must never be wrong |
| Camera signals and nudges | Ordinary code (in the browser, with hysteresis and rate limits) | Real-time, private, free |
| Weekly insight write-up | AI writes up statistics that ordinary code computed | The AI never invents a number |

### Features I'd add that weren't in your brief

1. **End-of-session reflection (20 s).** It's the only real ground truth for focus, and it powers the profile.
2. **Practice engine with spaced repetition (FSRS algorithm).** This is the biggest lever on actual results, and mastery tracking depends on it.
3. **Citations on every tutor answer** (slide or page), so you can check them in one click.
4. **Weekly availability and a feasibility check.** For example: "You need 14 h but have 9 h available, so these topics get cut."
5. **Importing a course outline or study guide** to create assessments and their scope automatically.
6. **Calendar export** (an ICS feed for Google or Outlook).
7. **A small always-on-top companion window** with the timer, status and push-to-talk, for when you're working in a PDF reader or another app.
8. **A privacy centre** showing what's collected, how long it's kept, and buttons to export or delete it.
9. **A per-user AI budget and cost log**, to keep running costs predictable.
10. **Later: an MCP connector**, so students can bring StudySensei's context into the AI assistant they already use.

### Where I'd push back on the original ideas

- **Gaze-based "focus %".** I'd drop it as a headline number. A webcam can't see focus, and looking down at a textbook isn't distraction. Replace it with time away from the desk, completed blocks and self-rated focus.
- **Emotion detection.** I'd drop it. It's inaccurate, sensitive, and can't be acted on.
- **Always-on microphone or audio monitoring.** I'd make the microphone push-to-talk only. Constant listening adds privacy risk and false triggers without helping anyone study.
- **Real-time voice conversation.** Start with push-to-talk: speech to text, then a streamed answer, then text to speech. Real-time speech-to-speech APIs cost more and can come later if the delay feels too long.
- **"Connect the student's personal AI."** Consumer plans like ChatGPT Plus or Claude Pro don't come with API keys. Bring-your-own-key means a separate pay-as-you-go key. The realistic order is: a built-in model with a usage budget, then optional bring-your-own-key, then the MCP connector.
- **Predicting exam questions.** Show evidence and estimated emphasis only, from 3 or more papers.
- **ML behaviour prediction.** Use rules and plain statistics first. Machine learning is only worth it once there are hundreds of sessions.
- **Posture.** Be honest about the scope: a front-facing laptop camera can tell when you're lower, closer or more tilted than your own baseline. It can't judge your spine.

## 3. Technical architecture

The recommended stack is a React web app plus a Python API, a background worker, and one Postgres database. Camera and voice run in the browser, and AI providers sit behind a small interface we write ourselves. Everything runs on your PC during development, and the hosted version needs only small, cheap services.

&#91;embedded content: System architecture: browser, server, external services\]

The browser does the real-time work: timers, nudges, camera and voice. The server owns stored data, search, AI calls and anything that runs in the background.

### Key decisions

| Decision | Choice | Alternatives considered | Why |
| --- | --- | --- | --- |
| Platform | Web app that can be installed as an app (PWA), Chromium browsers first | Keep PyQt desktop; Python camera agent plus web UI; Electron or Tauri desktop; native mobile | A polished interface is far easier to build on the web, there's nothing for other students to install, and the camera code runs on-device. If the background-tab test (run alongside Phase 2) fails, Tauri can wrap the same code |
| Front end | React + TypeScript + Vite, Tailwind with shadcn/ui components, TanStack Query, Zustand | Next.js; Svelte | Biggest ecosystem and component library. Server-side rendering isn't needed for an app behind a login |
| Back end | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 and Alembic, managed with `uv` | Node/TypeScript full-stack; Django | Python has the best document-processing and ML libraries, you already work in it, and Pydantic models double as the checks on AI output |
| Database | Postgres 16 with pgvector and built-in full-text search | SQLite with sqlite-vec; a separate vector database (Qdrant, Chroma) | One service holds relational data, vector search, keyword search and the job queue. A separate vector database adds operations work for no benefit at this scale |
| Background jobs | A worker process polling a Postgres `jobs` table (`FOR UPDATE SKIP LOCKED`) | Celery or RQ with Redis; FastAPI BackgroundTasks | No Redis needed, jobs survive restarts, and it's simple to test |
| Embeddings | Local: `fastembed` running `BAAI/bge-small-en-v1.5` (384 dimensions, CPU, ONNX) | Paid provider embeddings; Ollama | Free, private and quick enough. Switching later means re-embedding, which is cheap at this scale |
| LLM access | Our own `LLMClient` with two adapters: Anthropic, and OpenAI-compatible (covers OpenAI, Gemini, OpenRouter, Groq and Ollama) | LiteLLM; LangChain | About 200 lines we fully control, with no heavy framework |
| Default models | Fast tier (tutor chat, classification, question generation): a Claude Haiku-class model. Deep tier (topic maps, past-paper analysis, weekly write-up): a Claude Sonnet-class model | Gemini Flash models (cheaper); local Ollama models | Reliable structured output and long context for slides. Any OpenAI-compatible provider can be swapped in per tier through settings |
| Bring your own key | Optional, encrypted at rest, removes the usage cap | Bring-your-own-key only | Most students don't have API keys. The default is a built-in key with a monthly budget per user |
| PDF text | `pypdfium2` (Apache/BSD), `python-pptx`, `python-docx` | PyMuPDF; Docling | PyMuPDF is AGPL-licensed, which is a problem for a hosted product. Docling pulls in PyTorch, which is heavy |
| Scanned pages | Detect pages with no text layer; transcribe them with a vision-capable LLM after you opt in (shows the page count and cost) | Tesseract OCR | Many past papers are scans, and Tesseract handles maths and handwriting badly |
| Spaced repetition | FSRS (`ts-fsrs` / `py-fsrs`, MIT licence) | SM-2 (Anki's original algorithm) | Fewer reviews for the same retention, and a well-maintained library |
| Camera | MediaPipe Tasks Vision for the web (FaceLandmarker with blendshapes and head-pose matrix; PoseLandmarker lite) in a Web Worker | Port the Python version; a cloud vision API | Free, private, and gives proper blink and head-angle signals |
| Speech | Push-to-talk. Speech to text: browser Web Speech API first, server transcription as an option. Text to speech: browser `speechSynthesis` | OpenAI Realtime or Gemini Live speech-to-speech | Zero cost to start; the two-step approach can be upgraded later without changing the rest |
| Auth and hosting | Single local user until Phase 9. Then Supabase (Postgres + pgvector + Auth + Storage) for the database, plus one small container for the API and worker | Neon + our own auth + R2; Firebase | One free-tier provider covers four needs, and it's standard Postgres, so moving off it later is easy |

### Repository structure

```
StudySensei/
  apps/
    api/                      FastAPI service + worker (one Python package)
      app/
        api/                  routers: modules, materials, assessments, sessions, plan, tutor, practice, profile
        core/                 config, db, security, storage
        models/               SQLAlchemy models
        schemas/              Pydantic request/response + AI output schemas
        services/             planning/, mastery/, profile/, ingestion/, pastpapers/
        ai/                   llm_client.py, adapters/, prompts/, retrieval.py, budget.py
        jobs/                 worker.py, tasks/
      alembic/
      tests/
      evals/                  fixed test sets for tutor answers, topic extraction, past-paper parsing
    web/                      React app
      src/
        app/                  routes, layout, providers
        features/             today/, modules/, session/, plan/, practice/, insights/, settings/
        vision/               camera.ts, vision.worker.ts, signals.ts, calibration.ts, rollup.ts
        voice/                stt.ts, tts.ts
        session-engine/       timer.ts, interventions.ts
        lib/api/              client generated from OpenAPI
        ui/                   design-system components
  docs/                       PRODUCT.md, ARCHITECTURE.md, ROADMAP.md, decisions/
  CLAUDE.md
  docker-compose.yml          postgres + pgvector
  package.json                root "npm run dev" starts db + api + worker + web
```

### Data model

Every table has a UUID primary key, `user_id` (except child tables reached through a parent), and `created_at`/`updated_at` timestamps. Derived tables can always be rebuilt from source tables.

| Area | Tables | Notes |
| --- | --- | --- |
| People and settings | `users`, `ai_credentials`, `consents`, `push_subscriptions` | Keys encrypted with Fernet; consent is per feature (camera, mic, AI processing) with timestamps |
| Academic structure | `modules`, `topics` (tree via `parent_id`), `assessments`, `assessment_topics`, `tasks` | `topics.source` is `ai` or `user`; user edits are never overwritten |
| Materials | `materials`, `chunks` (text, page range, `embedding vector(384)`, `tsv tsvector`), `chunk_topics` | `materials.kind`: slides, notes, guide, tutorial, past paper, test, assignment, outline; SHA-256 hash to skip duplicates |
| Past papers | `past_questions` (paper label, year, number, marks, type, difficulty, page), `past_question_topics` | The profile is computed by queries, not stored as AI output |
| Planning | `availability_rules`, `availability_exceptions`, `plan_blocks` (start, duration, topic, method, status, reason) | `plan_version` on each block so you can see what changed |
| Sessions | `study_sessions`, `session_events` (pause, break, away, nudge shown or dismissed, question asked), `session_minutes` (per-minute camera summaries) | No images or audio, ever |
| Practice | `practice_items` (flashcard or question, source chunk IDs, where it came from), `reviews` (grade plus FSRS state) |  |
| Derived | `topic_mastery`, `profile_metrics` (value, sample size, label: measured or estimated), `recommendations` (message, evidence, status) | Rebuilt nightly and after each session |
| AI | `conversations`, `messages` (with citations), `ai_usage` (provider, model, tokens, estimated cost, feature) | Usage drives the budget and the cost dashboard |
| System | `jobs` (kind, payload, status, attempts, run\_after, error) |  |

### AI integration

- **One interface:** `LLMClient.complete(tier, messages, schema=None, stream=False)`. Each feature asks for a tier, not a specific model. Settings map each tier to a provider and model, per user when they bring their own key.
- **Structured output:** every AI result that gets saved (topics, questions, classifications) is checked against a Pydantic schema. It's retried once if invalid, otherwise the job is marked for manual review.
- **AI suggests, code decides:** AI writes proposals, and ordinary code decides what is stored and scheduled. The AI never changes the plan, deletes data or sends notifications itself.
- **Uploaded documents are untrusted input.** Retrieved text is labelled as source material in prompts, so it can't redirect the tutor.
- **Cost controls:** two tiers, a token limit per feature, prompt caching for repeated context, processing each file once (by hash), caching generated practice items, and a monthly budget per user enforced in `ai/budget.py`.
- **Later (Phase 10):** an MCP server exposing read-only tools (`get_modules`, `get_plan`, `get_weak_topics`, `search_materials`) so students can use StudySensei context from Claude or ChatGPT.

### Document pipeline

1. **Upload:** a size limit of 50 MB and an allowed file-type list. The file is stored through a `Storage` interface (local folder in development, Supabase Storage when hosted), and a hash is recorded.
2. **Extract:** text per page or slide, with titles and speaker notes. Pages with no text layer are flagged as scanned.
3. **Chunk:** split along page and slide boundaries, about 400 to 800 tokens, keeping the page reference.
4. **Index:** local embeddings into `chunks.embedding`, plus a `tsvector` for keyword search.
5. **Understand (deep tier):** AI proposes topics for each material, then merges them into the module's topic tree. Chunks are linked to topics by similarity, and you review it.
6. **Past papers:** AI splits the paper into questions with marks, maps each to topics, and classifies its type and difficulty. Ordinary code then recomputes the module's assessment profile.
7. **Search at question time:** vector and keyword search (top 20 each) are merged by reciprocal rank fusion, filtered to the module, boosted for the current topic, and the top 8 chunks are cited as \[S1\] to \[S8\].

### Camera and microphone

- **Camera:** `getUserMedia` at 640×480. Face landmarks are processed at about 5 frames a second and pose at about 1 a second, in a Web Worker, and slowed automatically on weak laptops. Signal logic lives in `signals.ts` as pure functions:
  - presence
  - head yaw and pitch, from the transformation matrix
  - eye closure, from blink blendshapes with edge detection and hysteresis
  - posture features compared with your 5-second calibration: face size (distance from the screen), nose height relative to the shoulder line (slumping), and shoulder tilt
- **Study mode setting:** "Screen" or "Desk/paper". In desk mode, looking down is normal and doesn't count against you.
- **What leaves the browser:** only per-minute summaries (presence ratio, head-away ratio, posture deviation, long eye closures). Frames are never stored or sent anywhere.
- **Interventions engine** (`interventions.ts`, ordinary code):
  - Posture nudge only after 3 minutes of continuous drift, at most once every 15 minutes, and never in the first 10 minutes.
  - Away for more than 5 minutes pauses the timer.
  - Break prompts come from the plan, adjusted by your measured session length.
  - Struggle suggestions come from repeated wrong answers or repeated confusion questions on the same topic.
  - Quiet mode silences everything except breaks.
- **Main technical risk:** browsers slow down tabs that aren't visible. A short test run alongside Phase 2 tries three approaches: processing in a Web Worker fed by `MediaStreamTrackProcessor`, the Document Picture-in-Picture companion window (Chrome/Edge), and, as a fallback, a Tauri wrapper.
- **Microphone:** push-to-talk only (hold Space or tap the mic). Speech to text goes through an interface: the Web Speech API by default (Chrome sends audio to Google, Edge to Microsoft, and the app says so), or server transcription. The answer streams back over SSE and `speechSynthesis` reads it sentence by sentence. Target: speaking starts within 2.5 s of releasing the key. Audio isn't stored; the transcript becomes a chat message you can delete.

### Behaviour tracking

Raw facts are sessions, events, per-minute summaries, reviews and plan blocks. A nightly job, also run after every session, computes `profile_metrics` with sample sizes and measured/estimated labels using the definitions in section 2. Recommendation rules (for example, "usual session length below the planned block length for 5 or more sessions, so shorten blocks") create `recommendations` that include their evidence. The AI only rewrites them in friendlier language.

### Scheduling and notifications

- **Planner (`services/planning/`):** a pure function taking availability, assessments, topic workload, mastery, past-paper importance and your preferred block length, and returning plan blocks plus a feasibility report.
  - Priority = importance × (1 − mastery) × urgency.
  - Every in-scope topic gets at least 2 spaced sessions plus a final review before the exam, where time allows.
  - Daily caps, and the next 24 hours stay fixed unless you change them.
- **Re-planning triggers:** a new assessment or material, a skipped or finished block, a mastery change, and a nightly job.
- **Study method per block:** a rules table based on question type, mastery and days left. Application-heavy topics get practice problems and past papers, definitions get active recall and flashcards, low mastery early on means learning and summarising, and the last 7 days means timed past papers.
- **Timers:** live in the browser and are based on start and end timestamps, so a reload or a throttled tab can't drift them. Every change is logged to the server as an event.
- **Reminders:** Web Push (VAPID keys and `pywebpush` from the worker), in-app notifications, and a private ICS calendar feed.

### Privacy and security

- **Camera and microphone:**
  - Off by default, and asked for each session, with an option to remember the choice.
  - A visible indicator in the header and the companion window, plus a one-click pause (and a keyboard shortcut).
  - Both turn off automatically when the session ends.
- **Retention:** per-minute camera summaries are kept for 90 days, then reduced to session totals. Documents and chats are kept until you delete them, and deleting a material also deletes its chunks and embeddings. There are buttons to export and delete everything.
- **Security:**
  - Every query is scoped to the user, with tests that try to read across users.
  - API keys are encrypted.
  - AI endpoints are rate-limited and uploads are checked.
  - The privacy page names the AI provider and states its no-training API terms.
- **Before multi-user launch:** check compliance with POPIA (South Africa's privacy law) and any other jurisdictions involved: lawful basis and consent, purpose limitation, data-subject access and deletion, and an information officer.

### Local development environment

Everything runs natively on Windows:

- Git and `uv` (Python 3.12)
- Node.js LTS
- Docker Desktop for Postgres (or a free Neon/Supabase database if Docker isn't an option)
- Claude Code

`npm run dev` at the repo root starts Postgres, the API with reload, the worker and the Vite dev server. A seed script creates the local user and an example module. Secrets live in `.env`, which is never committed, with `.env.example` documenting each setting.

### Testing and deployment

- **Back end:** `pytest` against a real Postgres. The planner, mastery, profile metrics and budget code get unit and property-based tests (Hypothesis). Ingestion is tested with fixture PDF and PPTX files.
- **Front end:** Vitest for `timer.ts`, `signals.ts` and `interventions.ts`, using recorded landmark traces (numbers only) as fixtures. This is exactly the test that would have caught the posture and blink bugs. Playwright covers the main flows.
- **AI quality:** `evals/` holds fixed test sets built from your real module, for tutor answers with expected citations, topic extraction and past-paper parsing. They run before and after every prompt or model change, with results logged.
- **CI:** GitHub Actions runs ruff, mypy, pytest (with a pgvector service container), eslint, tsc and vitest on every pull request, and Playwright on main.
- **Hosting from Phase 9:**
  - One Docker image for the API and worker on Fly.io, Railway or a small Hetzner VM.
  - Supabase for Postgres, Auth and Storage.
  - The web build on Cloudflare Pages.

  Hosting should cost little or nothing at beta scale. AI usage is the cost to watch, and `ai_usage` measures it.

## 4. Development roadmap

The roadmap has ten phases (0 to 9), a list for later, and three short parallel spikes. Every phase ends with software you use in real study before the next one starts. The order follows dependencies first, then value. Daily use comes first without AI, then AI grounded in your material, then planning and practice, then past papers. Camera and beta come last because they matter least for learning and carry the most risk.

&#91;embedded content: Roadmap: phases 0 to 9 plus later, 4 gates, 3 parallel spikes\]

Each gate is a point where you review real use in this Project before the next phase starts. The dashed boxes are short experiments that de-risk a later phase.

**Sizes are relative:** S is a handful of focused Claude Code sessions, M roughly twice that, and L roughly three to four times. Each phase is split into tasks of one session or one pull request each in `docs/ROADMAP.md`.

**What can run in parallel:**

- **Spike S3 (visual direction)** runs alongside Phases 0 and 1.
- **Spike S1 (camera in the browser)** runs alongside Phase 2, because its result decides between web and Tauri for Phase 7.
- **Spike S2 (past-paper parsing accuracy)** runs alongside Phases 4 and 5, using your real papers.
- **Phase 7 (camera)** can be pulled forward at any point after Phase 1 and S1 if you want it sooner. Nothing else depends on it.

**What should wait:** user accounts, hosting, the MCP connector and any machine learning. They all depend on a product that's already proven useful.

### Phase 0: Reset and foundations (S)

- **Objective:** a clean repository and a running skeleton, so every later phase starts from a working build.
- **Tasks:**
  1. Tag `v0-pyqt-prototype`, push the tag, and create the branch `rebuild`.
  2. Stop tracking `.venv/`, add `.gitattributes` (`* text=auto eol=lf`) and normalise line endings.
  3. Remove the legacy code from the working tree (it stays in the tag) and write `docs/legacy-notes.md` listing the reusable ideas.
  4. Scaffold `apps/api`:
     - `uv`, FastAPI, a `/health` endpoint and `pydantic-settings`
     - SQLAlchemy and Alembic, with a first migration for `users` and a seeded local user
  5. Scaffold `apps/web`:
     - Vite, React, TypeScript, Tailwind, shadcn/ui and a router
     - the app shell with the sidebar: Today, Modules, Plan, Practice, Insights, Settings
  6. Add `docker-compose.yml` (`pgvector/pgvector:pg16`) and a root `package.json` whose `dev` script starts everything.
  7. Generate the TypeScript API client from OpenAPI.
  8. Set up linting, type checks and tests (ruff, mypy, pytest, eslint, prettier, vitest) and a GitHub Actions workflow to run them.
  9. Write `CLAUDE.md`, `docs/PRODUCT.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md` and `docs/decisions/0001-web-rebuild.md`.
- **Depends on:** your approval of the move to a web app, and the Docker answer.
- **Verify:** a fresh clone on your PC runs by following the README, and CI passes on the first pull request.
- **Done when:**

* [ ] `npm run dev` opens the app shell showing "API connected" and "Database connected"
* [ ] CI runs on every pull request and passes
* [ ] CLAUDE.md and the four docs are committed

### Phase 1: Modules, assessments and study sessions (M)

- **Objective:** a tool you can use every day, before any AI.
- **Features:**
  - creating, editing and deleting modules (code, name, colour, semester)
  - a manual topic tree
  - assessments with date, weight and scope, and assignment tasks
  - a Today page with upcoming deadlines
  - a study session screen: focus and break cycles, pause, end, and a 20-second reflection
  - session history for each module
- **Tasks:**
  1. Models and migrations: `modules`, `topics`, `assessments`, `assessment_topics`, `tasks`, `study_sessions`, `session_events`.
  2. REST endpoints with API tests.
  3. `session-engine/timer.ts`, based on timestamps and saved to `localStorage` plus server events, so a reload or sleep can't lose time.
  4. Design system v1 (tokens, type scale, core components) from S3, plus empty states.
- **Key files:** `apps/api/app/models/`, `apps/api/app/api/modules.py`, `sessions.py`; `apps/web/src/features/session/`, `today/`, `modules/`.
- **Verify:** unit tests for pause and resume arithmetic, reload and sleep. Then a real 50-minute session with one reload and one break, where the timer matches the clock to within 1 s.
- **Done when:**

* [ ] Three real study days logged in StudySensei with no lost time
* [ ] All session and timer tests pass in CI

### Phase 2: Materials and topic maps (L)

- **Objective:** StudySensei understands a module from its files.
- **Features:** drag-and-drop upload, processing status, a materials viewer (pdf.js) that jumps to a page, search across the module, and a proposed topic map you review and edit. Settings for the AI provider and key.
- **Tasks:**
  1. The `Storage` interface, the `jobs` table and the worker.
  2. Extractors for PDF, PPTX and DOCX, plus a flag for scanned pages.
  3. Chunker, `fastembed` embeddings, `tsvector`, and a hybrid search endpoint.
  4. `LLMClient` with the Anthropic and OpenAI-compatible adapters, `ai_usage` logging and budget checks.
  5. Topic-extraction prompts with Pydantic schemas (per material first, then merged per module), linking chunks to topics.
  6. A topic review UI.
  7. `evals/topic_extraction` and `evals/search` built from your module.
- **Depends on:** Phase 1, an AI key, and your test module's files.
- **Verify:**
  - Fixture tests for the extractors.
  - For 12 of 15 hand-written search queries, the right slide is in the top 3.
  - You keep at least 80% of the proposed topics with only small edits.
- **Done when:**

* [ ] A real module with at least 3 slide decks gets a topic map within about 3 minutes of upload
* [ ] Every AI call appears in `ai_usage` with its cost

### Phase 3: Grounded tutor and voice v1 (M)

- **Objective:** help during study, answered from your own material.
- **Features:**
  - a tutor panel in the session, scoped to the module and topic
  - streamed answers with clickable citations
  - "Explain differently", "Give an example" and "Quiz me" (3 quick questions)
  - maths rendering (KaTeX)
  - push-to-talk with spoken answers
- **Tasks:**
  1. Retrieval with a boost for the current topic.
  2. Prompt templates and an SSE endpoint.
  3. `conversations` and `messages` storage.
  4. Citations that link to the material viewer.
  5. The `stt.ts` and `tts.ts` interfaces.
  6. Latency timing.
  7. `evals/tutor`: 20 questions with expected source pages.
- **Verify:**
  - At least 85% of eval answers cite a correct page.
  - Typical time to first token under 2 s.
  - Speech starts within 2.5 s in Chrome and Edge.
- **Done when:**

* [ ] You've used the tutor in 3 real sessions and found it useful
* [ ] Tutor evals are recorded in `evals/results/`

### Phase 4: Planner v1 (L)

- **Objective:** StudySensei decides what to study next and explains why.
- **Features:**
  - weekly availability
  - workload per topic (estimated from material size, editable) and a starting confidence rating per topic
  - plan generation, a week view (drag to move, mark days unavailable) and the next block on Today with its reason
  - a feasibility report and re-planning when you skip or finish a block or add an assessment
  - a study method per block
  - Web Push reminders and an ICS feed
- **Tasks:**
  1. Availability models.
  2. `services/planning/` as a pure function, with property tests:
     - no overlaps
     - stays within availability
     - respects the daily cap
     - every in-scope topic gets 2 or more sessions when there's time
     - a final review before each exam
  3. The rules table for study methods, and the text explaining each block's reason.
  4. Re-planning triggers, push subscriptions and the worker sender, and the ICS endpoint.
- **Depends on:** Phases 1 and 2.
- **Verify:** a scenario test with 2 modules, exams in 10 and 20 days and 12 hours a week available. Then skip a block by hand and check that the plan adjusts and says why.
- **Done when:**

* [ ] You follow the plan for one week, needing at most one manual change a day
* [ ] The planner property tests pass

### Phase 5: Practice and mastery (M)

- **Objective:** measure understanding and build it.
- **Features:**
  - generated flashcards and questions linked to their source, plus your own cards
  - an FSRS review queue
  - short-answer marking (AI against a reference answer) or self-marking
  - mastery per topic, which "Quiz me" and the planner both use
- **Tasks:**
  1. `practice_items` and `reviews`, and a generation job.
  2. FSRS integration.
  3. The mastery formula, documented in `services/mastery/README.md`.
  4. The practice UI, and connecting mastery to the planner.
- **Verify:**
  - Unit tests for mastery.
  - A spot check of 30 generated questions, where at least 90% can be answered from their cited source.
  - Due dates follow FSRS.
- **Done when:**

* [ ] The daily review queue has worked for one week
* [ ] The plan visibly shifts toward weak topics

### Phase 6: Past-paper intelligence (L)

- **Objective:** learn how each module is actually assessed.
- **Features:**
  - past-paper and test upload, with year and sitting
  - opt-in transcription of scanned pages
  - question segmentation, topic mapping, type and difficulty, and a correction UI
  - the assessment profile page, with drill-down to the questions
  - past questions in practice, and a timed paper mode
  - profile weights feeding planner priority and the tutor's emphasis
- **Tasks:**
  1. Models for past questions.
  2. The vision-LLM transcription path.
  3. Segmentation and classification prompts and schemas, chosen using S2's results.
  4. Profile queries.
  5. `evals/pastpapers`, using your papers labelled by hand.
- **Depends on:** Phases 2, 4 and 5, and S2.
- **Verify:**
  - At least 90% of questions are segmented correctly (number and marks).
  - You agree with at least 80% of the topic mappings.
  - Profile numbers match a count done by hand exactly.
- **Done when:**

* [ ] With 3 or more papers the profile is shown; with fewer it shows the evidence only, with a notice

### Phase 7: Camera companion, opt-in (L)

- **Objective:** supportive, private nudges that are rare and correct.
- **Features:**
  - consent and calibration
  - auto-pause when you're away
  - posture-drift and drowsiness nudges
  - break timing based on your habits
  - the companion mini-window with timer, status and push-to-talk
  - a camera indicator and pause button
  - Screen and Desk/paper modes
- **Tasks:**
  1. The vision worker, built from S1's chosen approach.
  2. `signals.ts`, calibration and per-minute summaries.
  3. `interventions.ts`.
  4. An opt-in tool for recording landmark traces (numbers only) as test fixtures.
  5. A performance governor.
- **Verify:**
  - In fixture tests, upright, slumped and leaning postures are told apart.
  - Blink counts are within ±20% on recorded traces.
  - CPU use on your laptop is measured and acceptable.
  - At most 4 nudges in a one-hour session.
- **Done when:**

* [ ] After 5 real sessions with the camera on, you choose to keep it on

### Phase 8: Profile and insights (M)

- **Objective:** get measurably better at knowing you each week.
- **Features:**
  - an Insights page with measured and estimated labels and sample sizes
  - a weekly review
  - recommendations you can accept or dismiss
  - the planner adapting block length and timing from your profile
- **Tasks:**
  1. Metric jobs.
  2. Recommendation rules.
  3. AI write-ups of the computed statistics.
  4. Revisiting the old `behavior_model.py` heuristics against your real data.
- **Verify:** metric tests on synthetic histories, and no insight shown before its threshold.
- **Done when:**

* [ ] After 3 to 4 weeks of use, at least 3 recommendations strike you as accurate

### Phase 9: Beta readiness (M)

- **Objective:** safe and affordable for other students.
- **Features:**
  - Supabase Auth and hosting
  - onboarding with course-outline import
  - the privacy centre (export and delete)
  - per-user budgets and bring-your-own-key
  - error monitoring and backups
  - a POPIA review
- **Verify:**
  - Tests that try to access another user's data.
  - A restore-from-backup drill.
  - 3 to 5 classmates onboard without help.
- **Done when:**

* [ ] Classmates use it for 2 weeks with no data or privacy incidents

### Phase 10: Later

The MCP connector, Google and Outlook calendar sync, mobile polish (reviews on your phone), better voices or real-time voice, a Tauri wrapper if S1 called for one, and shared class modules (which needs a copyright and privacy review first).

## 5. Immediate next steps

There are four things to do on your side, then Claude Code does Phase 0 in one or two sessions. I haven't changed anything in `C:\StudySensei` yet.

### Step 1: Decide (about 10 minutes)

- [x] Approve the move to a web app, with the PyQt code archived under the tag `v0-pyqt-prototype`
- [ ] Choose the AI provider for development and create an API key. My default is the Anthropic API. Google's Gemini API is a cheaper alternative. Keep the key ready but don't paste it into chat; it goes into `apps/api/.env`
- [ ] Choose the test module and collect its slides, notes, 2 or 3 past papers and the exam date in a folder outside the repo, for example `C:\StudySensei-data\<module code>\`. Confirm it's fine to send this material to the AI provider
- [ ] Tell me whether Docker Desktop is installed

### Step 2: Check your tools (PowerShell)

```powershell
git --version
winget install --id astral-sh.uv -e        # or: scoop install uv
uv python install 3.12
winget install OpenJS.NodeJS.LTS
docker --version                           # Docker Desktop (WSL 2). If missing, we'll use a free Neon database
claude --version                           # Claude Code; see code.claude.com/docs/en/quickstart
```

### Step 3: Put this plan in the repo

Export this doc as Markdown and save it as `C:\StudySensei\docs\PLAN.md`. Claude Code reads it and splits it into the working docs in Phase 0. If you'd rather not do it by hand, I can put it there for you.

### Step 4: Start Claude Code and paste this

Open a terminal in `C:\StudySensei`, run `claude`, and paste:

```text
We are rebuilding StudySensei as described in docs/PLAN.md. Read sections 1, 3, 4 and 6 first.
This session covers Phase 0 only. Start in plan mode and show me the plan before changing files.

1. Confirm `git diff --ignore-cr-at-eol --stat -- . ":!.venv"` is empty (line-ending noise only), then `git restore .`.
2. Create an annotated tag v0-pyqt-prototype on the current HEAD, push it, and create the branch `rebuild`.
3. Untrack .venv/, add .gitattributes (* text=auto eol=lf, *.ps1 eol=crlf) and renormalise.
4. Remove the legacy PyQt code from the tree and write docs/legacy-notes.md with the reusable ideas from PLAN section 1.
5. Scaffold apps/api, apps/web, docker-compose.yml and the root package.json as in PLAN section 3 "Repository structure".
   The API needs /health that checks the database. The web app needs the sidebar shell and a status card for API and database connectivity.
6. Add ruff, mypy, pytest, eslint, prettier, vitest and .github/workflows/ci.yml.
7. Split PLAN.md into docs/PRODUCT.md, docs/ARCHITECTURE.md, docs/ROADMAP.md (each phase as checkbox tasks, one task per session)
   and docs/decisions/0001-web-rebuild.md. Write a CLAUDE.md under 150 lines with commands, layout, conventions and the
   "Rules for CLAUDE.md" from PLAN section 6. Add docs/PROGRESS.md.

Commit in small logical commits on `rebuild`. Finish by running every check and `npm run dev`, then tell me exactly how to verify it.
```

### After Phase 0

- **In this Project chat:** I'll produce three visual directions for the Today, Session and Module screens on a Design canvas (spike S3). You pick one, and that becomes design system v1.
- **In Claude Code:** Phase 1 starts with its first task, the data models and the timer engine.
- **Gate review:** after Phase 1, bring a week of real use back here. We'll check the definition of done and adjust the roadmap before Phase 2.

## 6. Development workflow with Claude and Claude Code

Use Claude Code on your PC for all implementation, and this Project chat for direction, design and gate reviews. The repo's docs are the shared memory between them. Each roadmap checkbox is one Claude Code session and one pull request.

### Who does what

| Where | Used for |
| --- | --- |
| Claude Code on your PC (terminal, desktop app or VS Code), in `C:\StudySensei` | All coding, tests, git, running the app, fixing errors, and keeping the docs updated |
| Claude chat in this StudySensei Project | Product decisions, gate reviews, visual design on a Design canvas, research such as provider or library choices, and revising this plan |
| You | Decisions at gates, using it in real study, supplying materials and keys, testing camera and mic hardware, and merging pull requests |

This chat can reach your folder, but implementation shouldn't happen through it. It goes through a small Linux sandbox with about 300 MB of free disk and no webcam. It can't run your Windows toolchain, and it can't delete files, which breaks git operations. Claude Code running natively has none of these limits.

### How each task runs

1. Start a fresh session and say: *"Read docs/ROADMAP.md and do the next unchecked task in Phase N."*
2. For anything touching several files, use plan mode first (Shift+Tab or `/plan`). Approve or correct the plan before any code is written. Skip it for one-line fixes.
3. For deterministic logic (timer, planner, mastery, metrics, signals), write the tests first. For AI features, add or extend the eval set.
4. Run the checks with `npm run check` (lint, types and tests). Then run the app and look, or use `/verify`.
5. Commit on a branch named `phase-N/<task>`. Tick the checkbox in `ROADMAP.md`, add a 3 to 5 line entry to `docs/PROGRESS.md` (done, decided, next), and open a pull request.
6. For larger pull requests, and anything touching the planner, privacy or auth, run `/code-review`, or have a separate review subagent check it, before you merge.
7. Run `/clear` between tasks. Use `claude --continue` or `/resume` to pick up an unfinished one.

### Keeping context across sessions

| File | Holds | Rule |
| --- | --- | --- |
| `CLAUDE.md` | Commands, repo layout, conventions, non-negotiables | Under 150 lines; prune it when Claude starts ignoring lines |
| `docs/ROADMAP.md` | Phases as checkbox tasks | The single source of truth for status |
| `docs/PROGRESS.md` | Dated session log | Newest first, a few lines each |
| `docs/decisions/NNNN-*.md` | One record per significant decision: context, choice, alternatives, consequences | Written when a decision is made, never edited afterwards |
| `docs/PRODUCT.md`, `docs/ARCHITECTURE.md` | The "what" and the "how" from this plan | Updated in the same pull request as any change that alters them |
| `.claude/rules/` | Conventions that only apply to front-end or back-end files | Loaded only when matching files are opened |
| `.claude/skills/` | Repeatable workflows: `next-task`, `phase-review`, `new-migration` | Added when you've typed the same instructions three times |
| This Project | This plan, plus a short status note updated at each gate | Keeps the chat side current |

### Rules for CLAUDE.md

- Camera frames and audio never leave the browser and are never stored.
- AI output is saved only after passing a Pydantic schema. AI never changes the plan, timers or progress directly.
- Every database query is scoped by `user_id`.
- Timer, planner, mastery, metric and signal code is merged only with unit tests.
- Every number shown to the student is labelled measured or estimated, with its sample size.
- No secrets in git: use `.env` and keep `.env.example` current.
- Finish every task by running `npm run check`, ticking `ROADMAP.md` and adding a `PROGRESS.md` entry.

The last rule should also be enforced: a Stop hook that runs `npm run check` stops a session finishing with failing checks. A line in CLAUDE.md is guidance; a hook is a guarantee. Run `/fewer-permission-prompts`, or allowlist `uv run *`, `npm run *` and `git *` in `.claude/settings.json`, so routine commands don't ask for approval each time.

### Writing good task prompts

| Vague | Specific |
| --- | --- |
| "Build the planner" | "Do Phase 4 task 2: implement `services/planning/plan()` as a pure function with the property tests listed in ROADMAP. No API or UI yet." |
| "Fix the timer" | "After resuming from sleep the session timer shows 2 minutes too many. Reproduce it in a Vitest test first, then fix `timer.ts`." |
| "Make it look better" | "Apply the chosen design direction to the Today page: tokens from `ui/tokens.ts`, no new colours, keep the layout." |

### Cadence

- **Each task:** one focused session.
- **Each phase:** a gate review in this chat. Show what works, check the definition of done, and adjust the next phase.
- **Weekly while you're using it:** five minutes on what you used, what annoyed you and what you skipped. Each item becomes a roadmap task or gets dropped.

## Appendix: evidence, assumptions and sources

### How the audit was done

- **Code and history:** I read all 42 tracked source files and the git history (7 commits). I compared the working tree, which differs only in line endings, and checked which modules are reachable from `main.py`.
- **Runtime test:** I ran the real `MainWindow` headless (Qt offscreen) for 72 s in a clean Python 3.11 environment with MediaPipe 0.10.14 and a simulated camera. The script records whether frames are still being processed every 10 s.
- **Fresh-install test:** I installed today's MediaPipe (1.2.3) to test startup. The import fails with the code's own `ImportError`.
- **Signal tests:** I fed synthetic upright, slumped and leaning landmarks into `vision/posture.py`. I also replayed eye-aspect-ratio traces (15 normal blinks per minute, and one 3-second closure) through `detect_blink`.
- **Not tested:** real webcam video, because the cloud workspace has no camera. Detection quality on live video is therefore unverified. The bugs above are in the maths applied after detection, so they don't depend on the camera.

### Confirmed facts and assumptions

| Item | Status |
| --- | --- |
| Code size, dead code, defects, test results in section 1 | Confirmed by running or reading the code |
| No uncommitted work beyond line endings | Confirmed (`git diff --ignore-cr-at-eol` is empty outside `.venv`) |
| Which Python and MediaPipe versions you originally ran | Unknown; the committed `.venv` contains only pip and setuptools |
| You're the first user and classmates come later | Assumed |
| Chrome or Edge on a Windows laptop with a webcam | Assumed |
| Course materials are mostly English PDF and PPTX files, and some past papers are scans | Assumed; Phase 6 handles both |
| You have push access to `github.com/Josh-Heath123/StudySensei` | Assumed; needed to push the archive tag |
| Docker availability, AI budget, the test module | Open; see Step 1 in section 5 |

### Sources

- [MediaPipe issue #6192: Python 0.10.31 no longer contains `mediapipe.solutions`](https://github.com/google-ai-edge/mediapipe/issues/6192)
- [Claude Code: best practices](https://code.claude.com/docs/en/best-practices) (plan mode, CLAUDE.md, hooks)
- [Claude Code: extending Claude Code](https://code.claude.com/docs/en/features-overview) (CLAUDE.md versus rules, skills and hooks)
- [Claude Code: commands](https://code.claude.com/docs/en/commands) (`/plan`, `/init`, `/verify`, `/fewer-permission-prompts`)
- [Claude Code: quickstart](https://code.claude.com/docs/en/quickstart)
