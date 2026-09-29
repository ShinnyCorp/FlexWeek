# FlexWeek 0.17 mock-up

The options of Phase 2 of `docs/0.17/plan.md`: for each of the eight designs, the 0.16 screen and
two revised directions, **A** (refined in place) and **B** (a different structure or interaction),
drawn in the Phase 1 system; every revised look on Today's app; and the system itself. Jonathan
picks A, B or "Keep as it is" for each design on its page; the picks show under "Your picks".

Open it: `python docs/mockups/look-017/demo.py` (serves the repository read-only on 127.0.0.1 and
opens the page). This is a mock-up, not FlexWeek: it reads and writes no FlexWeek data.

## How a design is added

One file per design, `designs/<id>.js`, and optionally `designs/<id>.css`, both already linked from
`index.html`. The file calls:

```js
FW.register({
  id: "timeline",                  // today, timeline, mission, bento, retro, clay, one, dial
  name: "Timeline",
  purpose: "Agenda",               // as Settings names it
  role: "main",                    // "day" for One thing and Day dial
  now: "What 0.16 draws, in a sentence or two.",
  current: { week: "current/c-timeline-week.png", day: "current/c-timeline-day.png" },
  signature: { name: "Night", dark: true, vars: { "--page": "#0b0d10", "--accent": "#…" } },
  variants: {
    A: { name: "Notebook", summary: "…", catalogue: ["E-Ink / Paper", "…"], changes: ["…"],
         render(el, ctx) { … } },
    B: { name: "Planner spread", …, render(el, ctx) { … } },
  },
});
```

`render(el, ctx)` fills `el`, the window's content under the shared top bar: 1280 by 744 pixels.
`ctx.view` is `"week"` or `"day"` (`"myday"` for day screens); `ctx.look` the look's id; `ctx.dark`
whether it is a dark look; `ctx.colours` `"look"` or `"signature"`; `ctx.week` the busy week
(`data.js`); `ctx.time` its helpers (`clock`, `range`, `length`, `on(day)`). The top bar is drawn by
`app.js`; a design never draws its own.

## The rules a design keeps

- Colours only from the CSS variables in `looks.css`: `--page`, `--card`, `--card-2`, `--text`,
  `--muted`, `--hairline`, `--hairline-strong`, `--grid-rule`, `--accent`, `--accent-ink`,
  `--accent-tint`, `--danger`, `--focus`, `--shadow-sm`, `--shadow-lg`, and for a block or chip
  `data-cat="<category>"`, which sets `--fill` and `--mark` (and `--c-<category>-fill` and `-mark`
  are there too). A signature colourway may override variables, and nothing else.
- Type only from the scale: `--t-caption`, `--t-body`, `--t-heading`, `--t-title`, `--t-display`, in
  `--w-regular` or `--w-strong`, and `--w-number` for display numbers only. Faces: `--font-body`,
  `--font-head`, `--font-sans`, `--font-serif`, `--font-mono`; Retro desktop may use "Pixelify Sans"
  and "VT323" (both in `fonts/`, OFL).
- Spacing `--s1` to `--s6`; radii `--r-control`, `--r-card`, `--r-sheet`, `--r-pill`.
- Icons with `FW.icon(name, size)` (Lucide, `icons/`; add one with its SVG there and
  `python build_icons.py`); never a Unicode glyph or an emoji.
- Red (`--danger`) only for "cannot go here", "past due" and deleting.
- Homework (`assignments`) always has a non-colour cue: the book-open icon.
- It must read well in all ten looks, including High contrast, and at 1280x800.
- Motion, if shown, stays inside the design, uses CSS transitions of 150 to 300 ms, never loops, and
  honours `@media (prefers-reduced-motion: reduce)`.
- Namespaced class names (`.tl-…` for Timeline and so on) so designs never style each other.

## Looking at it

`~/.flexweek-ui-harness/shoot-mockup.sh <root> <out dir> name="<hash>" …` photographs states with a
headless Chromium on a throwaway profile. A hash is the page's address after `#`:
`design=timeline&variant=B&view=week&look=dark&colours=signature&bare=1` (`bare=1` is the stage alone
at 1280x800).
