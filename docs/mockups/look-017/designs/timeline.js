// Timeline (Agenda): the standard alternative to Today's app. A draws the week as a ruled notebook
// page, one line of hours per day; B as a paper planner opened flat, three days on the left page
// and four with the notes on the right.

(function () {
  const W = FW.week;
  const T = FW.time;
  const START = 8 * 60;
  const END = 22 * 60;
  const SPAN = END - START;
  const HOURS = Array.from({ length: SPAN / 60 + 1 }, (_, i) => START + i * 60);
  const pct = (minute) => ((minute - START) / SPAN) * 100;

  const minutesOf = (blocks) => blocks.reduce((sum, b) => sum + b.end - b.start, 0);
  const homeworkOn = (day) => T.on(day).filter((b) => b.homework);
  const weekPlanned = minutesOf(W.days.flatMap((d) => homeworkOn(d.index)));
  const mostInADay = Math.max(...W.days.map((d) => minutesOf(homeworkOn(d.index))));
  const unplaced = W.homework.filter((h) => !h.placed);
  const dueShort = (h) => `${W.days[h.due.day].short} ${W.days[h.due.day].date}`;
  const book = (size = 14) => `<span class="tl-book">${FW.icon("book-open", size)}</span>`;
  const quiet = (minutes) => `${T.length(minutes)} planned <span class="tl-dot">·</span> 0 done`;
  const zoom = () =>
    `<span class="tl-zoom"><span>${FW.icon("minus", 14)}</span><i></i><span>${FW.icon("plus", 14)}</span></span>`;

  // Where each homework sits in the week, for the notes.
  function placedAt(h) {
    const b = W.blocks.find((x) => x.homework === h.id);
    return b ? `${W.days[b.days[0]].short} ${T.clock(b.start)}` : "";
  }

  // A block shows as much as fits, whole: the title and its times, the title and its start, the
  // title alone, then smaller, then its first word, or its colour alone (homework keeps its book).
  // Never a cut word or time.
  function block(b, style, extra = "") {
    return `<div class="tl-block${b.homework ? " tl-hw" : ""} ${extra}" data-cat="${b.category}" style="${style}" title="${b.title}, ${T.range(b.start, b.end)}">
      <div class="tl-b-in">
        <span class="tl-b-title">${b.homework ? book(14) : ""}<span class="tl-b-name">${b.title}</span><span class="tl-b-word">${b.title.split(" ")[0]}</span></span>
        <span class="tl-b-time"><span class="tl-range">${T.range(b.start, b.end)}</span><span class="tl-start">${T.clock(b.start)}</span><span class="tl-len">${T.length(b.end - b.start)}</span></span>
      </div>
    </div>`;
  }

  // Fits: nothing spills out of the block, nor any word out of its line.
  const fits = (inner) =>
    inner.scrollHeight <= inner.clientHeight + 1 && inner.scrollWidth <= inner.clientWidth + 1 &&
    [...inner.children].every((c) => c.scrollWidth <= c.clientWidth + 0.5);
  function fit(root) {
    for (const node of root.querySelectorAll(".tl-block")) {
      const inner = node.firstElementChild;
      for (const level of ["full", "start", "title", "small", "word", "small-word", "bare"]) {
        node.dataset.fit = level;
        if (fits(inner)) break;
      }
    }
  }
  // Measure once laid out, and again once every face a block may use has loaded (a face loads
  // only when first used, so the first measure may be of a fallback).
  const FACES = ['400 11pt "JetBrains Mono"', '600 11pt "JetBrains Mono"', "600 11pt Inter", "600 15pt Newsreader"];
  function fitWhenLaidOut(root) {
    requestAnimationFrame(() => fit(root));
    Promise.all(FACES.map((face) => document.fonts.load(face)))
      .then(() => requestAnimationFrame(() => fit(root)));
  }

  function note(h, tilt) {
    return `<div class="tl-note" data-cat="assignments" style="--tilt:${tilt}deg">
      <span class="tl-note-title">${book(14)}<span>${h.title}</span></span>
      <span class="tl-note-meta"><span>${T.length(h.minutes)}</span><span class="tl-dot">·</span><span>due ${dueShort(h)}</span></span>
    </div>`;
  }

  const dayDate = (d) =>
    d.index === W.today
      ? `<span class="tl-date"><span class="tl-chip">${d.date}</span> September</span>`
      : `<span class="tl-date">${d.date} September</span>`;

  // --- A, Notebook ----------------------------------------------------------------------------

  function notebookWeek(el) {
    const axis = HOURS.map((m) => `<span class="tl-hour" style="left:${pct(m)}%">${T.clock(m)}</span>`).join("");
    const rows = W.days
      .map((d) => {
        const blocks = T.on(d.index)
          .map((b) => block(b, `left:calc(${pct(b.start)}% + 1.5px);width:calc(${pct(b.end) - pct(b.start)}% - 3px)`))
          .join("");
        const now =
          d.index === W.today
            ? `<div class="tl-now" style="left:${pct(W.now)}%"><span class="tl-now-pill">${T.clock(W.now)}</span></div>`
            : "";
        return `<div class="tl-row${d.index === W.today ? " today" : ""}">
          <div class="tl-day"><span class="tl-day-name">${d.name}</span>${dayDate(d)}</div>
          <div class="tl-lane">${blocks}${now}</div>
        </div>`;
      })
      .join("");
    el.innerHTML = `<div class="tl-a tl-a-week">
      <header class="tl-head"><span class="tl-quiet">${quiet(weekPlanned)}</span>${zoom()}</header>
      <div class="tl-sheet">
        <div class="tl-axis"><span></span><div class="tl-axis-hours">${axis}</div></div>
        ${rows}
      </div>
      <footer class="tl-tray">
        <div class="tl-tray-label"><span class="tl-label">Not placed yet</span></div>
        <div class="tl-notes">${unplaced.map((h, i) => note(h, i % 2 ? 0.8 : -1.1)).join("")}<span class="tl-hint">Drag a note onto a day to give it a time.</span></div>
      </footer>
    </div>`;
    fitWhenLaidOut(el);
  }

  function dayStrip() {
    return W.days
      .map((d) => {
        const minutes = minutesOf(homeworkOn(d.index));
        const on = d.index === W.today;
        return `<div class="tl-tab${on ? " on" : ""}">
          <div class="tl-tab-top">
            <span class="tl-tab-day">${d.short} <span class="${on ? "tl-chip" : "tl-tab-date"}">${d.date}</span></span>
            <span class="tl-tab-hw">${minutes ? book(13) + T.length(minutes) : ""}</span>
          </div>
          <div class="tl-tab-bar"><i style="width:${(minutes / mostInADay) * 100}%"></i></div>
        </div>`;
      })
      .join("");
  }

  // The day's hours down a page, for A's ruled page and B's left page.
  function dayHours(hourPx, extraClass = "") {
    const top = (m) => ((m - START) / 60) * hourPx;
    const rules = HOURS.map(
      (m) => `<div class="tl-rule" style="top:${top(m)}px"><span>${T.clock(m)}</span></div>`
    ).join("");
    const blocks = T.on(W.today)
      .map((b) => {
        const h = ((b.end - b.start) / 60) * hourPx;
        const shape = h < 50 ? `tl-one${h < 30 ? " tl-tiny" : ""}` : "tl-stack";
        return block(b, `top:${top(b.start) + 1.5}px;height:${h - 3}px`, shape);
      })
      .join("");
    const now = `<div class="tl-now-h" style="top:${top(W.now)}px"><span class="tl-now-pill">Now ${T.clock(W.now)}</span></div>`;
    return `<div class="tl-hours ${extraClass}" style="height:${(SPAN / 60) * hourPx}px">${rules}<div class="tl-col">${blocks}</div>${now}</div>`;
  }

  // The day's time by category, each with its dot (plan decision 16).
  function categorySummary(day) {
    const totals = {};
    for (const b of T.on(day)) totals[b.category] = (totals[b.category] || 0) + b.end - b.start;
    return Object.entries(totals)
      .map(([cat, m]) => `<li data-cat="${cat}"><i></i><span>${W.categories[cat]}</span><span class="tl-muted">${T.length(m)}</span></li>`)
      .join("");
  }

  function notebookDay(el) {
    const today = W.days[W.today];
    const next = W.next;
    el.innerHTML = `<div class="tl-a tl-a-day">
      <nav class="tl-tabs">${dayStrip()}</nav>
      <div class="tl-page">
        ${dayHours(46)}
        <aside class="tl-margin">
          <section>
            <div class="tl-margin-head"><span class="tl-label">Today</span>${zoom()}</div>
            <span class="tl-sum">${quiet(minutesOf(homeworkOn(today.index)))}</span>
            <ul class="tl-cats">${categorySummary(today.index)}</ul>
          </section>
          <section>
            <span class="tl-label">Next</span>
            <span class="tl-next-title">${next.title}</span>
            <span class="tl-next-meta">${T.clock(next.start)} <span class="tl-dot">·</span> in ${next.inMinutes} min</span>
          </section>
          <section>
            <span class="tl-label">Not placed yet</span>
            <div class="tl-notes stacked">${unplaced.map((h, i) => note(h, i % 2 ? 0.7 : -0.9)).join("")}</div>
            <span class="tl-hint">Drag a note onto the page to place it.</span>
          </section>
        </aside>
      </div>
    </div>`;
    fitWhenLaidOut(el);
  }

  // --- B, Planner spread ----------------------------------------------------------------------

  const HOUR_B = 36;

  function column(d) {
    const top = (m) => ((m - START) / 60) * HOUR_B;
    const blocks = T.on(d.index)
      .map((b) => block(b, `top:${top(b.start) + 1.5}px;height:${((b.end - b.start) / 60) * HOUR_B - 3}px`,
        (b.end - b.start) / 60 * HOUR_B < 30 ? "tl-one" : "tl-stack"))
      .join("");
    const now = d.index === W.today
      ? `<div class="tl-now-h" style="top:${top(W.now)}px"><span class="tl-now-pill">${T.clock(W.now)}</span></div>`
      : "";
    return `<div class="tl-pcol${d.index === W.today ? " today" : ""}">${blocks}${now}</div>`;
  }

  function columnHead(d) {
    const date = d.index === W.today ? `<span class="tl-chip">${d.date}</span>` : `<span class="tl-date">${d.date}</span>`;
    return `<div class="tl-phead${d.index === W.today ? " today" : ""}"><span class="tl-day-name">${d.name}</span>${date}</div>`;
  }

  function pageGrid(days, withGutter) {
    const rules = HOURS.map((m) => `<div class="tl-prule" style="top:${((m - START) / 60) * HOUR_B}px"></div>`).join("");
    const labels = withGutter
      ? `<div class="tl-pgutter">${HOURS.map((m) => `<span style="top:${((m - START) / 60) * HOUR_B}px">${T.clock(m)}</span>`).join("")}</div>`
      : "";
    return `<div class="tl-pheads${withGutter ? " gutter" : ""}">${withGutter ? "<span></span>" : ""}${days.map(columnHead).join("")}</div>
      <div class="tl-pgrid${withGutter ? " gutter" : ""}" style="height:${(SPAN / 60) * HOUR_B}px">
        ${labels}<div class="tl-pcols" style="--n:${days.length}">${rules}${days.map(column).join("")}</div>
      </div>`;
  }

  function dueList() {
    const rows = [...W.homework]
      .sort((a, b) => a.placed - b.placed)
      .map((h) => `<li${h.placed ? "" : " class=\"open\""}>
          <span class="tl-due-title">${book(13)}${h.title}</span>
          <span class="tl-due-when">${h.placed ? placedAt(h) : "Not placed yet"}</span>
        </li>`)
      .join("");
    return `<ul class="tl-due">${rows}</ul>`;
  }

  function plannerWeek(el) {
    const left = W.days.slice(0, 3);
    const right = W.days.slice(3);
    el.innerHTML = `<div class="tl-b tl-b-week">
      <div class="tl-spread">
        <section class="tl-leaf left">
          ${pageGrid(left, true)}
          <div class="tl-band">
            <span class="tl-label">This week</span>
            <div class="tl-stats">
              <div><strong>${T.length(weekPlanned)}</strong><span>homework planned</span></div>
              <div><strong>0 of ${W.homework.length}</strong><span>done</span></div>
              <div><strong>${unplaced.length}</strong><span>not placed yet</span></div>
            </div>
            <p class="tl-next-line"><span class="tl-muted">Next</span> ${W.next.title} <span class="tl-muted">at ${T.clock(W.next.start)}, in ${W.next.inMinutes} min</span></p>
          </div>
        </section>
        <section class="tl-leaf right">
          ${pageGrid(right, false)}
          <div class="tl-band notes">
            <div class="tl-band-part">
              <span class="tl-label">Not placed yet</span>
              <div class="tl-notes square">${unplaced.map((h, i) => note(h, i % 2 ? 1 : -1.4)).join("")}</div>
            </div>
            <div class="tl-band-part">
              <span class="tl-label">Due this week</span>
              ${dueList()}
            </div>
          </div>
        </section>
      </div>
    </div>`;
    fitWhenLaidOut(el);
  }

  function plannerDay(el) {
    const today = W.days[W.today];
    const summary = categorySummary(today.index);
    el.innerHTML = `<div class="tl-b tl-b-day">
      <div class="tl-spread">
        <section class="tl-leaf left">
          <div class="tl-pheads gutter one"><span></span>${columnHead(today)}</div>
          <div class="tl-pgrid gutter day">
            ${dayHours(45, "planner")}
          </div>
        </section>
        <section class="tl-leaf right">
          <div class="tl-notes-page">
            <section>
              <span class="tl-label">Today</span>
              <p class="tl-sum-line">${quiet(minutesOf(homeworkOn(today.index)))}</p>
              <ul class="tl-cats">${summary}</ul>
            </section>
            <section>
              <span class="tl-label">Next</span>
              <p class="tl-sum-line"><strong>${W.next.title}</strong> <span class="tl-muted">at ${T.clock(W.next.start)}, in ${W.next.inMinutes} min</span></p>
            </section>
            <section>
              <span class="tl-label">Due this week</span>
              ${dueList()}
            </section>
            <section>
              <span class="tl-label">Not placed yet</span>
              <div class="tl-notes">${unplaced.map((h, i) => note(h, i % 2 ? 0.9 : -1.2)).join("")}</div>
            </section>
            <section class="tl-lined"><span class="tl-label">Notes</span></section>
          </div>
        </section>
      </div>
    </div>`;
    fitWhenLaidOut(el);
  }

  // Ruled paper is a light colourway: under a dark look it puts back the light category fills that
  // the dark family would otherwise mix into its cards.
  const fills = {};
  for (const [cat, hue] of Object.entries({
    class: 255, assignments: 25, study: 295, exercise: 150, extra: 205, meals: 60, sleep: 275,
  })) fills[`--c-${cat}-fill`] = `oklch(var(--fill-l) var(--fill-c) ${hue})`;
  fills["--c-free-fill"] = "oklch(var(--fill-l) 0.01 250)";

  FW.register({
    id: "timeline",
    name: "Timeline",
    purpose: "Agenda",
    role: "main",
    now:
      "The week as seven lines of hours, with heavy black day names, homework as black slabs cut to " +
      "\"Hist…\", the title twice (the top bar's and \"This week\"), and \"D\" for every dinner.",
    current: { week: "current/c-timeline-week.png", day: "current/c-timeline-day.png" },
    signature: {
      name: "Ruled paper",
      dark: false,
      vars: {
        "--page": "#fdfbf7",
        "--card": "#fffdf9",
        "--card-2": "#f6f1e8",
        "--text": "#1a1a1a",
        "--muted": "#5c5750",
        "--hairline": "#e6e0d6",
        "--hairline-strong": "#cfc7b9",
        "--grid-rule": "#ece6dc",
        "--accent": "#3d6fc4",
        "--accent-ink": "#ffffff",
        "--danger": "#c42b1c",
        "--focus": "rgba(61, 111, 196, 0.4)",
        "--shadow-sm": "none",
        "--shadow-lg": "0 0 0 1px #cfc7b9",
        "--font-head": "var(--font-serif)",
        "--mark-l": "0.62",
        "--mark-c": "0.14",
        "--fill-l": "0.92",
        "--fill-c": "0.035",
        ...fills,
      },
    },
    variants: {
      A: {
        name: "Notebook",
        summary:
          "The week as seven ruled lines of hours down a page, as now, refined: quiet serif day names, " +
          "ink-outlined blocks with a category tab, homework in its own colour with a book, and the " +
          "homework not placed yet as sticky notes in the bottom margin.",
        catalogue: ["E-Ink / Paper", "Classic Elegant pairing (serif display, Inter body)"],
        changes: [
          "One title, the top bar's; the design's own header is a quiet line of what is planned and done.",
          "Day names in the heading face at 600, not black 800; today's date in an accent chip.",
          "Blocks outlined in ink with a 3-pixel category tab; whole times when they fit, and colour only below three letters of room, never \"D\".",
          "Homework in its category colour with the book icon, never black slabs.",
          "Not placed yet as sticky notes in the bottom margin.",
          "Day: one ruled page of the day, a strip of seven tabs with each day's homework, now with its time.",
        ],
        render(el, ctx) {
          (ctx.view === "day" ? notebookDay : notebookWeek)(el, ctx);
        },
      },
      B: {
        name: "Planner spread",
        summary:
          "The week as a paper planner opened flat: Monday to Wednesday on the left page, Thursday to " +
          "Sunday on the right, each day a column of hours from 08:00 to 22:00, and the notes at the foot " +
          "of the pages. Day opens the planner at one day: its hours on the left, its notes on the right.",
        catalogue: ["E-Ink / Paper", "Classic Elegant pairing (serif display, Inter body)"],
        changes: [
          "Two pages with a gutter between them, the hour rules running across both.",
          "Each day a column of hours, the blocks as in A.",
          "The foot of the right page holds Not placed yet as sticky notes and what is due this week.",
          "Day: the day's hours on the left page; what is due, what is not placed and the summary on the right.",
        ],
        render(el, ctx) {
          (ctx.view === "day" ? plannerDay : plannerWeek)(el, ctx);
        },
      },
    },
  });
})();
