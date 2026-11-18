# StudySensei design system v1: "Planner"

Chosen 13 Nov 2026 from three directions (canvas: https://claude.ai/artifact/VRuYrxfbGF65SRyfiAfqyd, row B).
Crisp black on white, bold headings, and each module's own colour used as a solid fill. The day is something you can see.
This file is the spec. The tokens live in `apps/web/src/index.css` and the components in `apps/web/src/ui/`.

## Principles

1. **Ink and paper first.** Almost everything is black (#111111) on white. Colour is rare and means something: a module's colour, or a status.
2. **One loud action per screen.** The single most important action (Start session, Start now) uses the module-colour button. Everything else is ink or outline.
3. **Time is drawn, not listed.** Show the day as a timeline, deadlines as countdowns and focus/break as a segmented bar. Readers should see the shape of time before they read a number.
4. **Flat and square.** No shadows, gradients or glass. Corners are small (4–6 px). Hierarchy comes from borders.
5. **Honest numbers.** Every metric carries a *Measured* or *Estimated* tag and its basis. Never use colour alone to carry meaning: overdue items say "Overdue".

## Tokens

### Colour

| Token | Value | Use |
| --- | --- | --- |
| `ink` | `#111111` | Text, primary buttons, strong borders, selected tabs |
| `paper` | `#FFFFFF` | Page and card background |
| `muted` | `#5B5B5B` | Secondary text (6.8:1 on paper) |
| `line` | `#E8E8E8` | Dividers, timeline grid, secondary card borders |
| `surface` | `#F0F0F0` | Quiet buttons, tracks of progress bars |
| `danger` | `#C4161C` | Overdue, destructive actions (6.0:1 on paper) |
| `warning` | `#9A5B00` | "Due soon" text (5.3:1 on paper) |
| `success` | `#1E7B46` | Completed states (5.3:1 on paper) |
| `focus` | `#111111` | Focus ring: 2 px outline, 2 px offset |

**Module colours.** These are the only saturated colours in the app. Each module picks one, and it's always used as a **fill behind ink text** (never as text on white), so every swatch must give at least 4.5:1 with `#111111`:

| Name | Value |
| --- | --- |
| Orange (default) | `#FF7A3D` |
| Yellow | `#FFD23F` |
| Mint | `#5EE0B0` |
| Blue | `#8FB8FF` |
| Lilac | `#C9A7FF` |
| Pink | `#FF8FA3` |
| Lime | `#B8E05E` |
| Cyan | `#6ED3E8` |

The current Modules form offers darker iOS-style colours (`#007AFF`, `#5856D6`, …), which fail with ink text. Replace the swatches with the list above. Add a migration that maps each existing module colour to the nearest new swatch, and update the custom-colour picker to reject colours below 4.5:1 against ink.

### Type

Self-host the fonts with `@fontsource-variable/inter` and `@fontsource/space-grotesk` (weights 500 and 700). Make no calls to Google Fonts: it's faster, works offline and leaks nothing.

| Role | Font | Size / line-height | Weight | Tracking |
| --- | --- | --- | --- | --- |
| Display (page date, hero) | Space Grotesk | 56 / 1.0 | 700 | −0.03em |
| Timer numerals | Space Grotesk, tabular | 128 / 0.9 | 700 | −0.04em |
| Countdown numerals | Space Grotesk | 40 / 1.0 | 700 | 0 |
| H1 | Space Grotesk | 40 / 1.1 | 700 | −0.02em |
| H2 (card hero) | Space Grotesk | 30 / 1.1 | 700 | −0.01em |
| H3 (section) | Space Grotesk | 20 / 1.2 | 700 | 0 |
| Body | Inter | 15 / 1.5 | 400 | 0 |
| Body strong | Inter | 15 / 1.5 | 600 | 0 |
| Small | Inter | 13 / 1.4 | 400 | 0 |
| Label (eyebrow) | Inter, uppercase | 12 / 1.2 | 600 | 0.08em |

Use tabular numerals (`font-variant-numeric: tabular-nums`) for every time, date and count that updates.

### Space, radius and borders

- **Spacing scale (px):** 4, 8, 12, 16, 20, 24, 32, 40, 56. Page padding is 40 on desktop and 20 below 640 px.
- **Radius:** 4 for controls, chips and timeline blocks; 6 for cards. Nothing rounder, and no pills.
- **Borders:**
  - Primary containers (the tutor panel, the key card on a page): 2 px `ink`.
  - Secondary cards: 2 px `line`.
  - Dividers and grid lines: 1 px `line`.
- **No shadows anywhere.**

### Motion

150 ms ease-out on hover and press. The timer ring and progress fills animate their width only. Respect `prefers-reduced-motion`.

## Components

| Component | Spec |
| --- | --- |
| **Button: primary** | `ink` background, `paper` text, 15/600, radius 4, padding 12×22, min-height 44 |
| **Button: module** | Module-colour background, `ink` text. Only for the one main action on a screen |
| **Button: outline** | `paper` background, 2 px `ink` border, `ink` text |
| **Button: quiet** | `surface` background, `ink` text, 13/500, min-height 36. For suggestion chips like "Explain differently" |
| **Button: on dark** | Transparent, 1 px `#737373` border, `paper` text. Used inside the ink "Next up" card |
| **Top navigation** | Replaces the sidebar. The bar is at least 64 px tall with a 2 px `ink` bottom border. Left: the *StudySensei* wordmark (Space Grotesk 20/700). Then links (14 px, `muted`); the active link is `ink` 600 with a 3 px module-colour underline. Wraps on small screens |
| **Page header** | Label eyebrow (e.g. FRIDAY), then the display title (e.g. 13 November). Optional countdown tiles on the right |
| **Countdown tile** | Big number (Space Grotesk 40) + "days to Assignment 2" (13/600) + module and date (13, `muted`). The nearest deadline gets a 2 px `ink` border, others 2 px `line` |
| **Next-up card** | `ink` background, `paper` text, radius 6, padding 28. Eyebrow (12/600, `#D4D4D4`), H2 title, one-line reason, then module button + on-dark button |
| **Day timeline** | Hour rows 52 px tall with 1 px `line` top borders and time labels (12, `muted`, tabular). Blocks are module-colour fills, radius 4, with `ink` text "10:30 · Topic" and "Method · 50 min". Review blocks use a 2 px dashed `ink` outline instead of a fill. A NOW marker is a 2 px `ink` line with a small label |
| **Segmented progress** | Focus segments `ink`, breaks `line`, the elapsed part filled with the module colour, labels underneath (12, `muted`) |
| **Tabs** | Segmented and full-width inside a 2 px `ink` container. The selected tab is inverted (`ink` background, `paper` text), and dividers are 2 px `ink`. Use real `role="tab"` + `aria-selected` |
| **Module badge** | Module-colour fill, `ink` text 13/600, radius 4, padding 4×10 |
| **Citation chip** | 1 px `ink` border, 12/600, radius 3, padding 3×8, e.g. "S1 CH02 slides". It's a link to the source page |
| **Card** | `paper` background, 2 px `line` border (or `ink` for the main one), radius 6, padding 20–24 |
| **Tag: measured/estimated** | 12 px `muted` text, no fill |
| **Form fields** | 15 px, 2 px `line` border, radius 4, min-height 44. Focus: 2 px `ink` border plus the focus ring. Every input has a real `<label>` (visually hidden is fine) |
| **Empty state** | One sentence plus one action. No illustration |

## Screens

- **Today:** the page header with countdown tiles. Below it, the day timeline (about 60% width) and a right column: next-up card, reviews due, and the "this week" bars (Measured).
- **Study session:** a header with ← Today, the module badge, the topic title, the camera status and End session (primary). A 6 px progress line under the header. Left: the eyebrow, the timer numerals, the segmented focus/break bar, Pause (primary) and Break now (outline), and materials links. Right: the tutor panel (2 px `ink` border, segmented tabs, answer with citation chips, quiet suggestion buttons, input row with push-to-talk).
- **Modules and module detail:** the same header pattern. Assessments, Tasks and Topics as segmented tabs. Lists are rows with 1 px `line` dividers, and overdue text uses `danger` with the word "Overdue".

## Not in v1

Dark mode (direction C can become it later), drag-and-drop on the timeline, and charts beyond the weekly bars.

## Implementation notes (Tailwind v4 + shadcn)

- Define the tokens with `@theme` in `index.css` (`--color-ink`, `--color-paper`, `--color-muted`, `--color-line`, `--color-surface`, `--color-danger`, `--color-warning`, `--color-success`, `--font-sans`, `--font-display`).
- Map the shadcn variables: `--primary` = ink, `--primary-foreground` = paper, `--radius` = 4px, `--ring` = ink.
- Pass the module colour to a page as a CSS variable (`--module`) set on its root, so components use `bg-[var(--module)]`.
- Restyle the existing screens in the same PR: the shell (sidebar → top nav), Today, Modules, and module detail.
- Keep the existing tests passing. Add a contrast unit test that checks every module swatch against ink.
