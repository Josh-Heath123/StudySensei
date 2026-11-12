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
  - for the COS330 test module, the student's own `u23541475_*` submissions are excluded from AI processing entirely

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
