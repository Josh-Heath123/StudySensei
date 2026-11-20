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
| `glass-strong` | `rgba(255,255,255,0.86)` | `rgba(24,24,36,0.86)` | Glass that can float over anything: dialogs, menus, toolbars, toasts |
| `glass-nav` | `rgba(255,255,255,0.92)`, blur 36 px | `rgba(21,21,31,0.94)`, blur 36 px | The navigation (top bar and phone tab bar): content scrolls under it all the time, so it's the most opaque |

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
| **Navigation** | One `<nav>`. From 640 px: a sticky `glass-nav` bar at the top, radius 20, inset from the edges, with the wordmark (17/600 with a gradient dot) and the sections; the current one is an `accent-soft` pill. Below 640 px: the wordmark stays at the top and the sections become a `glass-nav` tab bar fixed to the bottom (icons and 11 px labels, safe-area insets, the current tab violet on `accent-soft`) |
| **Menu** (`ui/dropdown-menu.tsx`) | A "…" button (`MoreButton`, with a label) opening a `glass-strong` popover, radius 16; items 13/500, min-height 40; destructive items in `danger`. For secondary actions (a module's Edit and Delete; a topic's actions on touch screens) |
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
| **Search result** | Leads with what will open, in strong text: the material's title and "page N"; the snippet underneath (Markdown stripped for display, highlights kept), clamped to 3 lines; one result per page, with "N matches on this page" when there are more |
| **Tutor panel** | Chrome `glass` (radius 24, sticky, collapsible to one "Ask about this topic…" line); the conversation on one solid `surface-card` (answers are reading material: `answer-prose`, 15/1.6); the input bar `glass`. Questions in `subtle` bubbles on the right. Citations are `accent-soft` chips (11/600, radius 6) that turn violet on hover or focus, with a `glass-strong` tooltip naming the material and page. Under each answer: cited sources first on `accent-soft`, the others folded; a muted "Answered by … (measured)" footnote. A violet caret while streaming (still under reduced motion). Errors in `danger` with Retry; "not covered" is a normal answer |
| **Bottom sheet** (`ui/sheet.tsx`) | `glass-strong`, pinned to the bottom, radius 24 on the top corners, up to 88 % of the viewport, safe-area padding; slides up in 320 ms (fades only under reduced motion) |
| **Viewer page** | A solid surface. **Fit page** (the default) fits the whole page into the visible area with no scrollbars; **Fit width** fits the width and scrolls down, with its scrollbar space reserved so the width never changes while drawing |
| **Topic tree rows** | Chapters 15/600, subtopics 15/400, page counts muted. Row actions appear on hover and focus-within (still in the tab order); on touch screens they're behind one "…" menu |
| **Weekly editor** (Settings → Study time) | A solid card; one row per weekday (the day 15/600 with its total muted under it, then its windows as two native time inputs with "to" between and a ghost remove button); "Add a window" a quiet button. Errors under the day in `danger`. No dragging yet |
| **Week grid** (Plan, from 1024 px) | A solid card: a 56 px hour column, then seven day columns, Monday first, in the user's timezone. Hour rows (dashed `line`) run only from the week's earliest free window or block to its latest. Free windows are bands of `accent-soft` at 60 %; today's column is tinted `accent-soft` with its header in `link`. 1.1 px a minute (a 50-minute block is 55 px). Blocks whose server action allows it can be dragged with pointer events, snapping to 5 minutes and across days; a ghost card shows the drop time; a refused drop snaps back with its sentence in a small `glass-strong` note under the block |
| **Plan block card** | Solid `surface`, 1 px `line`, radius 10, a 4 px left edge in the module colour. Two rows: the topic 13/600 (or "Final review · …"), then the time (start only in the grid) with the method, or the status in its place: done a `success` check and "48 min (measured)"; skipped muted and struck through; missed muted, "Missed"; in progress "Now" in `link` with a `ring`. It's a button that opens the popover |
| **Block popover** | `glass-strong`, radius 20, 352 px, beside the card from 640 px; a bottom sheet on phones. When, Why (the reason), How (the method), "Moved by you." or "Kept for the next 24 h.", then only the buttons the server allows: Start session (primary), Move… (outline: a dialog of the week's days and 5-minute times inside that day's free windows), Skip (ghost, confirms first) |
| **Day menu** | The "…" (`MoreButton`, 32 px) on a day's header: "Mark unavailable" (confirms first when it replaces custom hours), or "Make available again" (confirms that the day goes back to the weekly hours) on an unavailable day, whose header says "Unavailable" |
| **Confidence control** | The segmented-control look (`subtle` track, radius 12, raised selected segment) as a radio group: "–" (not rated) and 1-5, each with its meaning as the title and in the accessible name; the chosen meaning in a muted line below |
| **Icons** | lucide-react only, one stroke width (1.75, set globally) |

