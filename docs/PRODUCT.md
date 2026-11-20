# Product

The "what" and the "why". Change it in the same PR as any change that alters it. Source: [the original plan](archive/PLAN.md) §2 (12 Nov 2026).

## Statement

_StudySensei tells you what to study next and why, helps you while you study it, and gets more accurate about you every
week, using your own course material and your own study record._

It is a study planner and tutor built around one loop: **know what's coming → decide what to study → study with
support → check understanding → adjust.** Modules, materials, the topic map, past-paper evidence, assessments and mastery
form a shared context that every feature reads from. New materials and assessments can arrive at any time, and the next plan
reflects them. Camera and voice support the study session. They are not the product.

## The student's journey

1. **Onboarding (~10 min):**
   - add modules
   - upload a course outline and confirm the proposed assessments, dates and topics
   - set weekly available hours and get a first plan
2. **Building module knowledge:**
   - upload slides, notes, tutorials and past papers, and watch their processing status
   - review the proposed topic map (confirm, rename, merge, delete)
   - once past papers are processed, the module shows its assessment profile
3. **Today:** the next study block and _why it was chosen_ (for example, "Thermodynamics: entropy. Exam in 12 days. Seen in 4 of 5
   past papers. Last practice score 62 %."), plus reviews due and upcoming deadlines.
4. **Study session:**
   - opt in to the camera and microphone per session
   - a timer with planned breaks
   - a side panel with the topic's materials, a tutor that cites sources, and "quiz me"
   - rare, evidence-based nudges
   - ends with a 20-second reflection: focus 1–5, what was covered, confidence per topic
5. **Practice and review:** spaced-repetition reviews, past-paper questions by topic, and a timed paper mode in the final week.
6. **Weekly review:** hours planned vs studied, mastery trends, and what changes next week. Every insight is labelled
   _measured_ or _estimated_, with its evidence.

## How features share context

| Shared data                                        | Produced by                             | Used by                                                      |
| -------------------------------------------------- | --------------------------------------- | ------------------------------------------------------------ |
| Topic map (per module)                             | Document processing + your edits        | Tutor search scope, question generation, plan units, mastery |
| Past-paper profile                                 | Past-paper analysis                     | Plan priority, study method, practice style, tutor emphasis  |
| Topic mastery                                      | Practice results, reviews, self-ratings | Plan time allocation, review scheduling, struggle detection  |
| Session log + reflections                          | Study sessions                          | Student profile, realistic plan capacity                     |
| Camera signals (opt-in, per-minute summaries only) | In-browser vision                       | Break timing, posture nudges, "estimated" profile items      |
| Assessments + availability                         | You                                     | Hard limits on the plan                                      |

## Student profile: measured vs estimated

| Item                                | Derived from                                                                 | Label                | Shown after                      |
| ----------------------------------- | ---------------------------------------------------------------------------- | -------------------- | -------------------------------- |
| Usual session length before a break | Median active minutes before the first unplanned pause, absence or early end | Measured             | 5 sessions                       |
| Consistency                         | Days studied per week; planned blocks completed vs skipped                   | Measured             | 1 week                           |
| Break habits                        | Break count and length vs plan                                               | Measured             | 5 sessions                       |
| Most productive times               | Completion, self-rated focus and accuracy by time of day                     | Estimated            | 10 sessions across 3+ time bands |
| Topic mastery                       | FSRS memory model + practice accuracy + self-confidence                      | Estimated            | 3 attempts per topic             |
| Methods that work for you           | Mastery gained per minute by method and topic type                           | Estimated            | ~5 sessions per method           |
| Time away from desk                 | Face present or absent                                                       | Measured (camera on) | 3 camera sessions                |
| Posture drift                       | Minutes lower, closer or more tilted than your baseline                      | Estimated            | 3 camera sessions                |

**Rule:** nothing is shown before its minimum evidence, and every insight states what it's based on. Until then,
StudySensei uses general evidence-based defaults (such as 25–50 minute blocks) and says so.

## Academic context per module

- **Topics:**
  - a tree with learning objectives, linked to the pages and slides where each is taught
  - user edits always win over AI suggestions
- **Assessments:** date, weight, the topics they cover and their status. Assignments are tasks with deadlines.
- **Past-paper evidence:** each question has its paper, number, marks, topics, type (recall, explain, apply, calculate, essay) and estimated difficulty.
- **Assessment profile:**
  - for example, "Entropy: in 4 of 5 papers, 17 % of marks on average, mostly application"
  - forward-looking statements are labelled _Likely emphasis (estimate, based on N papers)_
  - never "will be in the exam"
  - hidden with fewer than 3 papers

## What AI does vs what ordinary code does

| Responsibility                                                        | Done by                                                                      |
| --------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Text extraction, chunking, search                                     | Ordinary code + local embeddings                                             |
| Proposing topic maps; segmenting and classifying past-paper questions | AI, validated by schema, then reviewed by you                                |
| Explaining, answering, generating practice                            | AI                                                                           |
| Marking short answers                                                 | AI with the reference answer and source shown; self-marking always available |
| Assessment-profile statistics                                         | Ordinary code (exact counts)                                                 |
| Scheduling, re-planning, feasibility                                  | Ordinary code (a tested planner)                                             |
| Study method per block                                                | Ordinary code: a rules table, and code-written text from computed facts (no AI in v1) |
| Timers, breaks, reminders, progress                                   | Ordinary code                                                                |
| Camera signals and nudges                                             | Ordinary code in the browser                                                 |
| Weekly insight write-up                                               | AI writes up numbers that code computed; it never invents a number           |

## Features beyond the original brief

1. A 20-second end-of-session reflection: the only real ground truth for focus.
2. A practice engine with FSRS spaced repetition.
3. Citations on every tutor answer (slide or page), one click to check.
4. Weekly availability and a feasibility check ("you need 14 h but have 9 h, so these topics get cut").
5. Course outline import to create assessments and their scope.
6. An ICS calendar feed.
7. A small always-on-top companion window (timer, status, push-to-talk).
8. A privacy centre: what's collected, retention, export and delete.
9. A per-user AI budget and usage log.
10. Later: an MCP connector.

## Positions taken

- **No gaze-based "focus %".** A webcam can't see focus, and looking down at a textbook isn't distraction. Use time away,
  completed blocks and self-rated focus instead.
- **No emotion detection.** It's inaccurate, sensitive and can't be acted on.
- **The microphone is push-to-talk only.** No always-on listening.
- **Voice is two-step** (speech-to-text → streamed answer → text-to-speech) before any real-time speech-to-speech.
- **Voice is on-device only** (decision 0015). Audio never leaves the browser, so voice needs a browser with
  on-device Web Speech: today that's Chrome or Edge, with the speech pack installed (the tutor offers to download it).
  Other browsers, and Chrome or Edge without the pack, keep typing. "Read aloud" uses only the device's own voices.
- **No exam prediction.** Show evidence and estimated emphasis from 3 or more papers only.
- **Rules and plain statistics before any ML.** ML waits until there are hundreds of sessions.
- **Honest posture scope.** The camera can tell you're lower, closer or more tilted than your own baseline. It can't judge your spine.
- **AI costs nothing** (decision 0002): free tiers only, and no personal data in prompts.
