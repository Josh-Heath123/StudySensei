# StudySensei design system v2: "Glass"

Direction C, chosen by the owner on 18 Nov 2026 from a reference image ([decision 0012](decisions/0012-visual-direction-glass.md)).
It replaces direction B "Planner" ([archived](archive/DESIGN-planner.md)). This file is the spec. The tokens live in
`apps/web/src/index.css` (one source; components use the Tailwind names, never raw values), the components in
`apps/web/src/ui/`, and `apps/web/src/lib/tokens.test.ts` checks every contrast claim below in both themes.

## Principles

1. **Calm, solid surfaces on a soft canvas.** Anything to read sits on a solid surface. Whitespace and hierarchy do
   the work that borders used to.
2. **Glass only for what floats.** Navigation, dialogs, menus, toasts and floating toolbars are glass; content never is.
3. **One primary action per screen,** in violet. Everything else is secondary (outline), quiet or ghost.
4. **Violet acts, pink accents.** The signature gradient (pink → lilac → violet) marks the few expressive moments:
   the Today hero, the session's progress ring and mist, the wordmark dot.
5. **Honest numbers.** Every metric keeps its *Measured* or *Estimated* tag and its basis. Colour never carries meaning
   alone: states always say what they are in words.

## Themes

Light and dark, set as `data-theme` on `<html>`. The Settings page's **Appearance** setting is System (the default),
Light or Dark, stored in `localStorage` (`studysensei.appearance`; every access is wrapped in try/catch). A tiny inline
script in `index.html` applies it before the first paint, so the page never flashes the wrong theme, and
`src/lib/appearance.ts` keeps System following the operating system.

## Tokens

### Colour

The palette was sampled from the reference image (its hex labels were wrong): Cloudy White `#F0F0F0`, Galactic Violet
`#5840FF`, Bubblegum Pink `#FE6BD4`, and the signature gradient `linear-gradient(135deg, #FE6BD4, #A77BF6, #5840FF)`.

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| `canvas` | `#F0F0F0` | `#0B0B12` | Page background |
| `surface` | `#FFFFFF` | `#15151F` | Cards, lists, tables, forms |
| `surface-2` / `subtle` | `#F7F7F8` | `#1C1C28` | Quiet fills, tracks, segmented-control track, hover |
| `fg` | `#0B0B12` | `#F0F0F0` | Text |
| `muted` | `#5E5E6B` | `#A3A3B5` | Secondary text |
| `line` | `rgba(11,11,18,0.08)` | `rgba(255,255,255,0.08)` | Hairlines and dividers (decorative) |
| `line-strong` | `#838394` | `#72728A` | Boundaries a control needs (inputs, outline buttons): 3:1 |
| `primary` | `#5840FF` | `#5840FF` | The violet button (white text) |
| `primary-hover` | `#4A33E0` | `#6A55FF` | Its hover |
| `primary-edge` | `#5840FF` | `#8B7BFF` | The button's 1 px edge, so it keeps a 3:1 boundary on dark surfaces |
| `link` / `ring` | `#5840FF` | `#8B7BFF` | Violet text and links; the focus ring |
| `accent-soft` | `#ECE8FF` | `#24203F` | Selected nav item, soft violet chips, icon wells |
| `danger` | `#C0183C` | `#FF7B8F` | Errors, destructive actions, "Overdue" |
| `warning` | `#8A5200` | `#F0B44C` | "Due soon", resting AI |
| `success` | `#137446` | `#4CD69B` | Done, connected |
| `pink` | `#FE6BD4` | `#FE6BD4` | A fill and accent only: never text on light, always dark text on top |
| `on-fill` | `#0B0B12` | `#0B0B12` | Text on module colours and on pink |
| `scrim` | `rgba(11,11,18,0.35)` | `rgba(0,0,0,0.6)` | Behind dialogs |

**Module colours** keep their eight swatches and their meaning: a fill behind dark text (`on-fill`, at least 4.5:1).
They read on both canvases, so nothing was retuned and no migration was needed: Orange `#FF7A3D` (default), Yellow
`#FFD23F`, Mint `#5EE0B0`, Blue `#8FB8FF`, Lilac `#C9A7FF`, Pink `#FF8FA3`, Lime `#B8E05E`, Cyan `#6ED3E8`.