## Screens

- **Today** (the most expressive): an editorial date in Display type; "Next up" as the hero card, the gradient as its
  background with its text on a `glass-hero` layer, naming the plan's next block (when, or "Now"; the method as the
  instruction; "Why:" its reason) with Start session and Skip only when allowed, or "Nothing planned yet" with links to
  study time and assessments; countdown tiles and deadlines calm and solid; "Your day" today's blocks as compact rows
  with their status; the system status card quiet.
- **Plan** (`/plan`): the page header with the week ("Mon 16 Nov – Sun 22 Nov") as its eyebrow, the version's summary
  muted with its time ("Updated 14:43 · You skipped …"), and previous / "This week" / next. Then one solid card: a
  status chip (Fits `success`, Tight `warning`, Short `danger`), the overall line, the levers, and the per-assessment
  lines folded under "Details". "Updating your plan…" while a re-plan is pending. Then the week grid from 1024 px, or an
  agenda below it: a solid card per day with its free windows, its day menu and the same block cards, without dragging.
  Empty states link to Settings → Study time, or to Modules.
- **Session** (`/session`): a very large, light timer inside a progress ring with a gradient stroke; a faint ambient
  gradient mist behind it in both themes; a floating `glass` control bar (pause, break, end); then one small card for
  Materials. From 1024 px the **tutor panel** sits on the right (360 px, 400 px from 1280) and the timer's column never
  narrows below 480 px; below 1024 px it's a "Tutor" button that opens a glass bottom sheet. The reflection form is
  solid and calm; the away dialog in glass.
- **Modules and module detail:** a clean header with the module's colour, Start session as the one primary action and
  Edit and Delete in a "…" menu; tabs as a segmented control; solid, readable lists and tables.
- **Topics:** a solid tree; AI and review state shown subtly (a small violet dot and a quiet label); the ReviewBar a
  floating glass toolbar; the merge and linked-pages dialogs in glass. A topic's workload and confidence show in its
  row only on hover or focus; they're edited in its detail dialog, on a solid card above its pages.
- **Materials:** a refined upload area and status, skeleton loaders, a prominent search box, and the viewer's chrome
  in glass with the page canvas on a solid surface.
- **Settings:** Appearance first, then Study time (a one-line summary of the week, the weekly editor beside Limits
  and Exceptions cards), then AI providers in solid cards with violet usage meters (labels kept).
- **Placeholders** (Practice, Insights): a designed empty state saying which phase each arrives in.

## Layout and responsive

- **One container per page:** 1120 px, centred. A page's header and its content share it, so header actions line up
  with the content's right edge. Sections don't add narrower columns of their own; only long prose keeps a readable
  measure (`max-w-2xl` on the paragraph).
- Desktop (1440), tablet (768) and mobile (375). Page padding 16 on mobile, 32 on tablet, 40 on desktop. Grids collapse
  to one column below 1024 px; below 640 px the navigation is the bottom tab bar and pages keep room for it; dialogs
  stay within the viewport and scroll inside.
