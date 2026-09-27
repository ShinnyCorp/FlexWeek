// Mission control (Dashboard): the week as lanes of hours with the numbers beside them. A, Flight
// deck: seven lanes from the top, a homework chart and the deadlines on the right. B, Ops board: four
// figures across the top, the lanes under them, and a deadline table on the right.

(function () {
  const W = FW.week;
  const T = FW.time;
  const START = 8 * 60;
  const END = 22 * 60;
  const SPAN = END - START;
  const HOURS = Array.from({ length: SPAN / 60 + 1 }, (_, i) => START + i * 60);
  const pct = (minute) => ((minute - START) / SPAN) * 100;
  const NOW = W.today * 1440 + W.now;
  const TICK = 30; // a block this short or shorter is drawn as a tick, named on hover

  const minutesOf = (blocks) => blocks.reduce((sum, b) => sum + b.end - b.start, 0);
  const homeworkOn = (day) => T.on(day).filter((b) => b.homework);
  const placed = W.homework.filter((h) => h.placed);
  const book = (size = 14) => `<span class="mc-book">${FW.icon("book-open", size)}</span>`;
  const num = (text) => `<span class="mc-num">${text}</span>`;
  const zoom = () =>
    `<span class="mc-zoom"><span>${FW.icon("minus", 14)}</span><i></i><span>${FW.icon("plus", 14)}</span></span>`;

  // "3 h 20 min" with the figures in mono and the units in the body face.
  function figure(minutes) {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    const parts = [];
    if (h) parts.push(`${num(h)}<span class="mc-unit">h</span>`);
    if (m || !h) parts.push(`${num(m)}<span class="mc-unit">min</span>`);
    return parts.join(" ");
  }
  const clockLength = (minutes) => `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}`;

  // Every homework is due at the end of its day.
  function timeLeft(h) {
    const left = (h.due.day + 1) * 1440 - NOW;
    const d = Math.floor(left / 1440);
    const hours = Math.floor((left % 1440) / 60);
    return d ? `${d} d ${hours} h` : `${hours} h`;
  }
  function slotOf(h) {
    const b = W.blocks.find((x) => x.homework === h.id);
    return b ? { day: b.days[0], start: b.start } : null;
  }
  const byTimeLeft = [...W.homework].sort(
    (a, b) => a.due.day - b.due.day || a.placed - b.placed || b.minutes - a.minutes
  );

  function header() {
    return `<header class="mc-head">
      <span class="mc-head-line"><strong>Week ${num(39)}</strong><span class="mc-sep"></span>${num(T.clock(W.now))}<span class="mc-sep"></span>${num(placed.length)} of ${num(W.homework.length)} placed</span>
      ${zoom()}
    </header>`;
  }

  // --- lanes ------------------------------------------------------------------------------------

  function block(b, hovered) {
    const length = b.end - b.start;
    const where = `left:calc(${pct(b.start)}% + 1.5px);width:calc(${pct(b.end) - pct(b.start)}% - 3px)`;
    if (length <= TICK) {
      const tip = hovered
        ? `<div class="mc-tip"><strong>${b.title}</strong><span>${num(T.range(b.start, b.end))} · ${T.length(length)}</span></div>`
        : "";
      return `<div class="mc-tick${hovered ? " hover" : ""}" data-cat="${b.category}" data-start="${b.start}" data-end="${b.end}" style="${where}" title="${b.title}, ${T.range(b.start, b.end)}"><i></i>${tip}</div>`;
    }
    return `<div class="mc-block${b.homework ? " mc-hw" : ""}" data-cat="${b.category}" data-start="${b.start}" data-end="${b.end}" style="${where}" title="${b.title}, ${T.range(b.start, b.end)}">
      <div class="mc-b-in">
        <span class="mc-b-title">${b.homework ? book(13) : ""}<span class="mc-b-name">${b.title}</span><span class="mc-b-word">${b.title.split(" ")[0]}</span></span>
        <span class="mc-b-time"><span class="mc-range">${T.range(b.start, b.end)}</span><span class="mc-start">${T.clock(b.start)}</span></span>
        <span class="mc-b-len">${figureText(length)}</span>
      </div>
    </div>`;
  }

  // A block shows as much as fits inside it, whole. When not even its title fits, the title and
  // start go beside it if the lane is free there (as a Gantt chart labels a short bar); failing
  // that, its first word, or its colour alone (homework keeps its book). Never a cut word: a block
  // fits when nothing spills out of it, nor any word out of its line.
  const fits = (inner) =>
    inner.scrollHeight <= inner.clientHeight + 1 && inner.scrollWidth <= inner.clientWidth + 1 &&
    [...inner.children].every((c) => c.scrollWidth <= c.clientWidth + 0.5);
  function fit(root) {
    for (const track of root.querySelectorAll(".mc-track")) {
      track.querySelectorAll(".mc-out").forEach((n) => n.remove());
      const width = track.clientWidth;
      const x = (m) => ((m - START) / SPAN) * width;
      const spans = [...track.querySelectorAll("[data-start]")].map((n) => [+n.dataset.start, +n.dataset.end]);
      for (const node of track.querySelectorAll(".mc-block")) {
        const inner = node.firstElementChild;
        let inside = false;
        for (const level of ["long", "full", "start", "title"]) {
          node.dataset.fit = level;
          if (fits(inner)) { inside = true; break; }
        }
        if (inside) continue;
        const start = +node.dataset.start;
        const end = +node.dataset.end;
        const after = Math.min(...spans.filter(([s]) => s >= end).map(([s]) => s), END);
        const before = Math.max(...spans.filter(([, e]) => e <= start).map(([, e]) => e), START);
        const out = FW.el("div", { class: "mc-out" },
          `<strong>${node.querySelector(".mc-b-name").textContent}</strong><span class="mc-num">${T.clock(start)}</span>`);
        track.appendChild(out);
        // The label may wrap onto a second line, never break a word, and must stay in the lane.
        const title = out.firstElementChild;
        const room = (free) => {
          out.style.maxWidth = `${free}px`;
          return free > 0 && out.scrollWidth <= free + 0.5 &&
            [...out.children].every((c) => c.scrollWidth <= c.clientWidth + 0.5) &&
            title.offsetHeight <= 2.5 * parseFloat(getComputedStyle(title).lineHeight) &&
            out.offsetTop + out.offsetHeight <= track.clientHeight - 4;
        };
        const right = x(after) - x(end) - 10;
        const left = x(start) - x(before) - 10;
        let side = "";
        for (const withTime of [true, false]) {
          out.classList.toggle("no-time", !withTime);
          if (room(right)) { side = "right"; break; }
          if (room(left)) { side = "left"; break; }
        }
        if (side === "right") {
          out.style.left = `${x(end) + 5}px`;
        } else if (side === "left") {
          out.style.left = `${x(start) - 5 - out.offsetWidth}px`;
          out.classList.add("left");
        } else {
          out.remove();
          for (const level of ["word", "bare"]) {
            node.dataset.fit = level;
            if (fits(inner)) break;
          }
          continue;
        }
        node.dataset.fit = "bare";
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

  // Every other hour is named, except where the now pill sits.
  function axis() {
    const labels = HOURS.filter((m) => (m / 60) % 2 === 0 && Math.abs(m - W.now) > 40)
      .map((m) => `<span style="left:${pct(m)}%">${T.clock(m)}</span>`)
      .join("");
    return `<div class="mc-axis"><span></span><div class="mc-axis-hours">${labels}<span class="mc-now-pill" style="left:${pct(W.now)}%">${T.clock(W.now)}</span></div></div>`;
  }

  function lane(d, { hoverDinner = false } = {}) {
    const blocks = T.on(d.index)
      .map((b) => block(b, hoverDinner && d.index === W.today && b.id === "dinner"))
      .join("");
    const now = d.index === W.today ? `<div class="mc-now" style="left:${pct(W.now)}%"></div>` : "";
    const date = d.index === W.today ? `<span class="mc-chip">${num(d.date)}</span>` : `<span class="mc-date">${num(d.date)}</span>`;
    const label = `<div class="mc-lane-name"><strong>${d.short}</strong>${date}</div>`;
    return `<div class="mc-lane${d.index === W.today ? " today" : ""}">${label}<div class="mc-track">${blocks}${now}</div></div>`;
  }

  function lanes(opts) {
    return `<div class="mc-lanes">
      ${axis()}
      <div class="mc-lane-list">${W.days.map((d) => lane(d, opts)).join("")}</div>
      <div class="mc-now-rule"><span></span><div><i style="left:${pct(W.now)}%"></i></div></div>
    </div>`;
  }

  function dayLane() {
    return `<div class="mc-lanes one">
      ${axis()}
      <div class="mc-lane-list">${lane(W.days[W.today])}</div>
    </div>`;
  }

  // --- the right column -------------------------------------------------------------------------

  function nextCard() {
    const n = W.next;
    return `<section class="mc-card mc-next">
      <div class="mc-card-head"><span class="mc-label">Next</span><span class="mc-muted">in ${num(n.inMinutes)} min</span></div>
      <div class="mc-next-row"><span class="mc-next-title" data-cat="extra"><i></i>${n.title}</span>${num(T.clock(n.start))}</div>
    </section>`;
  }

  // A small column chart: homework hours per day, one series in the accent, 0 to 2 h.
  function chartCard(highlight) {
    const max = 120;
    const cols = W.days
      .map((d) => {
        const m = minutesOf(homeworkOn(d.index));
        const on = d.index === highlight;
        const bar = m ? `<span class="mc-col-val">${num(clockLength(m))}</span><i></i>` : `<i class="zero"></i>`;
        return `<div class="mc-col${on ? " on" : ""}"><div class="mc-col-plot" style="--h:${(m / max) * 100}%">${bar}</div><span class="mc-col-day">${d.short}</span></div>`;
      })
      .join("");
    const total = minutesOf(W.days.flatMap((d) => homeworkOn(d.index)));
    return `<section class="mc-card mc-chart">
      <div class="mc-card-head"><span class="mc-label">Homework per day</span><span class="mc-muted">${num(clockLength(total))} this week</span></div>
      <div class="mc-plot">
        <div class="mc-grid"><span data-v="2 h"></span><span data-v="1 h"></span><span data-v="0"></span></div>
        <div class="mc-cols">${cols}</div>
      </div>
    </section>`;
  }

  function deadlinesCard() {
    const rows = byTimeLeft
      .map((h) => {
        const slot = slotOf(h);
        const where = slot
          ? `<span class="mc-muted">Placed ${W.days[slot.day].short} ${num(T.clock(slot.start))}</span>`
          : `<span class="mc-open">Not placed yet</span>`;
        return `<li>
          <div class="mc-dl-top"><span class="mc-dl-title">${book(13)}${h.title}</span><span class="mc-left">${num(timeLeft(h))}</span></div>
          <div class="mc-dl-sub">${where}<span class="mc-muted">${num(clockLength(h.minutes))}</span></div>
        </li>`;
      })
      .join("");
    return `<section class="mc-card mc-deadlines">
      <div class="mc-card-head"><span class="mc-label">Deadlines</span><span class="mc-muted">Due ${W.days[6].short} ${num(W.days[6].date)}</span></div>
      <ul>${rows}</ul>
    </section>`;
  }

  // --- the day's table, under the one wide lane -------------------------------------------------

  function startsIn(b) {
    if (b.end <= W.now) return `<span class="mc-muted">Over</span>`;
    if (b.start <= W.now) return `<span class="mc-open">Now</span>`;
    const m = b.start - W.now;
    return `in ${m >= 60 ? figureText(m) : `${num(m)} min`}`;
  }
  const figureText = (m) => `${num(Math.floor(m / 60))} h${m % 60 ? ` ${num(m % 60)} min` : ""}`;

  // The day's blocks and, from now on, the free time between them.
  function dayRows() {
    const rows = [];
    let cursor = W.now;
    for (const b of T.on(W.today)) {
      if (b.start > cursor) rows.push({ title: "Free", category: "free", start: cursor, end: b.start, free: true });
      rows.push(b);
      cursor = Math.max(cursor, b.end);
    }
    if (cursor < END) rows.push({ title: "Free", category: "free", start: cursor, end: END, free: true });
    return rows;
  }

  function dayTable() {
    const rows = dayRows()
      .map((b) => `<tr class="${b.end <= W.now ? "past" : ""}${b.free ? " free" : ""}">
        <td>${num(T.range(b.start, b.end))}</td>
        <td><span class="mc-cat" data-cat="${b.category}">${b.homework ? book(13) : "<i></i>"}${b.title}</span></td>
        <td class="mc-muted">${b.free ? "" : W.categories[b.category]}</td>
        <td class="r">${num(clockLength(b.end - b.start))}</td>
        <td class="r">${startsIn(b)}</td>
      </tr>`)
      .join("");
    return `<section class="mc-card mc-today">
      <div class="mc-card-head"><span class="mc-label">Today</span><span class="mc-muted">${num(T.on(W.today).length)} things, ${num(clockLength(minutesOf(T.on(W.today))))} in all</span></div>
      <table><thead><tr><th>Time</th><th>What</th><th>Kind</th><th class="r">Length</th><th class="r">Starts</th></tr></thead><tbody>${rows}</tbody></table>
    </section>`;
  }

  // --- A, Flight deck ---------------------------------------------------------------------------

  function flightDeck(el, ctx) {
    const week = ctx.view !== "day";
    el.innerHTML = `<div class="mc-a ${week ? "mc-week" : "mc-day"}">
      ${header()}
      <div class="mc-body">
        <div class="mc-main">${week ? lanes({ hoverDinner: true }) : dayLane() + dayTable()}</div>
        <aside class="mc-side">${nextCard()}${chartCard(W.today)}${deadlinesCard()}</aside>
      </div>
    </div>`;
    fitWhenLaidOut(el);
  }

  // --- B, Ops board -----------------------------------------------------------------------------

  // Free time left today: from now to 22:00, less what is planned.
  function freeLeft() {
    let busy = 0;
    for (const b of T.on(W.today)) busy += Math.max(0, Math.min(b.end, END) - Math.max(b.start, W.now));
    return END - W.now - busy;
  }

  function strip() {
    const today = homeworkOn(W.today);
    const first = today[0];
    const cells = [
      ["Planned today", "calendar", figure(minutesOf(today)), first ? `${first.title} at ${num(T.clock(first.start))}` : "Nothing planned"],
      ["Due this week", "book-open", num(W.homework.length), `${num(placed.length)} placed, ${num(W.homework.length - placed.length)} not placed yet`],
      ["Free time left today", "clock", figure(freeLeft()), `Until ${num(T.clock(END))}`],
      ["Focus minutes", "timer", figure(0), "None yet this week"],
    ];
    return `<div class="mc-strip">${cells
      .map(([label, icon, value, sub]) => `<section class="mc-card mc-fig">
        <div class="mc-card-head"><span class="mc-label">${label}</span><span class="mc-fig-icon">${FW.icon(icon, 16)}</span></div>
        <div class="mc-fig-value">${value}</div>
        <div class="mc-fig-sub">${sub}</div>
      </section>`)
      .join("")}</div>`;
  }

  // Each homework: what it needs, the time left, and a thin bar of how much of it is placed.
  function deadlineTable() {
    const rows = byTimeLeft
      .map((h) => {
        const slot = slotOf(h);
        const state = slot
          ? `Placed ${W.days[slot.day].short} ${num(T.clock(slot.start))}`
          : `<span class="mc-open">Not placed yet</span>`;
        return `<li>
          <span class="mc-dl-title">${book(13)}${h.title}</span>
          <span class="mc-num r">${clockLength(h.minutes)}</span>
          <span class="mc-num r mc-left">${timeLeft(h)}</span>
          <span class="mc-bar"><i style="width:${slot ? 100 : 0}%"></i></span>
          <span class="mc-state r">${state}</span>
        </li>`;
      })
      .join("");
    return `<section class="mc-card mc-table">
      <div class="mc-card-head"><span class="mc-label">Deadlines</span><span class="mc-muted">By time left</span></div>
      <div class="mc-th"><span>Homework</span><span class="r">Needs</span><span class="r">Left</span></div>
      <ol class="mc-rows">${rows}</ol>
      <p class="mc-foot">All ${num(W.homework.length)} are due ${W.days[6].name} ${num(W.days[6].date)}. The bar is how much of each is placed in the week.</p>
    </section>`;
  }

  const unplaced = W.homework.filter((h) => !h.placed);
  const unplacedMinutes = unplaced.reduce((sum, h) => sum + h.minutes, 0);
  const unplacedNames = () => unplaced.map((h) => h.title).join(" and ");

  function upNext() {
    const items = T.on(W.today).filter((b) => b.start > W.now);
    const tomorrow = W.days[W.today + 1];
    const first = T.on(tomorrow.index)[0];
    const free = dayRows().filter((r) => r.free);
    const longest = Math.max(...free.map((r) => r.end - r.start));
    return `<div class="mc-pair">
      <section class="mc-card mc-upnext">
        <div class="mc-card-head"><span class="mc-label">Up next</span><span class="mc-muted">${num(items.length)} more today</span></div>
        <ol class="mc-list">${items
          .map((b) => `<li data-cat="${b.category}">
            <span class="mc-num mc-when">${T.clock(b.start)}</span>
            <span class="mc-cat">${b.homework ? book(13) : "<i></i>"}${b.title}</span>
            <span class="r mc-muted">${startsIn(b)}</span>
          </li>`)
          .join("")}</ol>
        <p class="mc-foot">Then ${tomorrow.name}: ${first.title} at ${num(T.clock(first.start))}.</p>
      </section>
      <section class="mc-card mc-free">
        <div class="mc-card-head"><span class="mc-label">Free time left</span><span class="mc-muted">${num(clockLength(freeLeft()))} until ${num(T.clock(END))}</span></div>
        <ol class="mc-list">${free
          .map((r) => `<li>
            <span class="mc-num mc-when">${T.range(r.start, r.end)}</span>
            <span class="mc-bar"><i style="width:${((r.end - r.start) / longest) * 100}%"></i></span>
            <span class="mc-num r">${clockLength(r.end - r.start)}</span>
          </li>`)
          .join("")}</ol>
        <p class="mc-foot">Room for ${unplacedNames()}, ${num(clockLength(unplacedMinutes))} in all, before ${num(T.clock(END))}.</p>
      </section>
    </div>`;
  }

  function opsBoard(el, ctx) {
    const week = ctx.view !== "day";
    el.innerHTML = `<div class="mc-b ${week ? "mc-week" : "mc-day"}">
      ${strip()}
      <div class="mc-body">
        <div class="mc-main">${week ? lanes({ hoverDinner: true }) : dayLane() + upNext()}</div>
        <aside class="mc-side">${deadlineTable()}</aside>
      </div>
    </div>`;
    fitWhenLaidOut(el);
  }

  FW.register({
    id: "mission",
    name: "Mission control",
    purpose: "Dashboard",
    role: "main",
    now:
      "Lanes of hours floating in the middle of the window under internal labels (\"FLEXWEEK / WEEK 39\", " +
      "\"CARGO BAY\", \"PLAN 3/5 PLACED\"), a \"D\" box for every dinner, and a load chart of bare bars.",
    current: { week: "current/c-mission-week.png", day: "current/c-mission-day.png" },
    signature: {
      name: "Flight deck",
      dark: true,
      vars: {
        "--page": "#0b0f14",
        "--card": "#121821",
        "--card-2": "#18202b",
        "--text": "#e6edf5",
        "--muted": "#8d9aab",
        "--hairline": "#1f2934",
        "--hairline-strong": "#2c3846",
        "--grid-rule": "rgba(230, 237, 245, 0.07)",
        "--accent": "#7fa8ff",
        "--accent-ink": "#0b1224",
        "--danger": "#ff8a7a",
        "--focus": "rgba(127, 168, 255, 0.4)",
        "--shadow-sm": "0 1px 3px rgba(0, 0, 0, 0.5)",
        "--shadow-lg": "0 12px 32px rgba(0, 0, 0, 0.6)",
        "--mark-l": "0.72",
        "--mark-c": "0.11",
      },
    },
    variants: {
      A: {
        name: "Flight deck",
        summary:
          "Seven lanes of hours from the top of the window, days down the left and time across, with the " +
          "numbers in a mono face, a real chart of homework hours per day and the deadlines with their time " +
          "left in a column on the right. The accent is the only bright colour.",
        catalogue: ["HUD / Sci-Fi FUI", "Data-Dense Dashboard", "JetBrains Mono for figures, Inter for words"],
        changes: [
          "Words, not internal labels: \"Week 39\", \"Not placed yet\", \"Deadlines\".",
          "The lanes start at the top of the content; no empty band above Monday.",
          "Blocks of 30 minutes or less are coloured ticks, named on hover (Thursday's dinner is shown hovered).",
          "A real column chart of homework hours per day, with values on the bars and a scale.",
          "Deadlines with the time left, and where each is placed or that it is not placed yet.",
          "Day: the day as one wide lane, and a table of the day with when each thing starts.",
        ],
        render: flightDeck,
      },
      B: {
        name: "Ops board",
        summary:
          "Four figures across the top (planned today, due this week, free time left today, focus minutes), " +
          "the lanes under them, and a deadline table on the right sorted by time left, with a thin bar per " +
          "homework for how much of it is placed.",
        catalogue: ["Data-Dense Dashboard", "JetBrains Mono for figures, Inter for words"],
        changes: [
          "A strip of four figures replaces the header line.",
          "The deadline table: homework, what it needs, where it is placed, the time left, and a progress bar.",
          "Ticks for 30-minute blocks, as in A.",
          "Day: the day as one wide lane, and what is still to come today.",
        ],
        render: opsBoard,
      },
    },
  });
})();
