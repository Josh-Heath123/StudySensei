# Authorship and development record

Recorded 18 Nov 2026.

## Owner

- **Joshua Heath**, GitHub [Josh-Heath123](https://github.com/Josh-Heath123).
- Commit emails in the history (as of 18 Nov 2026):
  - `joshuaheath004@gmail.com` (personal): 187 commits;
  - `u23541475@tuks.co.za` (university address): 7 commits, from 19 to 26 Jan 2026.

## Origin

- **19 Jan 2026:** the first commit, the repository's initial commit made on GitHub.
- **Jan 2026 onwards:** a PyQt desktop prototype (webcam focus tracking). It's archived at the git tag
  `v0-pyqt-prototype`, and its reusable ideas are in `docs/legacy-notes.md`.
- **From Nov 2026:** the web rebuild (React and FastAPI), decided in
  [ADR 0001](decisions/0001-web-rebuild.md). Phase 0 merged on 12 Nov 2026 (PR #1). See `CHANGELOG.md` for the phases
  since.

## Status

A personal project, built on the owner's own time and equipment. It is not coursework and has never been submitted for
marks.

## How it's made, and who controls it

- **Product and decisions:** the owner sets the product (`docs/PRODUCT.md`), the plan and the roadmap
  (`docs/ROADMAP.md`), and makes every product decision. Decisions are recorded in `docs/decisions/`.
- **Implementation is AI-assisted:**
  - Claude Code writes code to the owner's task specifications.
  - A Claude Project chat drafts those specifications and reviews the results.
  - Both act only on the owner's instructions.
- **Merging:** every change reaches `main` only through a pull request that the owner merges after CI passes. AI
  features are tested on the owner's own data before merging.
- **The record of that control:**
  - the git history and the pull requests on GitHub. As of 18 Nov 2026, the 29 merge commits and the initial commit,
    made on GitHub, carry GitHub's verified signature; the owner's own commits are not yet signed
    (`.github/rulesets/main-signed.json` will require signing once it's set up);
  - the decisions in `docs/decisions/`;
  - the session log in `docs/PROGRESS.md`;
  - the evals in `apps/api/evals/`.

## AI tools' terms

Claude is used under Anthropic's [Consumer Terms of Service](https://www.anthropic.com/legal/consumer-terms) (effective
8 Oct 2025), which state: "Subject to your compliance with our Terms, we assign to you all of our right, title, and
interest—if any—in Outputs."

## The app's own AI

At runtime, StudySensei calls Gemini and Groq (free tiers, `docs/decisions/0002-free-ai-providers.md`) to build topic
maps from course material. That AI doesn't write StudySensei's code.

## Not in the repository

- Course materials (the COS330 slides, notes and past papers) are never committed.
- The evals (`apps/api/evals/`) hold only queries, material titles, page numbers and topic names, never course text.

This document records facts about how StudySensei is made. It is not legal advice.
