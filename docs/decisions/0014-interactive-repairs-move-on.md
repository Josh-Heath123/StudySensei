# 0014: An interactive JSON repair that's turned away moves to the next model, afresh

- **Date:** 2026-11-19
- **Status:** Accepted. Amends 0013 (the interactive rule) for JSON replies; background jobs are unchanged.

## Context

0013 says interactive calls never wait: a 429 or 503 moves straight on to the next model. That held for the first
attempt, but not for the one repair `complete_json` allows. In the live review of #38, a quiz's first reply didn't
validate, and its repair hit Groq's per-minute limit. The repair then went on through the fallbacks carrying Groq's
invalid reply, so a second model was asked to fix the first one's JSON. After that the quiz failed.

That hand-over breaks 0013's other rule, too: two models' output is never stitched together.

## Decision

For interactive JSON calls (`complete_json(..., interactive=True)`, used by "Quiz me"):

1. **The repair goes only to the model that wrote the reply.** It's that model's own JSON being fixed.
2. **When that model turns the repair away**, the next models get the original prompt afresh. Turned away means a
   429, 503 or 413, a timeout or lost connection, a cooldown or a spent budget (`AIUnavailable.exhausted`). The
   invalid reply is never passed on, and the fresh call has its own repair.
3. **A 5xx on the repair still fails at once** (0013), and a reply still invalid after its repair is
   `AIInvalidOutput`.
4. **Background calls are unchanged** (0007, 0008): a short wait on the same model, then the repair continues
   through the fallbacks.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Wait for Groq's minute to pass | A student is waiting; 0013 rules out waits for interactive calls |
| Send the repair (with the first model's reply) to the next model | Stitches two models' output, and the second model fixes JSON it didn't write |
| Treat a turned-away repair as a failure | The next model could well answer; the student would see an error they didn't need to |

## Consequences

- A busy primary costs at most one extra fresh call on the next model, never a wait.
- Tests (`tests/ai/test_interactive_repair.py`) cover 429, 503 and 413 on the repair, the repair going to the same
  model, a fresh call's own repair, a 5xx failing at once, every model busy, and background calls keeping their
  behaviour.
