# 0012: Visual direction C, "Glass"

- **Date:** 2026-11-18
- **Status:** Accepted. Supersedes the 13 Nov 2026 choice of direction B "Planner" (ROADMAP spike S3; the Planner spec
  is archived at `docs/archive/DESIGN-planner.md`).

## Context

- On 13 Nov the owner chose direction B "Planner" from three directions: ink on paper, flat and square, Space Grotesk
  headings, the module's colour as the one loud fill. It was built in PR #9 and has carried every screen since.
- The repository is now a public showcase, and the app is used daily. Planner reads as a strong document but a hard
  tool: 2 px ink borders everywhere, no depth to separate what floats from what's read, and one font pairing that
  felt heavy at the session timer's size.
- On 18 Nov the owner chose direction C, "Glass", from a reference image: a soft cloudy canvas, calm solid surfaces,
  translucent chrome, Galactic Violet for action and a Bubblegum Pink → violet gradient as the signature. The
  reference's hex labels didn't match its colours, so the palette was sampled from the image itself.

## Decision

1. **Direction C "Glass" replaces Planner** everywhere in the web app. `docs/DESIGN.md` is its spec: tokens, type,
   components, glass rules, motion and accessibility.
2. **One source of tokens:** CSS variables in `apps/web/src/index.css`, mapped into Tailwind v4 with `@theme`; no
   one-off values in components.
3. **Light and dark themes,** with an Appearance setting (System by default, Light, Dark) stored in `localStorage` and
   applied as `data-theme` on `<html>` by an inline script before the first paint.
4. **Glass is selective:** only floating chrome (navigation, dialogs, menus, toasts, floating toolbars, the session's
   control bar). Content, forms, lists, tables, the topic tree and the viewer's page stay solid.
5. **Legibility is enforced, not hoped for:** text never sits directly on the gradient; glass that can float over
   anything uses a stronger tint (`glass-strong`, 0.86) than the recipe's 0.62 / 0.55, because the recipe fails 4.5:1
   for muted text over dark content; a Vitest test computes the contrast of every text and control pair, including
   glass over its worst-case backdrop, in both themes.
6. **Inter variable only.** Space Grotesk is removed; display and timer type use light Inter weights.
7. **Module colours are unchanged:** the eight swatches keep their meaning (a fill behind dark text) and pass on both
   canvases, so no data migration is needed.

## Alternatives

- **Keep Planner and add a dark mode:** cheaper, but the owner chose C, and Planner's heavy borders and flat depth don't
  translate well to dark.
- **Glass everywhere:** visually striking in a reference image, but long text, tables and forms lose contrast and
  calm; the rule keeps glass to what floats.
- **The recipe's tint for all glass:** fails WCAG for muted text over dark content and bright module colours (computed
  in `tokens.test.ts`); the stronger tint keeps the look with legible text.
- **A theme library or CSS-in-JS:** unnecessary; CSS variables and one `data-theme` attribute cover both themes.

## Consequences

- Every screen was restyled in one PR; behaviour, routes, API calls and test intent are unchanged. A few tests that
  asserted Planner class names now assert the state they stood for.
- The README's banners, social preview and screenshots are regenerated in the new identity, in light and dark.
- `tokens.test.ts` must pass for any colour change, so a regression in contrast fails CI.
- Space Grotesk's 12 font files (about 137 kB) leave the build; the app CSS grows by about 13 kB (3 kB gzipped)
  and the main script by about 18 kB (5 kB gzipped) for the themes, glass and the new states.
