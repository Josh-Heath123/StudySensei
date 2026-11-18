# Legacy notes: the PyQt prototype

The PyQt5 + MediaPipe desktop prototype (Jan 2026, about 7,300 lines) was removed from the tree in Phase 0.
It is archived at the git tag `v0-pyqt-prototype` (commit `1d55ce1`).

```bash
git show v0-pyqt-prototype:vision/posture.py      # view one file
git ls-tree -r --name-only v0-pyqt-prototype      # list everything
git worktree add ../studysensei-v0 v0-pyqt-prototype   # check it all out side by side
```

We carry forward **ideas, not code**. The measured parts were broken (see "Bugs not to repeat").

## 1. Landmark sets (MediaPipe)

FaceMesh with iris (478 points), used by `vision/gaze.py` and `utils/constants.py`:

| Purpose | Left | Right |
| --- | --- | --- |
| Eye corners (outer, inner) | 33, 133 | 362, 263 |
| Iris centre + boundary | 468, 469–472 | 473, 474–477 |
| EAR points (outer, top1, top2, inner, bottom1, bottom2) | 33, 160, 158, 133, 153, 144 | 362, 385, 387, 263, 380, 373 |

Pose (33 points), used by `vision/posture.py`: nose 0, ears 7/8, shoulders 11/12, elbows 13/14, wrists 15/16, hips 23/24.

In the rebuild, FaceLandmarker gives `eyeBlinkLeft/Right` blendshapes and a facial transformation matrix,
so EAR and iris-centring maths are no longer needed. The index sets are still useful for debug overlays
and recorded traces.

## 2. Posture: ideas worth keeping

- **Visibility gating.** Skip a metric when any landmark it uses has `visibility < 0.5`, or the projected point
  falls outside the frame. Return "unknown", not a bad score.
- **Minimum-size guards.** Ignore frames where shoulder width < 10 px or eye width < 8 px (the subject is too far away or the detection is bad).
- **Signals chosen:** shoulder tilt (shoulder line vs horizontal), head drop (ears or nose relative to the shoulder line),
  and distance proxy (face or shoulder width).
- **Calibration concept:** a stored baseline per user (`shoulder_ear_angle`, `forward_head_ratio`, `neck_angle`,
  `shoulder_roll`, timestamp). The rebuild compares against a 5-second calibration and measures
  **deviation from the student's own baseline**, not fixed "ideal" angles.
- **Sustained-before-alert.** The slouch alert fired only after 30 s of continuous slouching. The rebuild uses 3 minutes,
  at most once every 15 minutes, and never in the first 10 minutes.

## 3. Session data schema (SQLite → Postgres)

From `analytics/session_store.py`, the shape to carry into `study_sessions` / `session_minutes`:

- `sessions`: started_at, ended_at, total_duration_sec, avg_focus_score, avg_posture_score, total_blinks,
  total_slouch_alerts, focus_mean / std / trend / volatility, metadata_json
- `time_series`: session_id, ts, focus_score, posture_score, gaze_confidence, blink_detected, slouching,
  text_neck, fps; indexed on (session_id, ts)
- `behavior_patterns`: session_id, pattern_type, start_time, end_time, metadata_json

Rebuild changes:
- per-minute summaries instead of per-frame rows
- presence and head-away ratios instead of "focus score"
- UUID keys and `user_id` scoping

## 4. Break heuristics (`analytics/break_logic.py`)

The structure to port into `session-engine/interventions.ts`:

- **Throttle.** No suggestion within 20 min of the last suggestion, or of the last break taken.
- **Reasons list.** Each rule appends a human-readable reason, and the message joins them, for example
  "You've been studying for over 25 minutes, and focus is declining rapidly. Consider a short break."
- **Rules:**
  - 25 min of work
  - ≥ 20 % drop from the session baseline
  - a steep decline rate
  - ≥ 15 min in a "fatigue" phase
- **Output:** `{message, urgency, recommended_duration_sec: 300}`.

In the rebuild, the plan drives break timing, adjusted by the measured session length. "Focus score" inputs are
replaced by presence, self-rating and practice signals.

## 5. Session phases and patterns (revisit in Phase 8)

From `analytics/behavior_model.py`. Only tune these against real data.

- **Phases:**
  - warm-up: first 5 min
  - peak: mean ≥ 75 and std < 10 over the last 20 points
  - fatigue: linear trend < −0.1 and mean < 60
  - recovery: trend > +0.1 after fatigue
- **Patterns:**
  - morning focus: 08–11 h, mean > 75
  - afternoon slump: 14–16 h, mean < 60
  - Pomodoro rhythm: low-focus dips 20–30 min apart, at least twice

## 6. Architecture idea

The engine produced signals and the UI subscribed to them (Qt signals → widgets). Keep this split in TypeScript:
the vision worker emits signals, `signals.ts` turns them into pure-function features, and `interventions.ts` and the UI subscribe.
Move computer vision **off the UI thread** (the prototype froze the UI because it ran inside a `QTimer`).

## 7. Visual: focus ring and palette

`ui/focus_circle_widget.py`:
- thin (3 px) ring, starting at 12 o'clock and filling clockwise
- 20 %-white track and a linear gradient from **#007AFF → #5856D6**
- 400 ms ease-out-cubic animation for both the number and the arc
- a soft pulsing glow (opacity 0.3–0.7) above 70
- 48 pt semibold percentage with a status word below it

Palette (`styles/*.qss`):

| Role | Value |
| --- | --- |
| Accent | #007AFF (hover #0A84FF, pressed #0051D5), secondary #5856D6 |
| Dark surfaces | #000000 background, rgba(28, 28, 30, 0.3–0.95) panels |
| Dark text / lines | white at 0.9 / 0.8 / 0.6 / 0.3 opacity, borders 0.05–0.2 |
| Light theme | #f5f5f7 background, #ffffff cards, #1d1d1f text, #86868b secondary, #d2d2d7 borders |

This is input for the design system (spike S3), not a final decision.

## 8. Bugs not to repeat

These were confirmed by running the prototype ([the original plan](archive/PLAN.md) §1). Each should have a regression test in the rebuild.

1. **Unpinned dependencies.** `mediapipe>=0.10.0` resolved to a release without `mp.solutions`. Pin and lock everything.
2. **Hidden lifecycle side effects.** A "memory manager" released the camera and stopped the timer every 60 s while the UI
   still said "running". Resource ownership must be explicit and owned by the session.
3. **Inverted angle maths.** `abs(90 - angle)` made perfect alignment read ~90°, so upright and slouched both scored 38.8.
   Test signal functions on synthetic upright / slumped / leaning fixtures.
4. **Blink detection without edge detection.** A 10-frame median filtered out real blinks, and every closed frame counted
   as a blink (one 3 s closure counted as 29 blinks). Count rising edges with hysteresis.
5. **Typo in eye width.** The right-eye width used `right_eye_inner[1] - right_eye_inner[1]` (always 0 vertically).
6. **Wrong chart time base.** The X-axis used `timestamp % 60`, and sampling ran 5× faster than intended.
7. **Calibration saved but never used.** Check that stored baselines actually feed the computation.
8. **Gaze ≠ focus.** Looking down at notes scored as "distracted". Desk/paper mode must treat looking down as normal.
9. **Debug noise left in.** There were 222 `print` calls and coloured debug borders. Use a logger and no debug UI in commits.