### Contrast

- Text: 4.5:1. UI boundaries and the focus ring: 3:1.
- `fg`, `muted`, `link`, `danger`, `warning` and `success` pass on `canvas`, `surface` and `surface-2` in both themes;
  white passes on `primary` and `primary-hover`; `fg` and `muted` pass on `accent-soft`; dark text passes on pink and
  on every module colour.
- Text never sits directly on the gradient (dark text fails at the violet end, white at the pink end). It sits on a
  solid or glass layer instead.
- `tokens.test.ts` computes all of this from the stylesheet, so it can't regress.

### Type

Inter variable only (`@fontsource-variable/inter`, self-hosted). Tabular numerals for every time, countdown and count.

| Role | Size / line height | Weight | Tracking |
| --- | --- | --- | --- |
| Display (`type-display`): Today's date, editorial moments | 44–64 / 1.0 (fluid) | 300 | −0.035em |
| Timer (`type-timer`) | 88–168 / 0.95 (fluid), tabular | 200 | −0.04em |
| Countdown (`type-countdown`) | 40 / 1.0, tabular | 300 | −0.03em |
| H1 (`type-h1`) | 36 / 1.15 | 500 | −0.025em |
| H2 (`type-h2`) | 24 / 1.25 | 600 | −0.015em |
| H3 (`type-h3`) | 17 / 1.35 | 600 | −0.01em |
| Body | 15 / 1.55 | 400 | 0 |
| Small | 13 / 1.45 | 400 | 0 |
| Label (`type-label`) | 12 / 1.3, uppercase | 600 | 0.06em |

### Radius

Controls 10 (`rounded-md`; the segmented control 12, its segments 9). Chips 6 (`rounded-sm`). Cards 16–20
(`rounded-lg`, `rounded-xl`). Dialogs and sheets 24 (`rounded-2xl`). Soft, not pills everywhere: only progress tracks
and the wordmark dot are fully round.

### Elevation

Light: soft, layered shadows tinted `rgba(17,12,46,…)`: `shadow-sm` (cards), `shadow-md` (the key card, raised
segments), `shadow-lg` (floating glass). Dark: barely any; depth comes from the surface steps (`canvas` → `surface` →
`surface-2`) and a faint top highlight on cards.

### Motion

Three durations, 120 / 200 / 320 ms, on one ease, `cubic-bezier(0.2, 0.8, 0.2, 1)` (`ease-soft`). Transitions,
`tw-animate-css` and Radix `data-state` animations only; no animation library. Presses scale to 0.98. Under
`prefers-reduced-motion` nothing moves: transforms are off and only (instant) opacity changes remain.

## Glass

**Where:** the sticky top navigation; dialogs and sheets; popovers, menus and selects; toasts; floating toolbars (the
topic ReviewBar); the session screen's floating control bar.

**Never:** data tables, forms, the topic tree, the materials list, the viewer's page area, the settings meters, or
anything long to read.

**Recipe** (`glass`, `glass-strong`, `glass-hero` utilities in `index.css`): a translucent tint, `backdrop-filter:
blur(24px) saturate(160%)`, a 1 px border (light `rgba(255,255,255,0.7)`, dark `rgba(255,255,255,0.08)`), an inner
hairline, a top highlight and a soft shadow.

