# 0002: Free-tier AI providers behind one OpenAI-compatible adapter

- **Date:** 2026-11-12
- **Status:** Accepted

## Context

PLAN.md §3 originally proposed Anthropic (Haiku-class fast tier, Sonnet-class deep tier) with a second
OpenAI-compatible adapter. The product owner confirmed that **AI must cost nothing** during development and early use.

## Decision

- **Primary:** the Google Gemini API free tier.
  - **Flash** for the tutor, topic maps and scanned-paper transcription.
  - **Flash-Lite** for bulk classification, such as past-paper question types and chunk-to-topic linking.
- **Fallback:** the Groq free tier.
- **Optional:** local Ollama.
- **One adapter:** all providers go through a single OpenAI-compatible adapter in `apps/api/app/ai/`.
  `LLMClient.complete(tier, messages, schema=None, stream=False)` stays the only interface, and settings map tiers to provider and model.
- **No Anthropic adapter for now.** It can be added later behind the same interface.
- **No personal data in prompts.** Free-tier prompts may be used by the provider to improve its models, so:
  - only course material and the student's study questions are sent
  - no names, student numbers, emails or reflections
  - for the COS330 test module, the student's own submissions are excluded from AI processing entirely

## Alternatives considered

| Option | Why not |
| --- | --- |
| Anthropic API (paid) | Costs money; a paid key isn't available |
| OpenAI API (paid) | Same |
| LiteLLM / LangChain | A heavy dependency for about 200 lines of adapter code we can own |
| Ollama only | Too slow and too weak on a student laptop for topic maps and long slide decks |

## Consequences

- Rate limits on free tiers are the main constraint:
  - the worker must back off and retry
  - processing each file once (by SHA-256 hash) matters more
  - Groq fallback is automatic on 429s
- `ai_usage` still logs tokens per call (cost is estimated as 0, but usage is visible).
- The privacy page must state that the free-tier provider may use prompts, and what is never sent.
- Evals (`apps/api/evals/`) must run before any switch of model or provider.

## Update, 2026-11-17: model IDs, limits and interface (Phase 2, LLM client)

Added when the client was built, at the product owner's request. The decision above stands. These are the specifics
it left open.

- **Model IDs** (the Gemini pricing page lists both as free on 2026-11-17; Groq's from its models and deprecations pages):

  | Role | Order |
  | --- | --- |
  | `smart` (was "Flash") | `gemini-3.8-flash` → Groq `openai/gpt-oss-120b` → Groq `qwen/qwen3.8-27b` (reads images) |
  | `bulk` (was "Flash-Lite") | `gemini-3.5-flash-lite` → Groq `openai/gpt-oss-20b` |

  Optional Ollama (`OLLAMA_MODEL`) is tried last in both. Roles are lists in config (`AI_SMART`, `AI_BULK`), not code.
- **Free-tier limits.** Google has stopped publishing free-tier numbers, so these are the per-project quotas that AI
  Studio and 429 replies reported (Sept–Nov 2026):
  - `gemini-3.8-flash`: 5 RPM, **20 RPD**
  - `gemini-3.5-flash-lite`: 15 RPM, 500 RPD
  - Gemini quotas reset at midnight Pacific
  - Groq `openai/gpt-oss-120b`, `openai/gpt-oss-20b` and `qwen/qwen3.8-27b`: 30 RPM, 1,000 RPD, 8K TPM; 200K TPD for gpt-oss
  - Groq's Llama models left the free and developer tiers on 2026-08-16

  Daily budgets are set about 10 % under these (18, 450, 900, 900, 900). Re-check them with `uv run python -m app.ai.ping`
  and the providers' limit pages, and update `AI_DAILY_BUDGET` if they change.
- **Consequence:** 20 Flash requests a day is far below what PLAN.md assumed. Topic maps and the tutor will often run
  on Groq's gpt-oss-120b, so evals should cover both models.
- **Interface:** `LLMClient.complete(tier, messages, schema=None, stream=False)` became
  `complete_text(role, messages, *, purpose, user_id)` and `complete_json(role, messages, Schema, *, purpose, user_id)`
  (one repair attempt). Streaming arrives with the tutor (Phase 3).
- **Privacy is enforced in code:** course text reaches prompts only through `app/ai/sources.py`, which filters out
  materials with `allow_ai` off and never sends file names.

## Update, 2026-11-17 (later): routes rebalanced, vision role

Added at the product owner's request after the first real pings. Gemini 3.8 Flash replaces neither "Flash" role any
more; the free tier's daily limits and latency decide the order.

- **Findings:**
  - `gemini-3.8-flash` timed out after 30 s twice (with no thinking level set, and at `low`), and its free tier allows
    about 20 requests a day.
  - `gemini-3.5-flash-lite` answered in 1–10 s and allows about 500 a day.
  - Groq's gpt-oss allows about 1,000 a day.
- **New routes** (config defaults, each with its `reasoning_effort`):

  | Role | Order |
  | --- | --- |
  | `smart` (tutor, topic maps) | Groq `openai/gpt-oss-120b` (low) → `gemini-3.5-flash-lite` (low) → `gemini-3.8-flash` (low), last resort |
  | `bulk` (classification, tagging) | `gemini-3.5-flash-lite` (minimal) → Groq `openai/gpt-oss-20b` (low) |
  | `vision` (any message with an image: scanned pages, figure slides) | `gemini-3.5-flash-lite` → Groq `qwen/qwen3.8-27b` → `gemini-3.8-flash`, all low |

- **Vision:** every model in it accepts images, per the provider docs (both Gemini model pages list image input;
  Groq's Qwen takes 3 images per request). It replaces the earlier per-model vision flag, and Ollama isn't added to it.
- **Budgets unchanged** (18, 450, 900, 900, 900 requests a day): Google still publishes no free-tier numbers, and Groq's
  page shows the same 1K RPD. gpt-oss-120b's 200K tokens a day may now bind first, which shows up as 429s that fall
  through to Flash-Lite.
- **Consequence:** the tutor and topic maps will mostly run on gpt-oss-120b, so its evals matter most. The earlier
  note that "Flash" does topic maps and scanned pages no longer holds.
