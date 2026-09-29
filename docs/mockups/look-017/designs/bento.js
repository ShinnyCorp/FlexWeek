// Bento (Dashboard), revised for 0.17 (docs/0.17/plan.md, Phase 2). A is the Bento Box Grid entry
// as written: a hero tile of the week's hours and smaller tiles around it. B makes today the hero and
// the other six days small tiles in a row. The top bar has Add, so no tile carries a second one.

(function () {
  const W = FW.week;
  const T = FW.time;
  const TODAY = W.today;
  const WEEK = { from: 8 * 60, to: 22 * 60 };
  const DAY = { from: 8 * 60, to: 21 * 60 };
  const LEGEND = ["class", "assignments", "extra", "exercise", "meals"];

  const sum = (list, f) => list.reduce((n, x) => n + f(x), 0);
  const minutesOn = (day) => sum(T.on(day), (b) => b.end - b.start);
  const homeworkOn = (day) => T.on(day).filter((b) => b.category === "assignments");
  const book = (size = 12) => FW.icon("book-open", size, 2);
  const weekMinutes = sum(W.days, (d) => minutesOn(d.index));
  const placedHomework = W.homework.filter((h) => h.placed);
  const unplaced = W.homework.filter((h) => !h.placed);
  const placedMinutes = sum(placedHomework, (h) => h.minutes);
  const unplacedMinutes = sum(unplaced, (h) => h.minutes);
  const ahead = T.on(TODAY).filter((b) => b.start > W.now).length;
  const top = (r, minute) => ((minute - r.from) / (r.to - r.from)) * 100;
  const tall = (r, minutes) => (minutes / (r.to - r.from)) * 100;

  // A short length for tight places: "1 h 30", "45 min".
  function short(minutes) {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    if (!h) return `${m} min`;
    return m ? `${h} h ${m}` : `${h} h`;
  }

  // --- the hours ---------------------------------------------------------------------------------

  // One block: the title, then the time on its own line. `fit` below drops what does not fit.
  function block(b, r, wide) {
    const len = b.end - b.start;
    const icon = b.category === "assignments" ? `<span class="bn-block-icon">${book(12)}</span>` : "";
    const time = wide ? `${T.range(b.start, b.end)} · ${T.length(len)}${b.pinned ? " · Pinned" : ""}` : T.clock(b.start);
    return `<div class="bn-block${wide ? " bn-wide" : ""}" data-cat="${b.category}" title="${b.title}, ${T.range(b.start, b.end)}"
      style="top:calc(${top(r, b.start)}% + 1.5px);height:calc(${tall(r, len)}% - 3px)">
      <div class="bn-block-title">${icon}<span class="bn-t">${b.title}</span></div><div class="bn-block-time">${time}</div></div>`;
  }

  // Nothing is cut: a block that overflows first puts its time beside the title (wide columns) or
  // drops it (narrow ones), then keeps its title to one line, then shortens the title at a word, and
  // below the room for one word shows its colour alone (look-review.md, section 4).
  function fit(root) {
    for (const b of root.querySelectorAll(".bn-block")) {
      const title = b.querySelector(".bn-block-title");
      const text = b.querySelector(".bn-t");
      const over = () => b.scrollHeight > b.clientHeight + 1 || title.scrollWidth > title.clientWidth + 1;
      if (!over()) continue;
      const time = b.querySelector(".bn-block-time");
      if (b.classList.contains("bn-wide")) {
        b.classList.add("bn-one");
        if (over()) time.remove();
      } else {
        time.remove();
        if (over()) b.classList.add("bn-one");
      }
      const words = text.textContent.split(" ");
      while (words.length > 1 && over()) {
        words.pop();
        text.textContent = words.join(" ");
      }
      if (over()) text.textContent = "";
    }
  }
  function fitLater(el) {
    setTimeout(() => document.fonts.ready.then(() => fit(el)), 0);
  }

  function hourMarks(r, labels) {
    let out = "";
    for (let m = r.from; m <= r.to; m += 60) {
      out += labels
        ? Math.abs(m - W.now) < 25 ? "" : `<div class="bn-hour" style="top:${top(r, m)}%">${T.clock(m)}</div>`
        : `<div class="bn-rule" style="top:${top(r, m)}%"></div>`;
    }
    return out;
  }

  // The hours of the given days, as columns under a row of day names.
  function hours(days, r, { wide = false, heads = true } = {}) {
    const hasToday = days.includes(TODAY);
    const cols = days
      .map((d) => {
        const line = d === TODAY ? `<div class="bn-now" style="top:${top(r, W.now)}%"></div>` : "";
        return `<div class="bn-col${d === TODAY && days.length > 1 ? " today" : ""}">${T.on(d).map((b) => block(b, r, wide)).join("")}${line}</div>`;
      })
      .join("");
    const head = heads
      ? `<div class="bn-dayheads">${days
          .map((d) => `<div class="bn-dayhead${d === TODAY ? " today" : ""}"><span class="bn-dayname">${W.days[d].short}</span><span class="bn-daydate">${W.days[d].date}</span></div>`)
          .join("")}</div>`
      : "";
    const track = hasToday && days.length > 1 ? `<div class="bn-now-track" style="top:${top(r, W.now)}%"></div>` : "";
    const pill = hasToday ? `<div class="bn-now-pill" style="top:${top(r, W.now)}%">${T.clock(W.now)}</div>` : "";
    return `<div class="bn-hours-wrap" style="--bn-cols:${days.length}">
      ${head}
      <div class="bn-hours">
        <div class="bn-gutter">${hourMarks(r, true)}${pill}</div>
        <div class="bn-cols"><div class="bn-rules">${hourMarks(r, false)}${track}</div>${cols}</div>
      </div>
    </div>`;
  }

  function swatch(c) {
    return c === "assignments"
      ? `<span class="bn-swatch bn-swatch-book" data-cat="${c}">${book(11)}</span>`
      : `<span class="bn-swatch" data-cat="${c}"></span>`;
  }

  function legend() {
    return `<div class="bn-legend">${LEGEND.map((c) => `<span class="bn-legend-item">${swatch(c)}${W.categories[c]}</span>`).join("")}</div>`;
  }

  function heroHead(title, sub, icon, withLegend) {
    return `<header class="bn-hero-head">
      <div class="bn-hero-name">
        <span class="bn-hero-icon">${FW.icon(icon, 18)}</span>
        <div><div class="bn-hero-title">${title}</div><div class="bn-hero-sub">${sub}</div></div>
      </div>
      ${withLegend ? legend() : ""}
    </header>`;
  }

  // --- the small tiles ---------------------------------------------------------------------------

  function tileHead(icon, label, extra = "") {
    return `<div class="bn-tile-head"><span class="bn-tile-label">${FW.icon(icon, 16)}${label}</span>${extra}</div>`;
  }

  function nextTile() {
    const n = W.next;
    const b = W.blocks.find((x) => x.title === n.title);
    return `<section class="bn-tile bn-next">
      ${tileHead("clock", "Next", `<span class="bn-tag" data-cat="${b.category}">${swatch(b.category)}${W.categories[b.category]}</span>`)}
      <div class="bn-next-title">${n.title}</div>
      <div class="bn-next-when"><span>${T.clock(n.start)} · ${T.length(b.end - b.start)}</span><span class="bn-pill">in ${n.inMinutes} min</span></div>
      <div class="bn-next-then"><span class="bn-muted">Then</span> Dinner at 18:30 <span class="bn-muted">·</span> History essay at 19:00</div>
    </section>`;
  }

  function dueTile() {
    const rows = W.homework
      .map((h) => {
        const placed = W.blocks.find((b) => b.homework === h.id);
        const when = placed ? `${W.days[placed.days[0]].short} ${T.clock(placed.start)}` : "Not placed";
        return `<li class="bn-due-row" data-cat="assignments">
          <span class="bn-due-icon">${book(14)}</span><span class="bn-due-title">${h.title}</span>
          <span class="bn-due-meta">${short(h.minutes)} · ${when}</span>
        </li>`;
      })
      .join("");
    const share = (placedHomework.length / W.homework.length) * 100;
    return `<section class="bn-tile bn-due">
      ${tileHead("calendar", "Due soon")}
      <div class="bn-figure"><span class="bn-figure-value">3 days</span><span class="bn-figure-sub">until Sunday 27</span></div>
      <ul class="bn-due-list">${rows}</ul>
      <div class="bn-meter-row">
        <div class="bn-meter" data-cat="assignments"><span style="width:${share}%"></span></div>
        <span class="bn-meter-label">${placedHomework.length} of ${W.homework.length} placed</span>
      </div>
    </section>`;
  }

  function loadTile() {
    const per = W.days.map((d) => sum(homeworkOn(d.index), (b) => b.end - b.start));
    const most = Math.max(...per);
    const bars = W.days
      .map((d, i) => {
        const bar = per[i] ? `<span class="bn-bar" data-cat="assignments" style="height:${(per[i] / most) * 100}%"></span>` : "";
        return `<div class="bn-bar-slot${i === TODAY ? " today" : ""}" title="${d.name}: ${per[i] ? T.length(per[i]) : "none"}">
          <div class="bn-bar-track">${bar}</div><span class="bn-bar-day">${d.short.slice(0, 1)}</span></div>`;
      })
      .join("");
    return `<section class="bn-tile bn-load">
      ${tileHead("chart-column", "Homework load")}
      <div class="bn-figure"><span class="bn-figure-value">${T.length(placedMinutes)}</span><span class="bn-figure-sub">placed, ${short(unplacedMinutes)} to go</span></div>
      <div class="bn-bars">${bars}</div>
    </section>`;
  }

  function trayTile() {
    const chips = unplaced
      .map((h) => `<div class="bn-chip" data-cat="assignments">
          <span class="bn-chip-icon">${book(14)}</span>
          <span class="bn-chip-title">${h.title}</span>
          <span class="bn-chip-len">${T.length(h.minutes)}</span>
        </div>`)
      .join("");
    return `<section class="bn-tile bn-tray">
      ${tileHead("list", "Not placed yet", `<span class="bn-count">${unplaced.length}</span>`)}
      <div class="bn-chips">${chips}</div>
      <div class="bn-hint">Drag one onto the week.</div>
    </section>`;
  }

  // The gaps between blocks from the first block to the range's end.
  function freeSlots(day, r) {
    const out = [];
    let at = T.on(day)[0].start;
    for (const b of T.on(day)) {
      if (b.start - at >= 30) out.push([at, b.start]);
      at = Math.max(at, b.end);
    }
    if (r.to - at >= 30) out.push([at, r.to]);
    return out;
  }

  // Today's hours by category, with swatches and a thin stacked bar (plan decision 16), and the
  // free time left in it.
  function daySummary(day, r, withFree) {
    const by = {};
    for (const b of T.on(day)) by[b.category] = (by[b.category] || 0) + b.end - b.start;
    const free = r.to - r.from - minutesOn(day);
    const order = LEGEND.filter((c) => by[c]);
    const segs = order.map((c) => `<span data-cat="${c}" style="flex:${by[c]}"></span>`).join("") + `<span class="bn-free" style="flex:${free}"></span>`;
    const rows = order.map((c) => `<li><span class="bn-sum-key">${swatch(c)}${W.categories[c]}</span><span class="bn-sum-len">${T.length(by[c])}</span></li>`).join("");
    const slots = freeSlots(day, r)
      .filter(([, end]) => end > W.now)
      .map(([a, b]) => `<li><span class="bn-sum-key"><span class="bn-swatch" data-cat="free"></span>${T.range(Math.max(a, W.now), b)}</span><span class="bn-sum-len">${T.length(b - Math.max(a, W.now))}</span></li>`)
      .join("");
    return `<div class="bn-summary">
      <div class="bn-sub-label">Your day <span class="bn-muted">${T.length(minutesOn(day))} planned</span></div>
      <div class="bn-stack">${segs}</div>
      <ul class="bn-sum-list">${rows}</ul>
      ${withFree ? `<div class="bn-sub-label bn-gap">Free from now</div><ul class="bn-sum-list">${slots}</ul>` : ""}
    </div>`;
  }

  // --- A. Bento -----------------------------------------------------------------------------------

  function renderA(el, ctx) {
    const sig = ctx.colours === "signature" ? " bn-sig" : "";
    const hero =
      ctx.view === "day"
        ? `<section class="bn-tile bn-hero">
            ${heroHead("Today", `${ahead} still to come · ${homeworkOn(TODAY).length} homework`, "sun", false)}
            <div class="bn-hero-body bn-hero-day">
              <div class="bn-panel">${hours([TODAY], WEEK, { wide: true, heads: false })}</div>
              <div class="bn-panel bn-side">${daySummary(TODAY, WEEK, true)}</div>
            </div>
          </section>`
        : `<section class="bn-tile bn-hero">
            ${heroHead("This week", `${Math.round(weekMinutes / 60)} h planned`, "calendar-days", true)}
            <div class="bn-hero-body"><div class="bn-panel">${hours([0, 1, 2, 3, 4, 5, 6], WEEK)}</div></div>
          </section>`;
    el.innerHTML = `<div class="bn-board bn-a${sig}">${hero}${nextTile()}${dueTile()}${loadTile()}${trayTile()}</div>`;
    fitLater(el);
  }

  // --- B. Today tiles -----------------------------------------------------------------------------

  // The week at a glance: seven thin columns of the week's blocks, no words, today outlined.
  function glance() {
    const cols = W.days
      .map((d) => {
        const bars = T.on(d.index)
          .map((b) => `<span data-cat="${b.category}" style="top:${top(WEEK, b.start)}%;height:calc(${tall(WEEK, b.end - b.start)}% - 2px)"></span>`)
          .join("");
        const now = d.index === TODAY ? `<i class="bn-glance-now" style="top:${top(WEEK, W.now)}%"></i>` : "";
        return `<div class="bn-glance-col${d.index === TODAY ? " today" : ""}"><div class="bn-glance-bars">${bars}${now}</div><span>${d.short}</span></div>`;
      })
      .join("");
    return `<div class="bn-glance">
      <div class="bn-sub-label">Week at a glance <span class="bn-muted">${Math.round(weekMinutes / 60)} h planned</span></div>
      <div class="bn-glance-cols">${cols}</div>
      ${legend()}
    </div>`;
  }

  function nextCard() {
    const n = W.next;
    const b = W.blocks.find((x) => x.title === n.title);
    return `<div class="bn-next-card">
      <div class="bn-sub-label">Next <span class="bn-tag" data-cat="${b.category}">${swatch(b.category)}${W.categories[b.category]}</span></div>
      <div class="bn-next-card-title">${n.title}</div>
      <div class="bn-next-when"><span>${T.clock(n.start)} · ${T.length(b.end - b.start)}</span><span class="bn-pill">in ${n.inMinutes} min</span></div>
    </div>`;
  }

  function dayTile(d, hover) {
    const day = W.days[d];
    const items = T.on(d);
    const first = items[0];
    const hw = homeworkOn(d).length;
    const dueHere = W.homework.filter((h) => h.due.day === d).length;
    const by = {};
    for (const b of items) by[b.category] = (by[b.category] || 0) + b.end - b.start;
    const segs = LEGEND.filter((c) => by[c]).map((c) => `<span data-cat="${c}" style="flex:${by[c]}"></span>`).join("");
    const free = WEEK.to - WEEK.from - minutesOn(d);
    const flags = [
      hw ? `<span class="bn-hw" data-cat="assignments" title="${hw} homework">${book(12)}${hw}</span>` : "",
      dueHere ? `<span class="bn-due-flag">${dueHere} due</span>` : "",
    ].join("");
    return `<section class="bn-tile bn-daytile${hover ? " hover" : ""}">
      <div class="bn-daytile-head"><span class="bn-daytile-name"><span class="bn-dayname">${day.short}</span> <span class="bn-daytile-date">${day.date}</span></span><span class="bn-flags">${flags}</span></div>
      <div class="bn-first" data-cat="${first.category}"><span class="bn-first-title">${first.title}</span><span class="bn-first-time">${T.clock(first.start)}${items.length > 1 ? ` · ${items.length - 1} more` : ""}</span></div>
      <div class="bn-load-row"><div class="bn-thin">${segs}<span class="bn-free" style="flex:${free}"></span></div><span class="bn-load-label">${short(minutesOn(d))}</span></div>
      <div class="bn-swap">${FW.icon("maximize-2", 14)}Show ${day.name} here</div>
    </section>`;
  }

  function renderB(el, ctx) {
    const sig = ctx.colours === "signature" ? " bn-sig" : "";
    const d = W.days[TODAY];
    const side = ctx.view === "day" ? daySummary(TODAY, WEEK, true) : glance();
    const hero = `<section class="bn-tile bn-hero">
      <div class="bn-hero-body bn-hero-b">
        <div class="bn-panel">${hours([TODAY], DAY, { wide: true, heads: false })}</div>
        <div class="bn-panel bn-side">
          <div class="bn-side-head">${ctx.view === "day" ? heroHead("Today", `${ahead} still to come · ${homeworkOn(TODAY).length} homework`, "sun", false) : heroHead(`${d.name} ${d.date}`, `Today · ${ahead} still to come`, "calendar-days", false)}</div>
          ${nextCard()}${side}
        </div>
      </div>
    </section>`;
    const others = W.days.filter((x) => x.index !== TODAY).map((x) => dayTile(x.index, x.index === 4)).join("");
    el.innerHTML = `<div class="bn-board bn-b${sig}">${hero}${others}</div>`;
    fitLater(el);
  }

  FW.register({
    id: "bento",
    name: "Bento",
    purpose: "Dashboard",
    role: "main",
    now: "A saturated indigo board holding the week, with a white Not placed yet card and a Deadlines list beside it. The board brings its own red-orange zoom buttons and a second red-orange Add, and its blocks are cut to \"Robotics …\" and \"Dinner · 18:…\".",
    current: { week: "current/c-bento-week.png", day: "current/c-bento-day.png" },
    signature: {
      name: "Indigo",
      dark: false,
      vars: {
        "--bn-indigo": "#4338ca",
        "--bn-indigo-ink": "#ffffff",
        "--bn-indigo-muted": "#e0e7ff",
        "--bn-indigo-accent": "#4f46e5",
        "--bn-indigo-accent-dark": "#a5b4fc",
      },
    },
    variants: {
      A: {
        name: "Bento",
        summary: "The week's hours as the hero tile, with Next, Due soon, the week's homework load and Not placed yet as smaller tiles around it. The page is the look's and the tiles are cards with soft shadows; the colour is in the blocks. Indigo paints the hero alone.",
        catalogue: ["Bento Box Grid (neutral page, 16-pixel gaps, 16 radius, soft shadows, tiles of three sizes)", "Swiss Modernism 2.0 type scale", "Inter"],
        changes: [
          "The indigo board becomes a hero tile on the look's page; Indigo stays as a colourway that paints only the hero.",
          "The second Add and the red-orange zoom buttons go: the top bar has Add.",
          "Blocks in the category family with 3-pixel edges; a block drops its time before its title, and shortens a title at a word, never mid-word.",
          "Next is its own tile, the name large and the time beside \"in 20 min\".",
          "Due soon shows the time left and when each homework is placed; the load tile charts the week's homework by day.",
          "Day keeps the tiles and puts the day's summary and its free time beside its hours.",
        ],
        render: renderA,
      },
      B: {
        name: "Today tiles",
        summary: "Today's hours as the hero, and the other six days as small tiles in a row, each with its first item, its load as a thin bar and its homework. Pointing at a day readies it to swap into the hero. Week shows the whole week at a glance beside today; Day shows the day's summary there.",
        catalogue: ["Bento Box Grid (one wide hero, six small tiles)", "Hover lifts a tile with the large shadow (200 ms, none under Reduce motion)", "Inter"],
        changes: [
          "Today is the hero, from the first block to an hour after the last, at a size where every block reads.",
          "The other six days become tiles: first item, a thin stacked load bar, homework count, and \"5 due\" on Sunday.",
          "Friday is shown pointed at, ready to take the hero's place.",
          "Week shows the whole week as a glance strip beside today; Day shows the day's summary and free time there.",
        ],
        render: renderB,
      },
    },
  });
})();