| Utility | Light tint | Dark tint | For |
| --- | --- | --- | --- |
| `glass` | `rgba(255,255,255,0.62)` | `rgba(24,24,36,0.55)` | Glass over a known, soft backdrop: the session bar over its mist |
| `glass-hero` | `rgba(255,255,255,0.80)` | `rgba(24,24,36,0.78)` | Text over the signature gradient (Today's hero) |
| `glass-strong` | `rgba(255,255,255,0.86)` | `rgba(24,24,36,0.86)` | Glass that can float over anything: navigation, dialogs, menus, toolbars, toasts |

**Legibility:** every glass surface keeps 4.5:1 for `fg` and `muted` text against the worst case behind it. The base
recipe passes over the session mist, but not over dark text or a bright module colour, so glass that can float over
any content uses `glass-strong`; `tokens.test.ts` checks each against its worst case. Without `backdrop-filter`, or under
`prefers-reduced-transparency`, glass falls back to the solid `surface`.

## Components

| Component | Spec |
| --- | --- |
| **Button: primary** (`default`, also `module`) | `primary` fill, white text, 1 px `primary-edge`, `shadow-sm`, 15/600, radius 10, min-height 44. One per screen |
| **Button: secondary** (`outline`, `onDark`) | `surface` fill, 1 px `line-strong` border, `fg` text; hover `subtle` |
| **Button: quiet** | `subtle` fill, `fg` text, 13/500, min-height 36: suggestion chips |
| **Button: ghost / link** | No fill; hover `subtle`. Links are `link` violet |
| **Button: destructive** | `surface` fill, `danger` text and border; hover a faint danger tint |
| **States** | Hover (fill steps), pressed (scale 0.98), focus-visible (2 px `ring` outline, 2 px offset), selected (`accent-soft` or a raised surface), disabled (45 % opacity), loading (skeletons), empty, error (`danger` text with `role="alert"`), success (`success` text) |
| **Top navigation** | Sticky glass bar, radius 20, inset from the edges. Wordmark (17/600 with a gradient dot), then sections; the current one is an `accent-soft` pill. Below 640 px the sections scroll sideways under the wordmark |
| **Page header** | Label eyebrow, then H1 (or Display on Today), optional description, actions or tiles on the right |
| **Card** | Solid `surface`, 1 px `line`, `shadow-sm`, radius 20, padding 20–24. `key` adds `shadow-md` |
| **Segmented control** (tabs) | `subtle` track, radius 12, padding 4; segments radius 9; the selected one is a raised `surface` with `fg` text; others `muted`. Real `role="tab"` + `aria-selected`; scrolls sideways when narrow |
| **Form fields** | Solid `surface`, 1 px `line-strong`, radius 10, min-height 44, 15 px. Focus: `ring` border plus the focus ring. Every input has a real `<label>` |
| **Dialog** | `glass-strong`, radius 24, padding 24, over the `scrim`; fades and scales from 0.97 in 200 ms |
| **Badge / chip** | Radius 6, 12/600. Status chips are `surface` with status-coloured text and a faint border; neutral chips `subtle` + `muted` |
| **Module badge** | Module-colour fill, `on-fill` text 12/600, radius 6 |
| **Segmented progress** | Focus segments on an `accent-soft` track, breaks on `subtle`, the elapsed part filled with the gradient |
| **Meters** | Solid track (`subtle`), violet fill, with the *Measured* / *Estimated* labels beside them |
| **Skeleton** | `skeleton` utility: a `subtle` block that pulses (opacity only) |
| **Empty state** | One icon in an `accent-soft` well, one sentence, at most one action |
| **Icons** | lucide-react only, one stroke width (1.75, set globally) |

## Screens

- **Today** (the most expressive): an editorial date in Display type; "Next up" as the hero card, the gradient as its
  background with its text on a `glass-hero` layer; countdown tiles, deadlines and the day timeline (module-colour
  blocks) calm and solid; the system status card quiet.
- **Session** (`/session`): a very large, light timer inside a progress ring with a gradient stroke; a faint ambient
  gradient mist behind it in both themes; a floating `glass` control bar (pause, break, end); the reflection form solid
  and calm; the away dialog in glass.
- **Modules and module detail:** a clean header with the module's colour; tabs as a segmented control; solid, readable
  lists and tables.
- **Topics:** a solid tree; AI and review state shown subtly (a small violet dot and a quiet label); the ReviewBar a
  floating glass toolbar; the merge and linked-pages dialogs in glass.
- **Materials:** a refined upload area and status, skeleton loaders, a prominent search box, and the viewer's chrome
  in glass with the page canvas on a solid surface.
- **Settings:** AI providers in solid cards with violet usage meters (labels kept), and Appearance.
- **Placeholders** (Plan, Practice, Insights): a designed empty state saying which phase each arrives in.

## Responsive

Desktop (1440), tablet (768) and mobile (375). Page padding 16 on mobile, 32 on tablet, 40 on desktop. Grids collapse
to one column below 1024 px; the navigation scrolls sideways below 640 px; dialogs stay within the viewport and scroll
inside.
